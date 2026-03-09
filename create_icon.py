"""
create_icon.py — generates assets/icon.ico using Pillow.

Run this once before building with PyInstaller:
    python create_icon.py

Produces a green icon with a white waveform motif at multiple sizes
(256×256, 128×128, 64×64, 48×48, 32×32, 16×16) packed into a single .ico.

Requires: Pillow (pip install pillow)  — already in requirements.txt.
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit(
        "Pillow is required to generate the icon.\n"
        "Run:  pip install pillow"
    )

# Brand green (matches BTN_START_COLOR in constants.py)
GREEN  = (67, 160, 71, 255)
WHITE  = (255, 255, 255, 255)
TRANSP = (0, 0, 0, 0)

SIZES = [256, 128, 64, 48, 32, 16]


def _make_frame(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), TRANSP)
    draw = ImageDraw.Draw(img)

    # Rounded green rectangle background
    pad    = max(1, size // 10)
    radius = max(2, size // 5)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=GREEN,
    )

    # Simple audio-waveform motif: 5 vertical bars of varying heights
    # (centre bar tallest, outer bars shortest)
    num_bars   = 5
    bar_ratios = [0.28, 0.48, 0.65, 0.48, 0.28]  # relative heights
    bar_w      = max(2, size // 14)
    spacing    = max(1, size // 18)
    total_w    = num_bars * bar_w + (num_bars - 1) * spacing
    start_x    = (size - total_w) // 2
    centre_y   = size // 2

    for i, ratio in enumerate(bar_ratios):
        bar_h = max(2, int(size * ratio * 0.75))
        x1 = start_x + i * (bar_w + spacing)
        y1 = centre_y - bar_h // 2
        x2 = x1 + bar_w
        y2 = centre_y + bar_h // 2
        draw.rectangle([x1, y1, x2, y2], fill=WHITE)

    return img


def main() -> None:
    frames     = [_make_frame(s) for s in SIZES]
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    out = assets_dir / "icon.ico"

    frames[0].save(
        out,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"Icon written to: {out}")


if __name__ == "__main__":
    main()
