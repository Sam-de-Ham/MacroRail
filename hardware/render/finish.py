"""Puts the raw renders (transparent, shadow in alpha) on the studio background, writes them
into the repository as palette PNGs, and builds the GitHub social preview.

    python hardware/render/finish.py <raw_out> [repo_root]

Needs Pillow and numpy.
"""

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG_TOP, BG_BOTTOM = (246, 246, 244), (232, 232, 229)
FONTS = ("C:/Windows/Fonts/segoeuisl.ttf", "C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf")


def background(w, h):
    t = np.linspace(0, 1, h)[:, None, None]
    g = np.array(BG_TOP) * (1 - t) + np.array(BG_BOTTOM) * t
    return np.repeat(g, w, axis=1)


def composite(path):
    im = np.asarray(Image.open(path).convert("RGBA")).astype(float) / 255
    h, w = im.shape[:2]
    a = im[..., 3:]
    out = background(w, h) * (1 - a) + im[..., :3] * 255 * a  # Blender writes straight alpha
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))


def save(img, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(
        path, optimize=True
    )
    print(f"{os.path.relpath(path):<55} {path.stat().st_size // 1024:4d} kB")


def font(size, bold=False):
    for f in (
        ("C:/Windows/Fonts/segoeuisb.ttf", "C:/Windows/Fonts/segoeuib.ttf") if bold else ()
    ) + FONTS:
        if Path(f).exists() or not Path(f).is_absolute():
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                pass
    return ImageFont.load_default(size)


def social(raw, repo):
    img = composite(Path(raw) / "social" / "rail.png").resize((1280, 640), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    d.text((80, 64), "MacroRail", font=font(72, bold=True), fill=(34, 36, 40))
    d.text(
        (83, 156),
        "Motorised focus-stacking rail with a Raspberry Pi web app",
        font=font(30),
        fill=(92, 96, 102),
    )
    save(img, Path(repo) / "docs" / "images" / "social-preview.png")


def main():
    raw = Path(sys.argv[1])
    repo = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / ".." / ".."
    for root, _, files in os.walk(raw / "docs"):
        for f in sorted(files):
            if f.endswith(".png"):
                src = Path(root) / f
                save(composite(src), repo / src.relative_to(raw))
    if (raw / "social" / "rail.png").exists():
        social(raw, repo)


if __name__ == "__main__":
    main()
