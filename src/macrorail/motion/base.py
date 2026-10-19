"""The focus axis abstraction. v1 implements it with the rail; v1.1 adds a 3D printer.

Positions, distances, speeds and accelerations are in the axis' own steps (`steps_per_mm`
converts), so stack positions stay exact integers on the axis' grid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AxisError(Exception):
    """An axis operation failed. The message is written for the user."""


class MotionInterrupted(AxisError):
    """Motion ended early because it was stopped on purpose."""


@dataclass(frozen=True)
class AxisState:
    connected: bool = False
    driver_ok: bool = False
    enabled: bool = False
    homed: bool = False
    moving: bool = False
    endstop: bool = False
    position: int = 0
    firmware: str | None = None
    problem: str | None = None  # why it is offline or unusable, for the user


class Axis(Protocol):
    steps_per_mm: int
    min_position: int
    max_position: int

    @property
    def state(self) -> AxisState: ...

    async def run(self) -> None:
        """Keep the connection alive for the lifetime of the app (reconnecting as needed)."""

    async def set_current(self, run_ma: int, hold_ma: int) -> None: ...

    async def enable(self) -> None: ...

    async def disable(self) -> None:
        """De-energise the motor. The position is lost, so the axis needs homing again."""

    async def home(self) -> None:
        """Find the home switch, then park clear of it (at `min_position` or beyond)."""

    async def move_to(self, target: int, speed: float, accel: float) -> int: ...

    async def jog(self, delta: int, speed: float, accel: float) -> int: ...

    async def stop(self) -> None:
        """Decelerate to a stop. The running motion raises MotionInterrupted."""
