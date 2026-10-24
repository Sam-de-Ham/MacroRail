"""The calibration maths, on synthetic measurements."""

from __future__ import annotations

import math

import pytest

from macrorail.focus.analysis import AnalysisError
from macrorail.scan.calibrate import half_steps_per_turn, tilt_error_deg

NOMINAL = 4075.7728


def test_turn_from_the_second_homing() -> None:
    assert half_steps_per_turn(12_231, 3, NOMINAL) == pytest.approx(4077.0)


def test_a_slipping_head_is_refused() -> None:
    with pytest.raises(AnalysisError, match="slip"):
        half_steps_per_turn(round(3 * NOMINAL * 1.05), 3, NOMINAL)


def rise(true_deg: float, k: float = 3.2, lean: float = 0.0) -> float:
    return k * math.sin(math.radians(true_deg)) + lean


@pytest.mark.parametrize("error", [0.0, 1.7, -2.4])
@pytest.mark.parametrize("k", [3.2, -2.5])  # either rail direction, any needle length
def test_tilt_error_whatever_the_needle(error: float, k: float) -> None:
    up, down = rise(10 + error, k), rise(-10 + error, k)
    assert tilt_error_deg(up, down, 10.0, least=0.1) == pytest.approx(error)


def test_a_short_needle_is_refused() -> None:
    with pytest.raises(AnalysisError, match="longer needle"):
        tilt_error_deg(rise(10, 0.2), rise(-10, 0.2), 10.0, least=0.1)


def test_a_crooked_needle_is_refused() -> None:
    # A lean that isn't averaged out looks like a large tilt error.
    with pytest.raises(AnalysisError, match="straight up"):
        tilt_error_deg(rise(10, lean=0.8), rise(-10, lean=0.8), 10.0, least=0.1)
