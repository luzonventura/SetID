from __future__ import annotations

import io
import math
import wave
from array import array
from pathlib import Path


def tone_frames(frequency: float, seconds: float, amplitude: float, rate: int = 44_100) -> bytes:
    n = int(seconds * rate)
    samples = array(
        "h",
        (int(amplitude * 32767 * math.sin(2 * math.pi * frequency * i / rate)) for i in range(n)),
    )
    return samples.tobytes()


def wav_bytes(frames: bytes, rate: int = 44_100) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    return buffer.getvalue()


def write_wav(path: Path, frames: bytes, rate: int = 44_100) -> Path:
    path.write_bytes(wav_bytes(frames, rate))
    return path


def counter_wav(path: Path, seconds: int, rate: int = 44_100) -> Path:
    """WAV en el que cada muestra vale su segundo, para comprobar posiciones."""
    samples = array("h", (s for s in range(seconds) for _ in range(rate)))
    return write_wav(path, samples.tobytes(), rate)
