"""Genera el logo de SetID: ``setid.ico`` (multi-tamaño), ``favicon.svg`` y un PNG grande.

Sin dependencias: rasteriza la geometría con supermuestreo y escribe PNG/ICO a mano, así
el icono se puede regenerar en cualquier máquina.

    uv run python scripts/make_icon.py

El logo: un anillo (disco / barrido de reconocimiento) con un hueco arriba a la derecha y un
punto central, en naranja «señal» sobre casi negro.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICO_PATH = ROOT / "backend" / "src" / "setid" / "app" / "assets" / "setid.ico"
SVG_PATH = ROOT / "frontend" / "public" / "favicon.svg"
PNG_PATH = ROOT / "backend" / "src" / "setid" / "app" / "assets" / "setid-256.png"

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# Geometría en un lienzo de 256×256 (coordenadas con y hacia abajo).
CANVAS = 256.0
CORNER = 56.0
CENTER = 128.0
RING_R = 72.0
GAP_FROM, GAP_TO = -80.0, -10.0  # grados; el hueco queda arriba a la derecha
DOT_R = 23.0
BG = (0x0A, 0x0A, 0x0B)
INK = (0xFF, 0x5A, 0x1F)


def stroke_for(size: int) -> float:
    # En tamaños pequeños el trazo es más grueso para que siga leyéndose.
    return 26.0 if size >= 48 else 26.0 + (48 - size) * 0.55


def gap_for(size: int) -> tuple[float, float]:
    # ...y el hueco más ancho, para que los extremos redondeados no lo cierren.
    extra = 0.0 if size >= 48 else (48 - size) * 0.9
    return GAP_FROM - extra / 2, GAP_TO + extra / 2


def in_rounded_square(x: float, y: float) -> bool:
    if not (0 <= x <= CANVAS and 0 <= y <= CANVAS):
        return False
    cx = min(max(x, CORNER), CANVAS - CORNER)
    cy = min(max(y, CORNER), CANVAS - CORNER)
    return (x - cx) ** 2 + (y - cy) ** 2 <= CORNER**2


def _cap(angle: float) -> tuple[float, float]:
    rad = math.radians(angle)
    return CENTER + RING_R * math.cos(rad), CENTER + RING_R * math.sin(rad)


def in_mark(x: float, y: float, stroke: float, gap: tuple[float, float]) -> bool:
    dx, dy = x - CENTER, y - CENTER
    dist = math.hypot(dx, dy)
    if dist <= DOT_R:
        return True
    half = stroke / 2
    if abs(dist - RING_R) <= half:
        angle = math.degrees(math.atan2(dy, dx))
        if not (gap[0] < angle < gap[1]):
            return True
    # Extremos redondeados del arco.
    return any(math.hypot(x - cx, y - cy) <= half for cx, cy in map(_cap, gap))


def render(size: int, samples: int = 4) -> bytes:
    """Devuelve las filas RGBA (sin filtro PNG) de un icono de ``size`` px."""
    stroke = stroke_for(size)
    gap = gap_for(size)
    scale = CANVAS / size
    rows = bytearray()
    for py in range(size):
        rows.append(0)  # filtro PNG «None»
        for px in range(size):
            bg = mark = 0
            for sy in range(samples):
                for sx in range(samples):
                    x = (px + (sx + 0.5) / samples) * scale
                    y = (py + (sy + 0.5) / samples) * scale
                    if in_rounded_square(x, y):
                        bg += 1
                        if in_mark(x, y, stroke, gap):
                            mark += 1
            total = samples * samples
            if bg == 0:
                rows += b"\x00\x00\x00\x00"
                continue
            t = mark / bg
            rgb = [round(b + (i - b) * t) for b, i in zip(BG, INK, strict=True)]
            rows += bytes([*rgb, round(255 * bg / total)])
    return bytes(rows)


def png(size: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8 bits RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(render(size), 9))
        + chunk(b"IEND", b"")
    )


def ico(images: dict[int, bytes]) -> bytes:
    """ICO con imágenes PNG embebidas (válido desde Windows Vista)."""
    count = len(images)
    out = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    data = b""
    for size, image in images.items():
        dim = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(image), offset)
        offset += len(image)
        data += image
    return out + data


def svg() -> str:
    start = _cap(GAP_TO)
    end = _cap(GAP_FROM)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        f'<rect width="256" height="256" rx="{CORNER:g}" fill="#0a0a0b"/>'
        f'<path d="M {start[0]:.2f} {start[1]:.2f} A {RING_R:g} {RING_R:g} 0 1 1 '
        f'{end[0]:.2f} {end[1]:.2f}" fill="none" stroke="#ff5a1f" stroke-width="26" '
        'stroke-linecap="round"/>'
        f'<circle cx="{CENTER:g}" cy="{CENTER:g}" r="{DOT_R:g}" fill="#ff5a1f"/>'
        "</svg>\n"
    )


def main() -> None:
    images = {size: png(size) for size in SIZES}
    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ICO_PATH.write_bytes(ico(images))
    PNG_PATH.write_bytes(images[256])
    SVG_PATH.write_text(svg(), encoding="utf-8")
    for path in (ICO_PATH, PNG_PATH, SVG_PATH):
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
