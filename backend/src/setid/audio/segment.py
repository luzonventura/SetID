"""Segmentación perezosa de un WAV normalizado.

Se lee con ``wave`` saltando a cada posición, así que en memoria solo hay un segmento
(12 s mono a 44,1 kHz son ~1 MB) independientemente de la duración del set.
"""

from __future__ import annotations

import io
import math
import wave
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from setid.audio.ffmpeg import CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH

# El último segmento puede ser más corto; por debajo de esto no merece una consulta.
MIN_SEGMENT_S = 4.0


@dataclass(frozen=True)
class Segment:
    index: int
    start_s: float
    duration_s: float
    wav: bytes


def segment_starts(total_s: float, window_s: float, step_s: float) -> list[float]:
    """Inicios de cada ventana. Útil para saber cuántas consultas costará un set."""
    if window_s <= 0 or step_s <= 0:
        raise ValueError("window_s y step_s deben ser positivos")
    starts: list[float] = []
    count = max(0, math.ceil(total_s / step_s))
    for i in range(count):
        start = i * step_s
        if min(window_s, total_s - start) >= min(MIN_SEGMENT_S, window_s):
            starts.append(start)
    return starts


def _to_wav(frames: bytes, framerate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(CHANNELS)
        out.setsampwidth(SAMPLE_WIDTH)
        out.setframerate(framerate)
        out.writeframes(frames)
    return buffer.getvalue()


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def iter_segments(path: Path, *, window_s: float, step_s: float) -> Generator[Segment]:
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (
            CHANNELS,
            SAMPLE_WIDTH,
            SAMPLE_RATE,
        ):
            raise ValueError("El WAV no está normalizado (mono, 16 bits, 44,1 kHz)")
        framerate = wav.getframerate()
        total_frames = wav.getnframes()
        window_frames = round(window_s * framerate)
        for index, start_s in enumerate(segment_starts(total_frames / framerate, window_s, step_s)):
            start_frame = round(start_s * framerate)
            wav.setpos(start_frame)
            frames = wav.readframes(min(window_frames, total_frames - start_frame))
            duration = len(frames) / (SAMPLE_WIDTH * CHANNELS) / framerate
            yield Segment(index, start_s, duration, _to_wav(frames, framerate))
