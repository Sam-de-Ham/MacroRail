"""The scan module's two calibrations, measured once per machine.

Yaw: how many half-steps make one output turn. The 28BYJ-48's gearbox makes it a non-integer
near 4075.77, and a small error adds up over a ring of poses. Yaw homing reports where it found
the magnet in the frame it replaces, so homing once, turning a few turns and homing again
measures those turns to within the homing's repeatability.

Tilt: the angle at which the tilt switch trips, against true level. A straight needle stands
on the holder along the head's up axis. Tilting by t moves a point at height z on it by z·sin t
along the lens axis, so the rail position that focuses the needle's top differs from the one
that focuses its bottom by k·sin t (k: the needle length between the two image rows, times the
rail's direction). If the true tilt is the commanded one plus an error e, measuring that rise
at +a and -a gives

    rise(+a) + rise(-a) = 2k·sin e·cos a        rise(+a) - rise(-a) = 2k·cos e·sin a

so tan e = tan a · (sum / difference), whatever k is. A needle leaning in the head frame adds
the same rise at both tilts, with opposite signs at yaws 180° apart, so each tilt is measured
at two opposite yaws and averaged.
"""

from __future__ import annotations

import math

from ..focus.analysis import AnalysisError

YAW_TURNS = 3  # turns between the two homings
YAW_TOLERANCE = 0.02  # a measured turn further than this from the nominal one is refused
TILT_PROBE_DEG = 10.0  # the tilts the needle is measured at, either side of level
TILT_MAX_ERROR_DEG = 5.0  # a larger error means the needle or the setup is wrong


def half_steps_per_turn(previous_position: int, turns: int, nominal: float) -> float:
    """The turn measured by homing yaw again after `turns` turns: where the magnet was found,
    counted from the first homing."""
    measured = previous_position / turns
    if abs(measured / nominal - 1) > YAW_TOLERANCE:
        raise AnalysisError(
            f"Yaw measured {measured:.1f} half-steps per turn, too far from the nominal "
            f"{nominal:.1f}. Check that the head doesn't slip on its shaft."
        )
    return measured


def tilt_error_deg(rise_up: float, rise_down: float, probe_deg: float, least: float) -> float:
    """How far the true tilt is above the commanded one, from the needle's rise (top focus
    minus bottom focus) at +probe and -probe. `least` is the smallest difference between the
    two rises that is still clearly measured (in the same units)."""
    difference = rise_up - rise_down
    if abs(difference) < least:
        raise AnalysisError(
            "The needle's top and bottom focus too close together when it tilts. Use a "
            "longer needle, standing straight up, and focus on it first."
        )
    error = math.degrees(
        math.atan(math.tan(math.radians(probe_deg)) * (rise_up + rise_down) / difference)
    )
    if abs(error) > TILT_MAX_ERROR_DEG:
        raise AnalysisError(
            f"The tilt seems {error:+.1f}° off, more than expected. Check that the needle "
            "stands straight up in the holder, then measure again."
        )
    return error
