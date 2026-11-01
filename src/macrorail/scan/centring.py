"""The centring fit: where the insect sits relative to the yaw axis, and which screw to turn.

The wizard looks at the insect at several yaw angles. In the world frame (X towards the camera,
Y along the tilt axis, Z up) an offset (x, y) of the centring plate, measured in the head frame
that turns with yaw (+x towards screw X, +y towards screw Y), sits at

    X = x·cos φ - y·sin φ        (depth: along the lens axis)
    Y = x·sin φ + y·cos φ        (sideways: across the image; the camera's right is +Y)

where φ = θ + SCREW_X_YAW_DEG is the direction screw X points at yaw θ. The image gives the
sideways position to a few µm, so that channel alone fixes the offset, together with where the
yaw axis appears in the image. The rail position at which the insect is sharpest follows the
depth channel; it is fitted independently as a cross-check, and its mean is the rail position
that focuses the axis.

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
# Where screw X points at yaw 0, counter-clockwise from the camera (seen from above): straight
# at the camera, as designed.
SCREW_X_YAW_DEG = 0.0
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
    theta = np.radians([o.yaw_deg + SCREW_X_YAW_DEG for o in observations])
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


Signs = dict[Literal["x", "y"], int]
DESIGN_SIGNS: Signs = {"x": 1, "y": 1}  # turning in moves the plate towards -x / -y


def screw_turns(result: CentringFit, signs: Signs = DESIGN_SIGNS) -> list[ScrewTurn]:
    """The turns that bring the insect onto the axis, rounded to what a hand can do. `signs`
    are the screws' directions as learnt on the rig (-1: that screw moves the plate the other
    way than designed)."""
    turns = []
    offsets: tuple[tuple[Literal["x", "y"], float], ...] = (
        ("x", result.offset_x_mm),
        ("y", result.offset_y_mm),
    )
    for screw, offset in offsets:
        amount = round(signs[screw] * offset / M3_PITCH_MM / TURN_RESOLUTION) * TURN_RESOLUTION
        if amount:
            turns.append(ScrewTurn(screw, amount))
    return turns


def plate_move_mm(turn: ScrewTurn, signs: Signs = DESIGN_SIGNS) -> float:
    """How far `turn` moves the plate along its screw's axis (head frame)."""
    return -signs[turn.screw] * turn.turns * M3_PITCH_MM


# A turn has to move the plate at least this far before its direction is judged from it.
CHECK_MIN_MM = 0.1


def wrong_way(
    before: CentringFit, after: CentringFit, advice: list[ScrewTurn], signs: Signs
) -> list[Literal["x", "y"]]:
    """The screws that moved the plate the opposite way to `advice`, judged by the next round
    (the user turned them as advised in between). Not turning a screw at all never counts."""
    moved: dict[Literal["x", "y"], float] = {
        "x": after.offset_x_mm - before.offset_x_mm,
        "y": after.offset_y_mm - before.offset_y_mm,
    }
    wrong: list[Literal["x", "y"]] = []
    for turn in advice:
        expected = plate_move_mm(turn, signs)
        actual = moved[turn.screw]
        if (
            abs(expected) >= CHECK_MIN_MM
            and actual * expected < 0
            and abs(actual) > abs(expected) / 2
        ):
            wrong.append(turn.screw)
    return wrong


def screw_facing_yaw(screw: Literal["x", "y"], access_deg: float) -> float:
    """The yaw that points `screw` at `access_deg` (counter-clockwise from the camera, seen
    from above), where the hex key reaches it best. Screw Y sits 90° counter-clockwise of X."""
    return (access_deg - SCREW_X_YAW_DEG - (90.0 if screw == "y" else 0.0)) % 360.0


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
