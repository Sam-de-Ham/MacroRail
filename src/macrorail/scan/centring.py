"""The centring fit: where the insect sits relative to the yaw axis, and which screw to turn.

The wizard looks at the insect at several yaw angles. In the world frame (X towards the camera,
Y along the tilt axis, Z up) an offset (x, y) of the centring plate, measured in the head frame
that turns with yaw, sits at

    X = x·cos θ - y·sin θ        (depth: along the lens axis)
    Y = x·sin θ + y·cos θ        (sideways: across the image; the camera's right is +Y)

at yaw θ. The image gives the sideways position to a few µm, so that channel alone fixes the
offset, together with where the yaw axis appears in the image. The rail position at which the
insect is sharpest follows the depth channel; it is fitted independently as a cross-check, and
its mean is the rail position that focuses the axis.

Screw X sits on the head's +X side and screw Y on its +Y side. Turning a screw in pushes the
plate away from it, by the M3 pitch per turn; backing it out lets the spring push it back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from ..focus.analysis import AnalysisError

M3_PITCH_MM = 0.5
TURN_RESOLUTION = 1 / 8  # what a hex key can sensibly be turned by
CENTRED_MM = 0.1  # good enough: well inside the frame at every yaw
# The rail's direction is learnt from a fit only when the offset shows clearly in depth.
SIGN_MIN_OFFSET_MM = 0.15


class CentringError(AnalysisError):
    """The measurements can't support a fit. The message is written for the user."""


@dataclass(frozen=True)
class Observation:
    yaw_deg: float
    sideways_mm: float  # the insect's image position along world Y, from the image centre
    focus_mm: float  # rail position where the insect was sharpest


@dataclass(frozen=True)
class CentringFit:
    offset_x_mm: float  # head frame: towards screw X
    offset_y_mm: float  # head frame: towards screw Y
    axis_sideways_mm: float  # where the yaw axis appears in the image, from its centre
    axis_focus_mm: float  # rail position that focuses the yaw axis
    sideways_rms_mm: float  # how well the sideways measurements fit
    depth_agreement_mm: float  # how far the focus measurements disagree with the fit
    # +1 if moving the rail up moves the insect towards the camera (so a nearer insect
    # focuses at a lower rail position), -1 the other way, 0 if this fit can't tell.
    rail_sign: int

    @property
    def distance_mm(self) -> float:
        return math.hypot(self.offset_x_mm, self.offset_y_mm)

    @property
    def centred(self) -> bool:
        return self.distance_mm <= CENTRED_MM


@dataclass(frozen=True)
class ScrewTurn:
    screw: Literal["x", "y"]
    turns: float  # > 0: turn in (clockwise); < 0: back it out


def fit(observations: list[Observation]) -> CentringFit:
    """Least-squares fit of the offset from measurements at three or more yaw angles."""
    angles = {round(o.yaw_deg % 360, 3) for o in observations}
    if len(angles) < 3:
        raise CentringError("Centring needs the insect seen at three or more yaw angles.")
    theta = np.radians([o.yaw_deg for o in observations])
    sideways = np.array([o.sideways_mm for o in observations])
    focus = np.array([o.focus_mm for o in observations])
    ones = np.ones_like(theta)

    # Sideways: Y0 + x·sin θ + y·cos θ
    design = np.column_stack([ones, np.sin(theta), np.cos(theta)])
    (y0, x, y), *_ = np.linalg.lstsq(design, sideways, rcond=None)
    rms = float(np.sqrt(np.mean((design @ np.array([y0, x, y]) - sideways) ** 2)))

    # Depth: focus = F0 - sign·X = F0 - sign·x·cos θ + sign·y·sin θ. Which way the rail moves
    # the insect depends on the rig, so both signs are tried against the sideways fit.
    design = np.column_stack([ones, np.cos(theta), np.sin(theta)])
    (f0, a, b), *_ = np.linalg.lstsq(design, focus, rcond=None)
    misfit = {sign: math.hypot(a + sign * x, b - sign * y) for sign in (1, -1)}
    sign = min(misfit, key=misfit.__getitem__)
    clear = math.hypot(x, y) >= SIGN_MIN_OFFSET_MM and misfit[sign] < 0.5 * misfit[-sign]

    return CentringFit(
        offset_x_mm=float(x),
        offset_y_mm=float(y),
        axis_sideways_mm=float(y0),
        axis_focus_mm=float(f0),
        sideways_rms_mm=rms,
        depth_agreement_mm=float(misfit[sign]),
        rail_sign=sign if clear else 0,
    )


def screw_turns(result: CentringFit) -> list[ScrewTurn]:
    """The turns that bring the insect onto the axis, rounded to what a hand can do."""
    turns = []
    for screw, offset in (("x", result.offset_x_mm), ("y", result.offset_y_mm)):
        amount = round(offset / M3_PITCH_MM / TURN_RESOLUTION) * TURN_RESOLUTION
        if amount:
            turns.append(ScrewTurn(screw, amount))  # type: ignore[arg-type]
    return turns


def screw_facing_yaw(screw: Literal["x", "y"]) -> float:
    """The yaw that points `screw` away from the lens, where a hex key reaches it."""
    return 180.0 if screw == "x" else 90.0


def height_error(focus_at: dict[float, float], rail_sign: int) -> float:
    """How far the insect sits above the tilt axis (mm; negative: below it), from the rail
    positions that focus it at two or more tilts (degrees → rail mm). Tilting by t moves a
    point at height h by h·sin t along the lens axis, towards the camera for t > 0."""
    if len(focus_at) < 2:
        raise CentringError("Measuring the height needs two or more tilts.")
    if rail_sign not in (1, -1):
        raise CentringError("The rail's direction isn't known yet: centre with yaw first.")
    tilts = np.radians(list(focus_at))
    focus = np.array(list(focus_at.values()))
    design = np.column_stack([np.ones_like(tilts), np.sin(tilts)])
    (_, slope), *_ = np.linalg.lstsq(design, focus, rcond=None)
    return float(-slope / rail_sign)
