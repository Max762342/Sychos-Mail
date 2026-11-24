#!/usr/bin/env python3
"""Erzeugt die PNG-Icons der Webmail-PWA im Sychos-Look (aus dem SVG-Design).

    python tools/make-icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ICON_DIR = Path(__file__).resolve().parent.parent / "webmail" / "web" / "static" / "icons"
SCALE = 8  # Kantenglaettung: in 8facher Groesse zeichnen, dann herunterskalieren

TOP = (79, 124, 255)     # #4f7cff
BOTTOM = (34, 211, 238)  # #22d3ee
INK = (43, 75, 214)      # #2b4bd6


def gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)),
        )
    return img


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def draw_icon(size: int, padding: int = 0, rounded: bool = True) -> Image.Image:
    """Mail-Icon: Verlaufskachel + weisser Umschlag + Punkt (wie logo.svg)."""
    big = size * SCALE
    pad = padding * SCALE
    inner = big - 2 * pad
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    tile = gradient(inner).convert("RGBA")
    mask = rounded_mask(inner, radius=int(inner * 0.235)) if rounded else Image.new("L", (inner, inner), 255)
    canvas.paste(tile, (pad, pad), mask)

    d = ImageDraw.Draw(canvas)
    # Umschlag (12/64 .. 52/64 des Originals)
    u = inner / 64
    x0, y0 = pad + 12 * u, pad + 19 * u
    x1, y1 = pad + 52 * u, pad + 47 * u
    d.rounded_rectangle([x0, y0, x1, y1], radius=5 * u, fill=(255, 255, 255, 255))
    # Klappe
    width = max(2, round(3.6 * u))
    d.line([(x0 + 5 * u, y0 + 5 * u), (pad + 27 * u, y0 + 16.5 * u), (x1 - 5 * u, y0 + 5 * u)],
           fill=INK + (255,), width=width, joint="curve")
    # Punkt oben rechts
    r = 7.5 * u
    cx, cy = pad + 49 * u, pad + 18 * u
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 14, 23, 255), outline=(255, 255, 255, 255),
              width=max(2, round(3.2 * u)))
    return canvas.resize((size, size), Image.LANCZOS)


def main() -> None:
    targets = {
        "favicon-32.png": 32,
        "preview-64.png": 64,
        "apple-touch-icon.png": 180,
        "icon-192.png": 192,
        "icon-512.png": 512,
        "icon-maskable-512.png": 512,
    }
    for name, size in targets.items():
        pad = int(size * 0.1) if name.startswith("icon-maskable") else 0
        draw_icon(size, padding=pad).save(ICON_DIR / name)
        print(f"{name} ({size}px)")


if __name__ == "__main__":
    main()
