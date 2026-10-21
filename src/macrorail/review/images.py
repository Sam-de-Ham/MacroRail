"""Image work for review: small copies of each shot, and a quick focus-stacked preview with
its depth map.

Both run on the Pi between and after shots, so they favour speed: JPEGs are decoded at a
reduced scale straight from the file, and the preview stack takes each pixel from whichever
frame is sharpest there. That is plenty to check a stack; final stacking belongs in a
dedicated tool (Zerene Stacker, Helicon Focus) working on the full-resolution files.

The depth map is the focus height of each pixel's winning frame, averaged over a small
neighbourhood weighted by sharpness, so detailed areas decide and flat ones follow them.
It is rough by nature: featureless areas have no real depth, and edges blur into the
background. Grey: white at the first shot's focus, black at the last.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

FRAME_SIDE = 1600  # longest side of the review copies
SHARPNESS_RADIUS = 4  # pixels: neighbourhood that decides which frame wins
DEPTH_SMOOTHING = 0.01  # of the long side: neighbourhood the depth is averaged over
BACKGROUND_DETAIL = 0.05  # of the most detailed areas' sharpness: less than this is background


@dataclass(frozen=True)
class Stacked:
    image: bytes  # JPEG
    depth: bytes  # 16-bit grey PNG (for Blender and the like)
    depth_colour: bytes  # JPEG, false colour: red at the first shot's focus, blue at the last


def shrink(jpeg: bytes, side: int = FRAME_SIDE) -> bytes:
    """A smaller JPEG copy, decoded at reduced scale for speed."""
    with Image.open(io.BytesIO(jpeg)) as image:
        image.draft("RGB", (side, side))
        small = image.convert("RGB")
        small.thumbnail((side, side))
    return _encode(small)


def focus_stack(frames: list[bytes], heights: list[float]) -> Stacked:
    """Combine frames by taking every pixel from the frame that is sharpest around it.
    `heights` is each frame's focus distance from the first frame's (any unit)."""
    first = _decode(frames[0])
    result = first.copy()
    best = _sharpness(first)
    height = np.full(best.shape, heights[0], dtype=np.float32)
    for jpeg, frame_height in zip(frames[1:], heights[1:], strict=True):
        image = _decode(jpeg, size=(first.shape[1], first.shape[0]))
        sharpness = _sharpness(image)
        sharper = sharpness > best
        result[sharper] = image[sharper]
        height[sharper] = frame_height
        np.maximum(best, sharpness, out=best)
    radius = max(1, round(DEPTH_SMOOTHING * max(best.shape)))
    weight = _box_mean(best, radius)
    smooth = _box_mean(best * height, radius) / np.maximum(weight, 1e-6)
    low, high = min(heights), max(heights)
    near = 1 - np.clip((smooth - low) / ((high - low) or 1), 0, 1)  # 1 at the first shot
    # Areas with no detail in any frame are background: fade them to the far end.
    detail = np.percentile(weight, 99) * BACKGROUND_DETAIL
    near *= np.clip(weight / (detail or 1), 0, 1)
    depth = Image.fromarray(np.round(near * 65535).astype(np.uint16))
    colour_map = _turbo(0.1 + 0.8 * near)  # Turbo's ends are near black
    colour = Image.fromarray((colour_map * 255).round().astype(np.uint8))
    return Stacked(_encode(Image.fromarray(result)), _encode_png(depth), _encode(colour))


def _decode(jpeg: bytes, size: tuple[int, int] | None = None) -> np.ndarray:
    with Image.open(io.BytesIO(jpeg)) as image:
        rgb = image.convert("RGB")
        if size is not None and rgb.size != size:
            rgb = rgb.resize(size)
        return np.asarray(rgb).copy()


def _sharpness(rgb: np.ndarray) -> np.ndarray:
    """Local detail: |Laplacian| of the brightness, averaged over a small square."""
    gray = rgb.astype(np.float32).mean(axis=2)
    padded = np.pad(gray, 1, mode="edge")
    laplacian = np.abs(
        4 * gray - padded[:-2, 1:-1] - padded[2:, 1:-1] - padded[1:-1, :-2] - padded[1:-1, 2:]
    )
    return _box_mean(laplacian, SHARPNESS_RADIUS)


def _box_mean(values: np.ndarray, radius: int) -> np.ndarray:
    """Mean over a (2r+1)² square around each pixel, via an integral image."""
    size = 2 * radius + 1
    padded = np.pad(values, radius, mode="edge")
    integral = np.pad(padded.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    total = (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )
    mean: np.ndarray = total / (size * size)
    return mean


def _turbo(x: np.ndarray) -> np.ndarray:
    """The Turbo colour map (polynomial fit by Ruofei Du): dark blue at 0, dark red at 1."""
    coefficients = (
        (0.13572138, 4.61539260, -42.66032258, 132.13108234, -152.94239396, 59.28637943),
        (0.09140261, 2.19418839, 4.84296658, -14.18503333, 4.27729857, 2.82956604),
        (0.10667330, 12.64194608, -60.58204836, 110.36276771, -89.90310912, 27.34824973),
    )
    channels = [np.polynomial.polynomial.polyval(x, c) for c in coefficients]
    rgb: np.ndarray = np.clip(np.stack(channels, axis=-1), 0, 1)
    return rgb


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()
