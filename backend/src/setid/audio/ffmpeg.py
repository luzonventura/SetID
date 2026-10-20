"""Inspección y normalización de audio con ffprobe/ffmpeg.

Las rutas se pasan con el prefijo ``file:`` y en forma absoluta: así un nombre que empiece
por ``-`` no se interpreta como opción y nadie puede colar protocolos como ``http:`` o
``concat:`` a través del nombre del archivo.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from setid import proc

SAMPLE_RATE = 44_100
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16 bits

# Contenedores que ffprobe reconoce pero que no son audio aunque tengan "streams".
_IMAGE_FORMATS = {"image2", "png_pipe", "jpeg_pipe", "gif", "webp_pipe", "bmp_pipe", "tiff_pipe"}


class InvalidAudioError(ValueError):
    """El archivo no es audio válido o no cumple los límites. Mensaje apto para el usuario."""


class AudioInfo(BaseModel):
    format_name: str
    duration_s: float
    codec: str


def ffmpeg_input(path: Path) -> str:
    return f"file:{path.resolve()}"


def parse_probe(raw_json: str) -> AudioInfo:
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise InvalidAudioError("No se pudo analizar el archivo.") from exc
    fmt = info.get("format") or {}
    streams = info.get("streams") or []
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    format_name = str(fmt.get("format_name", ""))
    if not audio or set(format_name.split(",")) & _IMAGE_FORMATS:
        raise InvalidAudioError("El archivo no contiene audio.")
    try:
        duration = float(fmt.get("duration") or audio[0].get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise InvalidAudioError("No se conoce la duración del audio.")
    return AudioInfo(
        format_name=format_name, duration_s=duration, codec=str(audio[0].get("codec_name"))
    )


def probe(path: Path, *, timeout: float = 60.0) -> AudioInfo:
    args = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        ffmpeg_input(path),
    ]  # fmt: skip
    try:
        result = proc.run(args, timeout=timeout, program="ffprobe")
    except (proc.ProcessTimeout, proc.ProcessCancelled, proc.ProgramNotFound):
        raise
    except proc.ProcessError as exc:
        raise InvalidAudioError("El archivo no se puede leer como audio.") from exc
    return parse_probe(result.stdout)


def validate_local_file(path: Path, *, max_bytes: int, max_duration_s: float) -> AudioInfo:
    """Valida un archivo local por su contenido real, no por la extensión."""
    if not path.is_file():
        raise InvalidAudioError("El archivo no existe.")
    if path.stat().st_size > max_bytes:
        raise InvalidAudioError(f"El archivo supera el límite de {max_bytes / 1024**3:g} GB.")
    info = probe(path)
    if info.duration_s > max_duration_s:
        raise InvalidAudioError(f"El audio dura más de {max_duration_s / 3600:g} horas.")
    return info


def normalize(src: Path, dst: Path, *, timeout: float) -> Path:
    """Convierte a WAV PCM mono, 44,1 kHz y 16 bits."""
    args = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", ffmpeg_input(src),
        "-map", "0:a:0",
        "-vn", "-sn", "-dn",
        "-ac", str(CHANNELS),
        "-ar", str(SAMPLE_RATE),
        "-c:a", "pcm_s16le",
        "-f", "wav",
        ffmpeg_input(dst),
    ]  # fmt: skip
    proc.run(args, timeout=timeout, program="ffmpeg")
    return dst
