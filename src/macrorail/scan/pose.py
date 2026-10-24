"""Moving the scan module to angles.

Every arrival ends turning the same way, so the gearboxes' backlash is taken up identically at
every pose, as the rail does before a stack: tilt arrives from above (its angle decreasing),
yaw arrives turning counter-clockwise.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import ModuleConfig
from ..log import ActivityLog
from ..motion.base import AxisError
from ..motion.module import Rotary, ScanModule


class Poser:
    def __init__(
        self,
        module: ScanModule,
        config: ModuleConfig,
        check_stop: Callable[[], None],
        log: ActivityLog,
    ) -> None:
        self._module = module
        self._config = config
        self._check_stop = check_stop
        self._log = log

    def tilt_range(self) -> tuple[float, float]:
        geometry = self._module.geometry
        return geometry.tilt_min_deg, geometry.tilt_max_deg

    async def home(self, axes: tuple[Rotary, ...]) -> None:
        """Home tilt before yaw: the cradle's position matters more for clearance."""
        if "tilt" in axes:
            self._check_stop()
            self._log.info("Homing tilt…")
            release = await self._module.home_tilt(self._check_stop)
            self._log.info(f"Tilt homed. Its switch releases {release:.1f}° past where it trips.")
        if "yaw" in axes:
            self._check_stop()
            self._log.info("Homing yaw…")
            found = await self._module.home_yaw()
            self._log.info(
                f"Yaw homed on the magnet (signal {found.deviation} above the background)."
            )

    async def measure_turn(self, turns: int) -> int:
        """Home yaw, turn `turns` turns (by the current calibration) and home again. Returns
        where the second homing found the magnet, counted from the first."""
        await self.home(("yaw",))
        turn = self._module.geometry.half_steps_per_turn
        # Stop a little short, so the second homing's sweep meets the magnet early on.
        self._check_stop()
        await self._module.move("yaw", round((turns - 0.1) * turn), *self._profile("yaw"))
        self._check_stop()
        return (await self._module.home_yaw()).previous_position

    async def jog(self, axis: Rotary, delta_deg: float) -> None:
        self._check_stop()
        geometry = self._module.geometry
        delta = round(delta_deg * geometry.per_deg)
        if axis == "tilt":
            delta = -delta  # the controller counts tilt up as the angle goes down
        await self._module.jog(axis, delta, *self._profile(axis))

    async def go(self, tilt: float | None = None, yaw: float | None = None) -> None:
        """Move to a pose: tilt first, then yaw. Either may be left where it is."""
        if tilt is not None:
            await self.tilt_to(tilt)
        if yaw is not None:
            await self.yaw_to(yaw)

    async def tilt_to(self, deg: float) -> None:
        low, high = self.tilt_range()
        if not low - 1e-6 <= deg <= high + 1e-6:
            raise AxisError(f"Tilt goes from {low:g}° to {high:g}°.")
        geometry = self._module.geometry
        target = geometry.tilt_steps(deg)
        takeup = round(self._config.takeup_deg * geometry.per_deg)
        # The soft limits leave room for the take-up above the safe range; only a switch
        # calibrated unusually low narrows it.
        top = geometry.tilt_limits()[0]
        await self._arrive("tilt", target, max(target - takeup, top))

    async def yaw_to(self, deg: float) -> None:
        """Turn to `deg` (any angle; the nearest equivalent turn is used)."""
        geometry = self._module.geometry
        current = self._module.state.yaw_steps
        turn = geometry.half_steps_per_turn
        wanted = (deg % 360.0) * geometry.per_deg
        # The equivalent of `deg` nearest the current position, so a short move stays short.
        target = round(wanted + turn * round((current - wanted) / turn))
        takeup = round(self._config.takeup_deg * geometry.per_deg)
        await self._arrive("yaw", target, target - takeup)

    async def _arrive(self, axis: Rotary, target: int, before: int) -> None:
        """Go to `target` counting up, by way of `before` unless the last stretch from here
        already counts up by at least the take-up."""
        state = self._module.state
        current = state.tilt_steps if axis == "tilt" else state.yaw_steps
        profile = self._profile(axis)
        if current > before and before != target:
            self._check_stop()
            await self._module.move(axis, before, *profile)
        self._check_stop()
        await self._module.move(axis, target, *profile)

    def _profile(self, axis: Rotary) -> tuple[float, float]:
        per_deg = self._module.geometry.per_deg
        speed = self._config.tilt_speed_deg_s if axis == "tilt" else self._config.yaw_speed_deg_s
        return speed * per_deg, self._config.accel_deg_s2 * per_deg
