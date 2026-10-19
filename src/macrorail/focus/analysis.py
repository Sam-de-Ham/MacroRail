"""Turning a focus scan (sharpness per tile at each rail position) into answers. Pure functions.

- `find_range`: where the subject starts and ends coming into focus.
- `curve_shift`: how far apart two passes through the same focus curve are.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A tile shows subject detail if its sharpest frame is this many times its typical frame.
PEAK_RATIO = 2.0
# ...and its peak is at least this fraction of the sharpest tile's peak (ignores faint noise).
PEAK_FLOOR = 0.02
# A tile is "in focus" while it is above this fraction of the way from its typical to its peak.
IN_FOCUS_LEVEL = 0.5
# Two passes through focus match if what is left after shifting is under this share of the
# curve's variance.
CURVE_MISMATCH = 0.25
# Forward/backward sweep pairs averaged by a backlash measurement.
BACKLASH_ROUNDS = 2


class AnalysisError(Exception):
    """The scan did not contain what was needed. The message is written for the user."""


@dataclass(frozen=True)
class Sample:
    position: int  # rail position (steps) when the frame was taken
    tiles: np.ndarray  # sharpness per tile


@dataclass(frozen=True)
class RangeResult:
    start: int
    end: int
    positions: tuple[int, ...]
    coverage: tuple[float, ...]  # share of subject tiles in focus at each position
    clipped: bool  # the subject was still in focus at an edge of the scan


def find_range(samples: list[Sample], margin: int) -> RangeResult:
    """The span (plus `margin` on each side) in which some part of the subject is in focus."""
    if len(samples) < 3:
        raise AnalysisError("The scan is too short to judge focus.")
    ordered = sorted(samples, key=lambda s: s.position)
    positions = np.array([s.position for s in ordered])
    sharpness = np.stack([s.tiles.ravel() for s in ordered])  # (samples, tiles)

    typical = np.median(sharpness, axis=0)
    peak = sharpness.max(axis=0)
    subject = (peak > typical * PEAK_RATIO) & (peak > PEAK_FLOOR * peak.max())
    if not subject.any():
        raise AnalysisError(
            "No part of the image came into focus during the scan. Move closer to the subject "
            "or scan a wider span."
        )
    level = typical + IN_FOCUS_LEVEL * (peak - typical)
    in_focus = (sharpness >= level) & subject
    hits = np.flatnonzero(in_focus.any(axis=1))
    first, last = int(hits[0]), int(hits[-1])
    coverage = in_focus[:, subject].mean(axis=1)
    return RangeResult(
        start=int(positions[first]) - margin,
        end=int(positions[last]) + margin,
        positions=tuple(int(p) for p in positions),
        coverage=tuple(round(float(c), 3) for c in coverage),
        clipped=first == 0 or last == len(ordered) - 1,
    )


def strongest_tile(samples: list[Sample]) -> int:
    """The tile whose sharpness changes most through focus: the best one to track."""
    sharpness = np.stack([s.tiles.ravel() for s in samples])
    contrast = sharpness.max(axis=0) / np.maximum(np.median(sharpness, axis=0), 1e-9)
    tile = int(np.argmax(contrast))
    if contrast[tile] < PEAK_RATIO:
        raise AnalysisError("Nothing sharp came into focus. Focus on a detailed subject first.")
    return tile


def curve_shift(
    positions: list[int], forward: list[float], backward: list[float], max_shift: int
) -> float:
    """How far below the forward curve the backward one lies on the motor's scale: the shift
    `L` for which backward(x) best matches forward(x + L), to a quarter step.

    Matching the whole curves rather than their peaks uses the steep flanks, so a broad or
    noisy top does not throw it off."""
    x = np.asarray(positions, dtype=np.float64)
    f = np.asarray(forward, dtype=np.float64)
    b = np.asarray(backward, dtype=np.float64)
    shifts = np.arange(0.0, max_shift + 0.25, 0.25)
    errors = np.full(len(shifts), np.inf)
    for i, shift in enumerate(shifts):
        overlap = x + shift <= x[-1]
        if overlap.sum() >= 3:
            errors[i] = np.mean((b[overlap] - np.interp(x[overlap] + shift, x, f)) ** 2)
    best = int(np.argmin(errors))
    if best == len(shifts) - 1 or errors[best] > CURVE_MISMATCH * np.var(b):
        raise AnalysisError(
            "The two passes through focus did not line up: the backlash is larger than this "
            "measurement covers, or the subject moved."
        )
    return float(shifts[best])
