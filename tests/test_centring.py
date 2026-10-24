"""The centring fit, screw advice and height measurement, on synthetic measurements."""

from __future__ import annotations

import math
import random

import pytest

from macrorail.scan.centring import (
    CentringError,
    Observation,
    fit,
    height_error,
    screw_facing_yaw,
    screw_turns,
)

AXIS_SIDEWAYS = 0.37  # where the yaw axis appears in the image, mm from its centre
AXIS_FOCUS = 21.5  # rail mm that focuses the axis


def observe(x: float, y: float, yaws: list[float], sign: int = 1, noise: float = 0.0,
            seed: int = 1) -> list[Observation]:  # fmt: skip
    rng = random.Random(seed)
    out = []
    for yaw in yaws:
        t = math.radians(yaw)
        depth = x * math.cos(t) - y * math.sin(t)
        sideways = x * math.sin(t) + y * math.cos(t)
        out.append(
            Observation(
                yaw_deg=yaw,
                sideways_mm=AXIS_SIDEWAYS + sideways + rng.gauss(0, noise),
                focus_mm=AXIS_FOCUS - sign * depth + rng.gauss(0, 3 * noise),
            )
        )
    return out


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize(("x", "y"), [(0.6, -0.4), (-1.2, 0.0), (0.0, 2.1), (0.05, 0.02)])
def test_fit_recovers_the_offset_and_the_axis(x: float, y: float, sign: int) -> None:
    result = fit(observe(x, y, [0, 90, 180, 270], sign))
    assert result.offset_x_mm == pytest.approx(x, abs=1e-9)
    assert result.offset_y_mm == pytest.approx(y, abs=1e-9)
    assert result.axis_sideways_mm == pytest.approx(AXIS_SIDEWAYS)
    assert result.axis_focus_mm == pytest.approx(AXIS_FOCUS)
    assert result.depth_agreement_mm == pytest.approx(0, abs=1e-9)
    # The rail's direction is only claimed when the offset shows clearly in depth.
    assert result.rail_sign == (sign if math.hypot(x, y) >= 0.15 else 0)


def test_fit_with_noise_and_uneven_angles() -> None:
    result = fit(observe(0.8, 0.3, [0, 70, 150, 220, 300], noise=0.004))
    assert result.offset_x_mm == pytest.approx(0.8, abs=0.01)
    assert result.offset_y_mm == pytest.approx(0.3, abs=0.01)
    assert result.sideways_rms_mm < 0.01
    assert result.rail_sign == 1


def test_fit_needs_three_angles() -> None:
    with pytest.raises(CentringError, match="three or more"):
        fit(observe(0.5, 0.5, [0, 180, 360]))


def test_screw_turns_push_the_plate_back_onto_the_axis() -> None:
    result = fit(observe(0.6, -0.4, [0, 90, 180, 270]))
    turns = {t.screw: t.turns for t in screw_turns(result)}
    # Turning screw X in moves the plate towards -X: 0.6 mm is 1.2 turns, i.e. 1 1/4 by hand.
    assert turns == {"x": 1.25, "y": -0.75}
    assert not result.centred


def test_centred_needs_no_turns() -> None:
    result = fit(observe(0.03, -0.02, [0, 90, 180, 270]))
    assert result.centred
    assert screw_turns(result) == []


def test_screw_facing_the_user() -> None:
    # At yaw θ screw X points along θ and screw Y along θ + 90°; 180° is away from the lens.
    assert (screw_facing_yaw("x") + 0) % 360 == 180
    assert (screw_facing_yaw("y") + 90) % 360 == 180


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("height", [0.4, -0.25])
def test_height_from_focus_at_two_tilts(height: float, sign: int) -> None:
    focus = {t: AXIS_FOCUS - sign * height * math.sin(math.radians(t)) for t in (-30.0, 30.0)}
    assert height_error(focus, sign) == pytest.approx(height)


def test_height_needs_the_rail_direction() -> None:
    with pytest.raises(CentringError, match="direction"):
        height_error({-30.0: 1.0, 30.0: 2.0}, 0)
