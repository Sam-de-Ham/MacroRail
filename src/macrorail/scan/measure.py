"""Reading positions out of focus sweeps: where a sharpness curve peaks, overall and per row
of tiles. Pure functions over `focus.analysis.Sample`s, so they are tested on their own."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..focus.analysis import AnalysisError, Sample


class MeasureError(AnalysisError):
    """The sweep can't support the measurement. The message is written for the user."""


def peak(positions: Sequence[float], values: Sequence[float]) -> float:
    """Where `values` peak along `positions`, between samples: a parabola through the best
    sample and its neighbours. A peak at either end of the sweep means it may lie beyond."""
    if len(positions) != len(values) or len(values) < 3:
        raise MeasureError("A focus sweep needs at least three frames.")
    best = int(np.argmax(values))
    if best in (0, len(values) - 1):
        raise MeasureError(
            "The subject came into focus at the end of the scan, or not at all. Focus on it "
            "with the rail first, then try again."
        )
    x0, x1, x2 = positions[best - 1 : best + 2]
    y0, y1, y2 = values[best - 1 : best + 2]
    if not x0 < x1 < x2:
        raise MeasureError("A focus sweep must move one way.")
    # The vertex of the parabola through the three points (unequal spacing allowed).
    denominator = (x0 - x1) * (x0 - x2) * (x1 - x2)
    a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denominator
    b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / denominator
    if a >= 0:
        return float(x1)  # flat or a dip around the best sample: take the sample itself
    return float(min(max(-b / (2 * a), x0), x2))


def best_focus(samples: Sequence[Sample]) -> float:
    """The rail position where the frame as a whole is sharpest."""
    ordered = sorted(samples, key=lambda s: s.position)
    return peak([s.position for s in ordered], [float(s.tiles.sum()) for s in ordered])


def row_focus(samples: Sequence[Sample], rows: Sequence[int]) -> float:
    """The rail position where tile rows `rows` (0 = top) are sharpest together."""
    ordered = sorted(samples, key=lambda s: s.position)
    values = [float(s.tiles[list(rows), :].sum()) for s in ordered]
    if max(values) <= 0:
        raise MeasureError("Those rows show no detail.")
    return peak([s.position for s in ordered], values)
