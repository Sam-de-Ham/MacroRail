"""Stack planning: which positions to shoot, and how long it will take. Pure functions."""

from __future__ import annotations

import math
from dataclasses import dataclass


class PlanError(ValueError):
    """The requested stack cannot be shot. The message is written for the user."""


@dataclass(frozen=True)
class StackPlan:
    positions: tuple[int, ...]
    step: int
    direction: int  # +1 away from home, -1 toward home

    @property
    def start(self) -> int:
        return self.positions[0]

    @property
    def end(self) -> int:
        return self.positions[-1]

    @property
    def count(self) -> int:
        return len(self.positions)


def plan_range(start: int, end: int, step: int, low: int, high: int) -> StackPlan:
    """Shoot from `start` toward `end` every `step`, always covering the whole range.

    If the range is not a whole number of steps, one extra shot lands just past `end`.
    """
    if step < 1:
        raise PlanError("The step must be at least one microstep.")
    if start == end:
        raise PlanError("Start and end are the same position.")
    direction = 1 if end > start else -1
    count = math.ceil(abs(end - start) / step) + 1
    return _build(start, step, count, direction, low, high)


def plan_count(start: int, step: int, count: int, direction: int, low: int, high: int) -> StackPlan:
    if step < 1:
        raise PlanError("The step must be at least one microstep.")
    if count < 2:
        raise PlanError("A stack needs at least two shots.")
    return _build(start, step, count, direction, low, high)


def _build(start: int, step: int, count: int, direction: int, low: int, high: int) -> StackPlan:
    positions = tuple(start + direction * step * i for i in range(count))
    if not (low <= positions[0] <= high and low <= positions[-1] <= high):
        raise PlanError(
            "The stack would run past the end of the rail. Move the range or reduce the step."
        )
    return StackPlan(positions, step, direction)


def move_time(distance: float, speed: float, accel: float) -> float:
    """Duration of a trapezoidal (or triangular, for short moves) move."""
    if distance <= 0:
        return 0.0
    ramp = speed * speed / accel  # distance spent accelerating plus decelerating
    if distance < ramp:
        return 2 * math.sqrt(distance / accel)
    return distance / speed + speed / accel


def estimate_seconds(
    plan: StackPlan, speed: float, accel: float, settle_s: float, capture_s: float
) -> float:
    per_shot = settle_s + capture_s
    return plan.count * per_shot + (plan.count - 1) * move_time(plan.step, speed, accel)
