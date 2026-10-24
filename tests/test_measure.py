"""Peaks of focus sweeps, overall and per row of tiles."""

from __future__ import annotations

import numpy as np
import pytest

from macrorail.focus.analysis import Sample
from macrorail.scan.measure import MeasureError, best_focus, peak, row_focus


def gaussian(x: float, centre: float, width: float = 20.0) -> float:
    return float(np.exp(-(((x - centre) / width) ** 2)))


@pytest.mark.parametrize("centre", [103.0, 117.4, 125.0])
def test_peak_between_samples(centre: float) -> None:
    positions = list(range(40, 201, 8))
    values = [gaussian(x, centre) for x in positions]
    assert peak(positions, values) == pytest.approx(centre, abs=1.0)


def test_peak_at_an_end_is_refused() -> None:
    positions = [0, 10, 20, 30]
    with pytest.raises(MeasureError, match="end of the sweep"):
        peak(positions, [4.0, 3.0, 2.0, 1.0])


def test_peak_needs_three_frames() -> None:
    with pytest.raises(MeasureError, match="three"):
        peak([0, 1], [1.0, 2.0])


def sweep(top_centre: float, bottom_centre: float) -> list[Sample]:
    samples = []
    for position in range(0, 201, 5):
        tiles = np.zeros((6, 8))
        tiles[:2, :] = gaussian(position, top_centre)
        tiles[4:, :] = gaussian(position, bottom_centre)
        tiles[2:4, :] = 0.5 * (gaussian(position, top_centre) + gaussian(position, bottom_centre))
        samples.append(Sample(position, tiles))
    return samples[::-1]  # the order frames were taken in doesn't matter


def test_rows_focus_separately() -> None:
    samples = sweep(80.0, 120.0)
    assert row_focus(samples, [0, 1]) == pytest.approx(80.0, abs=1.0)
    assert row_focus(samples, [4, 5]) == pytest.approx(120.0, abs=1.0)


def test_best_focus_of_a_whole_subject() -> None:
    # Parts at nearby depths blur into one peak between them.
    assert best_focus(sweep(95.0, 105.0)) == pytest.approx(100.0, abs=1.0)
