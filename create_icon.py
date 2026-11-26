"""
create_icon.py — draws the app icon into assets/icon.ico and assets/icon.png.

Run this before building with PyInstaller:
    python create_icon.py

Flat, in the style of yt-slurp's icon: a rounded green square (the same
green as the interface's ACCENT), a dark speech bubble, and a white
waveform whose centre bar is pale green.

Requires: Pillow (already in requirements.txt).
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("Pillow is required to generate the icon.\nRun:  pip install pillow")

GREEN      = "#34c26b"   # matches ACCENT in src/ui/constants.py
DARK       = "#0f1a13"   # matches ACCENT_TEXT
PALE_GREEN = "#a9e5c0"   # GREEN mixed 55% towards white
WHITE      = "#ffffff"

SIZES = [256, 128, 64, 48, 32, 24, 16]
_SUPERSAMPLE = 4


def draw(size: int) -> Image.Image:
    n = size * _SUPERSAMPLE
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([n * .04, n * .04, n * .96, n * .96], radius=n * .22, fill=GREEN)
    # Speech bubble with its tail at the bottom left
    d.rounded_rectangle([n * .17, n * .2, n * .83, n * .7], radius=n * .16, fill=DARK)
    d.polygon([(n * .27, n * .62), (n * .25, n * .84), (n * .46, n * .66)], fill=DARK)
    # Waveform; small sizes get fewer, wider bars so they stay legible
    heights = [.12, .26, .36, .26, .12] if size >= 32 else [.2, .36, .2]
    bar_w, gap = (n * .06, n * .045) if size >= 32 else (n * .1, n * .07)
    x = n / 2 - (len(heights) * bar_w + (len(heights) - 1) * gap) / 2
    for i, h in enumerate(heights):
        fill = PALE_GREEN if i == len(heights) // 2 else WHITE
        d.rounded_rectangle([x, n * .45 - n * h / 2, x + bar_w, n * .45 + n * h / 2], radius=bar_w / 2, fill=fill)
        x += bar_w + gap
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    assets = Path(__file__).parent / "assets"
    assets.mkdir(exist_ok=True)
    frames = [draw(s) for s in SIZES]
    frames[0].save(assets / "icon.ico", format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[1:])
    frames[0].save(assets / "icon.png")
    print(f"Icon written to: {assets}")


if __name__ == "__main__":
    main()
