"""Image work for review: small copies of each shot, and a quick focus-stacked preview.

Both run on the Pi between and after shots, so they favour speed: JPEGs are decoded at a
reduced scale straight from the file, and the preview stack takes each pixel from whichever
frame is sharpest there. That is plenty to check a stack; final stacking belongs in a
dedicated tool (Zerene Stacker, Helicon Focus) working on the full-resolution files.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

FRAME_SIDE = 1600  # longest side of the review copies
SHARPNESS_RADIUS = 4  # pixels: neighbourhood that decides which frame wins


def shrink(jpeg: bytes, side: int = FRAME_SIDE) -> bytes:
    """A smaller JPEG copy, decoded at reduced scale for speed."""
    with Image.open(io.BytesIO(jpeg)) as image:
        image.draft("RGB", (side, side))
        small = image.convert("RGB")
        small.thumbnail((side, side))
    return _encode(small)


def focus_stack(frames: list[bytes]) -> bytes:
    """Combine frames by taking every pixel from the frame that is sharpest around it."""
    first = _decode(frames[0])
    result = first.copy()
    best = _sharpness(first)
    for jpeg in frames[1:]:
        image = _decode(jpeg, size=(first.shape[1], first.shape[0]))
        sharpness = _sharpness(image)
        sharper = sharpness > best
        result[sharper] = image[sharper]
        np.maximum(best, sharpness, out=best)
    return _encode(Image.fromarray(result))


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


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()
