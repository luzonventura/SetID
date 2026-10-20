"""Generador de un "set" sintético para probar todo el pipeline sin gastar consultas.

Cada track del catálogo de demo es un tono puro de una frecuencia concreta, y los tramos
"unreleased" son ruido. :class:`setid.providers.fake.FakeProvider` reconoce esos tonos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from setid import proc
from setid.audio.ffmpeg import SAMPLE_RATE, ffmpeg_input


@dataclass(frozen=True)
class DemoTrack:
    frequency_hz: float
    artist: str
    title: str
    label: str
    isrc: str | None


DEMO_CATALOG: tuple[DemoTrack, ...] = (
    DemoTrack(330.0, "Lumen Grid", "Night Shift", "Demo Records", "XXDEM2600001"),
    DemoTrack(440.0, "Sofia Varela & K-Loop", "Groove Theory", "Fake Tones", "XXDEM2600002"),
    DemoTrack(550.0, "The Sine Collective", "Low End Ritual (Extended Mix)", "Demo Records", None),
    DemoTrack(660.0, "Marta Bass", "Warehouse 4AM", "Synthetic Cuts", "XXDEM2600004"),
    DemoTrack(770.0, "Oscillator Twins", "Back To The Basement", "Fake Tones", None),
)


@dataclass(frozen=True)
class DemoPart:
    seconds: float
    frequency_hz: float | None  # None = ruido (tramo sin identificar)
    volume: float = 0.5


# Unos 20 minutos: intro sin identificar, un tramo débil dentro de un track, un ID – ID,
# un track que vuelve más tarde y un final.
DEMO_SET: tuple[DemoPart, ...] = (
    DemoPart(60, None),
    DemoPart(240, 330.0),
    DemoPart(100, 440.0),
    DemoPart(30, 440.0, volume=0.12),  # baja confianza dentro del track
    DemoPart(110, 440.0),
    DemoPart(150, None),  # unreleased → ID – ID
    DemoPart(210, 550.0),
    DemoPart(120, 330.0),  # vuelve el primer track
    DemoPart(180, 660.0),
    DemoPart(120, 770.0),
)


# El filtro ``sine`` de ffmpeg genera con amplitud 1/8; se compensa para que ``volume`` sea
# el pico final.
_SINE_AMPLITUDE = 1 / 8


def build_filtergraph(parts: tuple[DemoPart, ...]) -> str:
    chains = []
    for i, part in enumerate(parts):
        if part.frequency_hz is None:
            source = f"anoisesrc=color=white:amplitude=0.3:r={SAMPLE_RATE}:d={part.seconds:g}"
        else:
            source = (
                f"sine=frequency={part.frequency_hz:g}:r={SAMPLE_RATE}:d={part.seconds:g},"
                f"volume={part.volume / _SINE_AMPLITUDE:g}"
            )
        chains.append(f"{source}[p{i}]")
    inputs = "".join(f"[p{i}]" for i in range(len(parts)))
    chains.append(f"{inputs}concat=n={len(parts)}:v=0:a=1[out]")
    return ";".join(chains)


def generate_demo_set(dst: Path, parts: tuple[DemoPart, ...] = DEMO_SET) -> Path:
    args = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-filter_complex", build_filtergraph(parts),
        "-map", "[out]",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-f", "wav",
        ffmpeg_input(dst),
    ]  # fmt: skip
    proc.run(args, timeout=300, program="ffmpeg")
    return dst
