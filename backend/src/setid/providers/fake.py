"""Proveedor determinista para tests y desarrollo local, sin red y sin coste.

Reconoce los tonos puros del set de demo (:mod:`setid.audio.demo`): estima la frecuencia
dominante por cruces por cero y la busca en el catálogo con una tolerancia que simula el
pitch del DJ. La confianza depende del volumen. Con audio real casi nunca encuentra nada.
"""

from __future__ import annotations

import asyncio
import io
import itertools
import statistics
import sys
import wave
from array import array
from collections.abc import Sequence
from typing import NamedTuple

from setid.audio.demo import DEMO_CATALOG, DemoTrack
from setid.models import Match
from setid.providers.base import clamp_confidence

# Un tono puro cruza el cero a intervalos casi idénticos (variación ~2 %); la música real y el
# ruido no. Por encima de este coeficiente de variación no se considera un tono del catálogo.
MAX_IRREGULARITY = 0.15


class ToneAnalysis(NamedTuple):
    frequency_hz: float
    peak: float  # 0–1
    irregularity: float  # coeficiente de variación de los intervalos entre cruces por cero


_SILENCE = ToneAnalysis(0.0, 0.0, float("inf"))


def analyze_tone(wav_bytes: bytes) -> ToneAnalysis:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            return _SILENCE
        rate = wav.getframerate()
        samples = array("h")
        samples.frombytes(wav.readframes(wav.getnframes()))
    if sys.byteorder == "big":
        samples.byteswap()
    if len(samples) < 2:
        return _SILENCE
    crossings = [i for i, (a, b) in enumerate(itertools.pairwise(samples)) if (a < 0) != (b < 0)]
    if len(crossings) < 3:
        return _SILENCE
    intervals = [b - a for a, b in itertools.pairwise(crossings)]
    mean = statistics.fmean(intervals)
    irregularity = statistics.pstdev(intervals) / mean if mean else float("inf")
    peak = max(abs(min(samples)), abs(max(samples))) / 32768
    return ToneAnalysis(len(crossings) * rate / (2 * len(samples)), peak, irregularity)


class FakeProvider:
    name = "fake"
    cost_per_query = 0.0

    def __init__(
        self,
        catalog: Sequence[DemoTrack] = DEMO_CATALOG,
        *,
        pitch_tolerance: float = 0.06,
        latency_s: float = 0.0,
    ) -> None:
        self._catalog = tuple(catalog)
        self._tolerance = pitch_tolerance
        self._latency_s = latency_s

    async def identify(self, segment: bytes) -> Match | None:
        if self._latency_s:
            await asyncio.sleep(self._latency_s)
        frequency, peak, irregularity = await asyncio.to_thread(analyze_tone, segment)
        if frequency <= 0 or irregularity > MAX_IRREGULARITY:
            return None
        track = min(self._catalog, key=lambda t: abs(t.frequency_hz - frequency))
        if abs(track.frequency_hz - frequency) > track.frequency_hz * self._tolerance:
            return None
        return Match(
            artist=track.artist,
            title=track.title,
            label=track.label,
            isrc=track.isrc,
            confidence=clamp_confidence(round(peak * 1.9, 2)),
            provider=self.name,
        )

    async def aclose(self) -> None:
        return None
