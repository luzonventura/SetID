"""Metadatos y descarga de audio con yt-dlp.

Solo acepta :class:`CanonicalSource`, es decir, URLs ya validadas y reconstruidas. Aun así
se pasan siempre detrás de ``--`` y con ``--ignore-config`` para que ninguna configuración
local cambie el comportamiento.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from setid import proc
from setid.sources.url import CanonicalSource

_COMMON = ["--ignore-config", "--no-playlist", "--no-warnings", "--no-progress", "--color", "never"]
_EXPECTED_EXTRACTORS = {"youtube", "soundcloud"}


class SourceRejected(ValueError):
    """La fuente existe pero no se puede procesar. Mensaje apto para el usuario."""


class SourceMetadata(BaseModel):
    id: str
    title: str
    uploader: str | None = None
    duration_s: float
    description: str | None = None
    webpage_url: str | None = None


def parse_metadata(raw_json: str, *, max_duration_s: float) -> SourceMetadata:
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SourceRejected("yt-dlp devolvió metadatos no válidos.") from exc
    if not isinstance(info, dict):
        raise SourceRejected("yt-dlp devolvió metadatos no válidos.")
    if info.get("_type", "video") != "video":
        raise SourceRejected("El enlace apunta a una lista, no a un único set.")
    if str(info.get("extractor_key", "")).lower() not in _EXPECTED_EXTRACTORS:
        raise SourceRejected("Fuente no soportada.")
    if info.get("is_live"):
        raise SourceRejected("No se pueden procesar directos en curso.")
    duration = info.get("duration")
    if not isinstance(duration, int | float) or duration <= 0:
        raise SourceRejected("No se conoce la duración del set.")
    if duration > max_duration_s:
        hours = max_duration_s / 3600
        raise SourceRejected(f"El set dura más de {hours:g} horas.")
    try:
        return SourceMetadata(
            id=str(info.get("id", "")),
            title=str(info.get("title") or "Sin título"),
            uploader=info.get("uploader") or info.get("channel"),
            duration_s=float(duration),
            description=info.get("description"),
            webpage_url=info.get("webpage_url"),
        )
    except ValidationError as exc:
        raise SourceRejected("yt-dlp devolvió metadatos no válidos.") from exc


def fetch_metadata(
    source: CanonicalSource, *, max_duration_s: float, timeout: float
) -> SourceMetadata:
    args = [
        *proc.yt_dlp_command(),
        *_COMMON,
        "--dump-single-json",
        "--skip-download",
        "--",
        source.url,
    ]
    result = proc.run(args, timeout=timeout, program="yt-dlp")
    return parse_metadata(result.stdout, max_duration_s=max_duration_s)


def download_audio(
    source: CanonicalSource, workdir: Path, *, max_bytes: int, timeout: float
) -> Path:
    """Descarga solo la pista de audio a ``workdir`` y devuelve la ruta del archivo."""
    args = [
        *proc.yt_dlp_command(),
        *_COMMON,
        "--format",
        "bestaudio/best",
        "--max-filesize",
        str(max_bytes),
        "--no-part",
        "--no-mtime",
        "--no-cache-dir",
        "--paths",
        str(workdir),
        "--output",
        "source.%(ext)s",
        "--",
        source.url,
    ]
    proc.run(args, timeout=timeout, program="yt-dlp")
    files = [p for p in workdir.glob("source.*") if p.is_file()]
    if len(files) != 1:
        raise SourceRejected("La descarga no produjo un archivo de audio (¿supera el límite?).")
    return files[0]


class CommunityData(BaseModel):
    description: str | None = None
    comments: list[dict[str, object]] = []


def parse_community_json(raw_json: str) -> CommunityData:
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError:
        return CommunityData()
    if not isinstance(info, dict):
        return CommunityData()
    comments = info.get("comments")
    description = info.get("description")
    return CommunityData(
        description=description if isinstance(description, str) else None,
        comments=[c for c in comments if isinstance(c, dict)] if isinstance(comments, list) else [],
    )


def fetch_community(source: CanonicalSource, *, max_comments: int, timeout: float) -> CommunityData:
    """Descripción y comentarios (los más votados, con sus respuestas) del vídeo o track."""
    n = max(1, max_comments)
    args = [
        *proc.yt_dlp_command(),
        *_COMMON,
        "--skip-download",
        "--write-comments",
        # max_comments, max_parents, max_replies, max_replies_per_thread; los más votados.
        "--extractor-args",
        f"youtube:max_comments={n},{n},{n},10;comment_sort=top",
        "--dump-single-json",
        "--",
        source.url,
    ]
    return parse_community_json(proc.run(args, timeout=timeout, program="yt-dlp").stdout)
