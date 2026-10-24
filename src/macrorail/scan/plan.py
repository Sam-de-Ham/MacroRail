"""Planning a 3D scan: the poses, in the order they are visited, and what the scan will cost.

Tilt rings go from the top down; within a ring yaw only ever increases, and the next ring
carries on turning the same way (nothing electrical turns with the head, so there is no
reason to unwind, and every arrival takes up backlash the same way).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..focus.analysis import AnalysisError


class ScanPlanError(AnalysisError):
    """The plan can't be made. The message is written for the user."""


@dataclass(frozen=True)
class Pose:
    index: int
    tilt_deg: float
    yaw_deg: float  # 0-360, as shown; the module reaches it turning forwards


def plan_poses(
    tilts: list[float], yaw_step_deg: float, tilt_range: tuple[float, float]
) -> list[Pose]:
    """Every pose: each tilt ring (highest first) at every `yaw_step_deg` round the circle."""
    if not tilts:
        raise ScanPlanError("Add at least one tilt ring.")
    low, high = tilt_range
    outside = [t for t in tilts if not low - 1e-6 <= t <= high + 1e-6]
    if outside:
        raise ScanPlanError(
            f"Tilt {outside[0]:g}° is outside the range ({low:g}° to {high:g}°)."
            + (" Calibrate tilt to reach further down." if outside[0] < low else "")
        )
    if not 1.0 <= yaw_step_deg <= 360.0:
        raise ScanPlanError("The yaw step must be between 1° and 360°.")
    per_ring = max(1, round(360.0 / yaw_step_deg))
    poses: list[Pose] = []
    for tilt in sorted(set(tilts), reverse=True):
        for k in range(per_ring):
            poses.append(Pose(len(poses), tilt, round(k * 360.0 / per_ring, 4)))
    return poses


@dataclass(frozen=True)
class Estimate:
    poses: int
    shots: int  # all poses, at the shots per pose given
    seconds: float
    pi_bytes: int  # previews, depth maps and the kept frames
    card_bytes: int  # the full-size files on the camera's card


PREVIEW_BYTES = 600_000  # a 1600 px preview JPEG, about
DEPTH_BYTES = 500_000  # 16-bit PNG plus the false-colour JPEG
FRAME_BYTES = 250_000  # one 1600 px frame
CARD_BYTES = 10_000_000  # one full-size JPEG fine (A6400), about


def estimate(poses: int, shots_per_pose: int, seconds_per_pose: float, keep_every: int) -> Estimate:
    shots = poses * shots_per_pose
    kept = poses * math.ceil(shots_per_pose / max(keep_every, 1))
    return Estimate(
        poses=poses,
        shots=shots,
        seconds=poses * seconds_per_pose,
        pi_bytes=poses * (PREVIEW_BYTES + DEPTH_BYTES) + kept * FRAME_BYTES,
        card_bytes=shots * CARD_BYTES,
    )
