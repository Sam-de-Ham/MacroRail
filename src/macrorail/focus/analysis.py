"""Turning a focus scan (sharpness per tile at each rail position) into answers. Pure functions.

- `find_range`: where the subject starts and ends coming into focus.
- `peak_position`: where one sharpness curve peaks, to sub-sample precision.
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


def peak_position(positions: list[int], values: list[float]) -> float:
    """Where a sharpness curve peaks: a parabola fitted through the points around its top."""
    x = np.asarray(positions, dtype=np.float64)
    y = np.asarray(values, dtype=np.float64)
    top = int(np.argmax(y))
    near = y >= y.min() + 0.5 * (y[top] - y.min())
    lo, hi = top, top
    while lo > 0 and near[lo - 1]:
        lo -= 1
    while hi < len(y) - 1 and near[hi + 1]:
        hi += 1
    lo, hi = max(lo, top - 8), min(hi, top + 8)  # the top of the peak, not its tails
    if hi - lo < 2:
        lo, hi = max(0, top - 1), min(len(y) - 1, top + 1)
    if hi - lo < 2 or top in (0, len(y) - 1):
        raise AnalysisError("The sharpness peak is at the edge of the scan. Focus closer to it.")
    a, b, _ = np.polyfit(x[lo : hi + 1], y[lo : hi + 1], 2)
    if a >= 0:  # not a peak: fall back to the best sample
        return float(x[top])
    return float(-b / (2 * a))
