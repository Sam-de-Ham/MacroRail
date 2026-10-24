"""How sharp each part of a live-view frame is.

The frame is split into a grid of tiles and each tile scores the energy of its Laplacian:
fine detail in focus scores high, the same detail out of focus (or empty background) scores
low. Scoring tiles separately lets a scan see each part of the subject come into focus at its
own depth.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

GRID_ROWS = 6
GRID_COLS = 8


def tile_sharpness(jpeg: bytes) -> np.ndarray:
    """A (GRID_ROWS, GRID_COLS) array of sharpness scores for one JPEG frame."""
    with Image.open(io.BytesIO(jpeg)) as image:
        image.draft("L", (image.width // 2, image.height // 2))  # fast reduced-size decode
        gray = np.asarray(image.convert("L"), dtype=np.float32)
    laplacian = (
        4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    )
    energy = laplacian * laplacian
    height = energy.shape[0] // GRID_ROWS
    width = energy.shape[1] // GRID_COLS
    tiles = energy[: height * GRID_ROWS, : width * GRID_COLS]
    return tiles.reshape(GRID_ROWS, height, GRID_COLS, width).mean(axis=(1, 3))


@dataclass(frozen=True)
class Detail:
    """Where the sharp detail in a frame is: its sharpness-weighted centre, in pixels of the
    full frame from its top-left corner, and how strong it is overall."""

    u: float  # to the right
    v: float  # down
    strength: float
    width: int  # the frame's size, so callers can convert to a position from the centre
    height: int


def detail_centre(jpeg: bytes, keep: float = 0.2) -> Detail | None:
    """The centre of the frame's sharp detail: the Laplacian energy, keeping only what is at
    least `keep` of its 99.5th percentile (so the background and blurred parts don't pull),
    weighted by that energy. None if the frame has no detail."""
    with Image.open(io.BytesIO(jpeg)) as image:
        full = image.size
        image.draft("L", (image.width // 2, image.height // 2))
        gray = np.asarray(image.convert("L"), dtype=np.float32)
    laplacian = (
        4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    )
    energy = laplacian * laplacian
    top = float(np.percentile(energy, 99.5))
    if top <= 0:
        return None
    weight = np.where(energy >= keep * top, energy, 0.0)
    total = float(weight.sum())
    if total <= 0:
        return None
    rows, cols = np.indices(weight.shape)
    scale_u = full[0] / gray.shape[1]
    scale_v = full[1] / gray.shape[0]
    # +1: the Laplacian drops the frame's outermost pixels.
    u = (float((weight * cols).sum()) / total + 1 + 0.5) * scale_u
    v = (float((weight * rows).sum()) / total + 1 + 0.5) * scale_v
    return Detail(u=u, v=v, strength=total / weight.size, width=full[0], height=full[1])
