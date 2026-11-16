"""Dibuja el fondo de la ventana del .dmg: «arrastra SetID a Aplicaciones».

Necesita Pillow, que no es dependencia del proyecto (solo hace falta al construir el .dmg):

    uv run --with pillow python scripts/make_dmg_background.py <carpeta>

Escribe ``background.png`` (660×400) y ``background@2x.png`` (1320×800) en la carpeta. En el
Mac, ``build_app.py --dmg`` los junta en un TIFF multirresolución para pantallas Retina.

Las posiciones de los iconos (``APP_POS``, ``APPS_POS``) las usa también ``create-dmg``, así
que el dibujo y la ventana del Finder coinciden siempre.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 660, 400
S = 2  # se dibuja a 2× y se reduce para la versión 1×
ICON_SIZE = 128
TEXT_SIZE = 13
APP_POS = (170, 196)  # centro del icono de SetID.app
APPS_POS = (490, 196)  # centro del acceso directo a Aplicaciones

# Paleta de la app (frontend/src/index.css) y el azul hielo de la vista 3D.
INK = (0x0A, 0x0A, 0x0B)
LINE = (0x26, 0x26, 0x2B)
FOG = (0x8C, 0x8C, 0x96)
CHALK = (0xED, 0xED, 0xEF)
ICE = (0x7D, 0xD3, 0xFC)
# Fondo de la etiqueta bajo cada icono. El Finder pinta el nombre en negro (modo claro) o en
# blanco (modo oscuro) y no deja elegir: con un tono medio ambos se leen (contraste ≈ 4,5:1).
PLATE = (0x4F, 0x7F, 0x99)

TITLE = "Arrastra SetID a Aplicaciones"
SUBTITLE = "Luego ábrela desde Aplicaciones o Launchpad."
HINT = "¿No se abre? Ajustes del Sistema › Privacidad y seguridad › Abrir igualmente"

# (ruta, índice en la colección, eje de peso para fuentes variables)
_FONTS = {
    "bold": [
        ("/System/Library/Fonts/SFNS.ttf", 0, 640),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1, None),
        ("C:/Windows/Fonts/seguisb.ttf", 0, None),
        ("C:/Windows/Fonts/segoeuib.ttf", 0, None),
    ],
    "regular": [
        ("/System/Library/Fonts/SFNS.ttf", 0, 400),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0, None),
        ("C:/Windows/Fonts/segoeui.ttf", 0, None),
    ],
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path, index, weight in _FONTS[kind]:
        if not Path(path).is_file():
            continue
        try:
            loaded = ImageFont.truetype(path, size, index=index)
        except OSError:
            continue
        if weight is not None:
            try:
                axes = loaded.get_variation_axes()
                values = [
                    weight
                    if bytes(a.get("name", b"")).lower() in {b"weight", b"wght"}
                    else a["default"]
                    for a in axes
                ]
                loaded.set_variation_by_axes(values)
            except (OSError, KeyError, TypeError):
                pass
        return loaded
    return ImageFont.load_default(size)


def centered_text(
    draw: ImageDraw.ImageDraw,
    y: float,
    text: str,
    fnt: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    draw.text((WIDTH * S / 2, y * S), text, font=fnt, fill=fill, anchor="mm")


def glow(
    size: tuple[int, int],
    shapes: list[tuple[str, tuple[float, ...], int]],
    blur: float,
    color: tuple[int, int, int],
    alpha: int,
) -> Image.Image:
    """Capa RGBA con formas desenfocadas (halo)."""
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    for kind, box, width in shapes:
        if kind == "ellipse":
            d.ellipse(box, fill=255)
        else:
            d.line(box, fill=255, width=width, joint="curve")
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    layer = Image.new("RGBA", size, (*color, 0))
    layer.putalpha(mask.point(lambda v: v * alpha // 255))
    return layer


def arrow_points() -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    y = APP_POS[1] * S
    start = (APP_POS[0] + ICON_SIZE / 2 + 26) * S
    end = (APPS_POS[0] - ICON_SIZE / 2 - 26) * S
    head = 13 * S
    shaft = [(start, y), (end, y)]
    tip = [(end - head, y - head), (end, y), (end - head, y + head)]
    return shaft, tip


def render() -> Image.Image:
    size = (WIDTH * S, HEIGHT * S)
    img = Image.new("RGBA", size, (*INK, 255))

    # Halo azul muy tenue detrás de los iconos.
    cx, cy = WIDTH * S / 2, APP_POS[1] * S
    img.alpha_composite(
        glow(
            size,
            [("ellipse", (cx - 300 * S, cy - 120 * S, cx + 300 * S, cy + 120 * S), 0)],
            90 * S,
            ICE,
            34,
        )
    )

    draw = ImageDraw.Draw(img)

    # Anillos alrededor de SetID, como el logo (un anillo con el punto en el centro).
    ax, ay = APP_POS[0] * S, APP_POS[1] * S
    for radius, color in ((96, LINE), (124, (0x1A, 0x1A, 0x1E))):
        r = radius * S
        draw.ellipse((ax - r, ay - r, ax + r, ay + r), outline=color, width=S)

    # Flecha con un poco de brillo.
    shaft, tip = arrow_points()
    img.alpha_composite(
        glow(
            size,
            [("line", (*shaft[0], *shaft[1]), 10 * S), ("line", sum(tip, ()), 10 * S)],
            10 * S,
            ICE,
            90,
        )
    )
    draw = ImageDraw.Draw(img)
    x0, y0 = shaft[0]
    x1, _ = shaft[1]
    dash, gap = 6 * S, 7 * S
    x = x0
    while x < x1 - 4 * S:
        draw.line((x, y0, min(x + dash, x1 - 4 * S), y0), fill=ICE, width=3 * S)
        x += dash + gap
    draw.line(tip, fill=ICE, width=3 * S, joint="curve")
    for px, py in (tip[0], tip[2]):
        r = 1.5 * S
        draw.ellipse((px - r, py - r, px + r, py + r), fill=ICE)

    # Fondo de las etiquetas que pinta el Finder bajo cada icono.
    for px, py in (APP_POS, APPS_POS):
        top = py + ICON_SIZE / 2 + 3
        box = ((px - 70) * S, top * S, (px + 70) * S, (top + 24) * S)
        draw.rounded_rectangle(box, radius=12 * S, fill=PLATE)

    centered_text(draw, 52, TITLE, font("bold", 23 * S), CHALK)
    centered_text(draw, 80, SUBTITLE, font("regular", 13 * S), FOG)
    centered_text(draw, 356, HINT, font("regular", 11 * S), FOG)
    return img.convert("RGB")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    out.mkdir(parents=True, exist_ok=True)
    big = render()
    big.save(out / "background@2x.png", dpi=(144, 144))
    big.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(out / "background.png", dpi=(72, 72))
    print(f"{out / 'background.png'}\n{out / 'background@2x.png'}")


if __name__ == "__main__":
    main()
