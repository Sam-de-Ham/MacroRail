"""How sharp each part of a live-view frame is.

The frame is split into a grid of tiles and each tile scores the energy of its Laplacian:
fine detail in focus scores high, the same detail out of focus (or empty background) scores
low. Scoring tiles separately lets a scan see each part of the subject come into focus at its
own depth.
"""

from __future__ import annotations

import io

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
