"""Focus scans: step through positions, read sharpness from live view at each, then analyse.

A scan is the building block for anything that needs to know where things are in focus:
finding a subject's front and back (auto range) now, and re-finding it after each turn of a
rotation stage later. Every sweep approaches its first position in its own direction, so the
lead-screw backlash is taken up the same way for every frame.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass

from ..camera.base import Camera
from ..motion.base import Axis
from .analysis import (
    BACKLASH_ROUNDS,
    RangeResult,
    Sample,
    curve_shift,
    find_range,
    strongest_tile,
)
from .sharpness import tile_sharpness

Approach = Callable[[int, int], Awaitable[None]]

# The largest backlash a measurement looks for. A worn lead-screw nut is well under this.
MAX_BACKLASH_MM = 0.25


@dataclass(frozen=True)
class Motion:
    speed: float
    accel: float
    settle_s: float


@dataclass(frozen=True)
class BacklashResult:
    backlash: float  # steps the carriage lags behind the motor after a reversal
    spread: float  # how much the rounds disagreed (repeatability), steps
    suggested_takeup: int  # steps of overshoot to use when approaching a position


class FocusScanner:
    def __init__(
        self,
        axis: Axis,
        camera: Camera,
        approach: Approach,
        check_stop: Callable[[], None],
        on_change: Callable[[], None],
    ) -> None:
        self._axis = axis
        self._camera = camera
        self._approach = approach
        self._check_stop = check_stop
        self._on_change = on_change
        self.task: str | None = None  # "range" or "backlash" while a scan runs
        self.done = 0
        self.total = 0
        self.range: RangeResult | None = None
        self.backlash: BacklashResult | None = None

    def snapshot(self) -> dict[str, object]:
        return {
            "task": self.task,
            "done": self.done,
            "total": self.total,
            "range": asdict(self.range) if self.range else None,
            "backlash": asdict(self.backlash) if self.backlash else None,
        }

    async def find_range(self, center: int, span: int, step: int, motion: Motion) -> RangeResult:
        """Scan `span` steps centred on `center` every `step` steps for the subject's extent."""
        positions = self._positions(center - span // 2, center + span // 2, step)
        self._begin("range", len(positions))
        try:
            samples = await self._sweep(positions, motion)
            self.range = find_range(samples, margin=max(1, step // 2))
            return self.range
        finally:
            self._end()

    async def measure_backlash(self, center: int, dof: int, motion: Motion) -> BacklashResult:
        """Find a sharp detail near `center`, then pass through its focus forwards and
        backwards. The carriage lags the motor by the backlash after each reversal, so the
        backward pass sees the same sharpness curve that much lower on the motor's scale."""
        coarse = self._positions(center - 6 * dof, center + 6 * dof, max(1, dof // 2))
        max_backlash = round(MAX_BACKLASH_MM * self._axis.steps_per_mm)
        fine_step = max(1, dof // 4)
        # The coarse scan ran forwards, so its best frame is near the forward peak; the
        # backward peak lies up to `max_backlash` below it.
        span = (4 * dof + max_backlash) // fine_step * fine_step
        self._begin("backlash", len(coarse) + 2 * BACKLASH_ROUNDS * (span // fine_step + 1))
        try:
            samples = await self._sweep(coarse, motion)
            tile = strongest_tile(samples)
            best = max(samples, key=lambda s: float(s.tiles.ravel()[tile]))
            top = min(best.position + 2 * dof, self._axis.max_position)
            up = self._positions(top - span, top, fine_step)
            shifts = []
            for _ in range(BACKLASH_ROUNDS):
                forward = self._values(await self._sweep(up, motion), tile)
                backward = self._values(await self._sweep(up[::-1], motion), tile)[::-1]
                shifts.append(curve_shift(up, forward, backward, max_backlash + dof))
            backlash = sum(shifts) / len(shifts)
            self.backlash = BacklashResult(
                backlash=round(backlash, 1),
                spread=round(max(shifts) - min(shifts), 1),
                suggested_takeup=math.ceil(2 * backlash) + max(1, dof),
            )
            return self.backlash
        finally:
            self._end()

    # -- helpers ------------------------------------------------------------------------------

    def _positions(self, low: int, high: int, step: int) -> list[int]:
        low = max(low, self._axis.min_position)
        high = min(high, self._axis.max_position)
        return list(range(low, high + 1, step))

    async def _sweep(self, positions: list[int], motion: Motion) -> list[Sample]:
        """Visit `positions` in order, reading a live-view frame at each."""
        if len(positions) < 3:
            raise ValueError("a sweep needs at least three positions")
        direction = 1 if positions[-1] > positions[0] else -1
        await self._approach(positions[0], direction)
        samples = []
        for position in positions:
            self._check_stop()
            if self._axis.state.position != position:
                await self._axis.move_to(position, motion.speed, motion.accel)
            await asyncio.sleep(motion.settle_s)
            frame = await self._camera.preview()
            tiles = await asyncio.to_thread(tile_sharpness, frame)
            samples.append(Sample(position, tiles))
            self.done += 1
            self._on_change()
        return samples

    @staticmethod
    def _values(samples: list[Sample], tile: int) -> list[float]:
        return [float(s.tiles.ravel()[tile]) for s in samples]

    def _begin(self, task: str, total: int) -> None:
        self.task, self.done, self.total = task, 0, total
        self._on_change()

    def _end(self) -> None:
        self.task = None
        self._on_change()
