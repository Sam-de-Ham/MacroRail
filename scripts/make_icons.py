"""Draws the app icons (PNG) used when MacroRail is added to a home screen.

They mirror src/macrorail/web/icon.svg. Run after changing it:  uv run python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "macrorail" / "web" / "icons"
BACKGROUND = (22, 25, 30)
RAIL = (91, 99, 110)
ACCENT = (242, 163, 58)


def draw(size: int, *, maskable: bool) -> Image.Image:
    """The 32-unit icon design at `size` pixels. Maskable icons fill the square and keep the
    design inside the central 80 % safe zone."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    if maskable:
        d.rectangle((0, 0, size, size), fill=BACKGROUND)
        unit, offset = size * 0.8 / 32, size * 0.1
    else:
        unit, offset = size / 32, 0.0
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=7 * unit, fill=BACKGROUND)

    def box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        return (
            offset + x * unit,
            offset + y * unit,
            offset + (x + w) * unit,
            offset + (y + h) * unit,
        )

    d.rounded_rectangle(box(5, 20, 22, 3), radius=1.5 * unit, fill=RAIL)
    d.rounded_rectangle(box(11, 15, 10, 5), radius=1.5 * unit, fill=ACCENT)
    d.ellipse(box(12.8, 6.8, 6.4, 6.4), outline=ACCENT, width=max(1, round(2 * unit)))
    return image


def main() -> None:
    OUT.mkdir(exist_ok=True)
    draw(192, maskable=False).save(OUT / "icon-192.png")
    draw(512, maskable=False).save(OUT / "icon-512.png")
    draw(512, maskable=True).save(OUT / "icon-maskable-512.png")
    draw(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")


if __name__ == "__main__":
    main()
