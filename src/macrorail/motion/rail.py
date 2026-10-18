"""The macro rail: an Arduino Nano + TMC2209 running `firmware/`, reached through a Link."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace

from ..config import RailConfig
from ..log import ActivityLog
from .base import AxisError, AxisState, MotionInterrupted
from .link import DeviceError, Link, LinkError, Transport
from .protocol import PROTOCOL_VERSION, Event

STATUS_INTERVAL_S = 0.5
RETRY_INTERVAL_S = 2.0

_ERRORS = {
    "BUSY": "The rail is busy.",
    "DISABLED": "The motor is off.",
    "NOT_HOMED": "Home the rail first.",
    "LIMIT": "That position is outside the rail's travel.",
    "DRIVER": "The stepper driver is not responding. Check the 12 V supply and its wiring.",
    "ENDSTOP": "The home switch was hit unexpectedly. Home the rail again.",
    "NO_SWITCH": "Homing did not find the switch. Check the switch and its wiring.",
    "SWITCH_STUCK": "The home switch stayed pressed after backing off. Check the switch.",
    "LINK": "The controller stopped the motor because it lost contact with the Pi.",
}

_FAULTS = {
    "driver_lost": "The stepper driver stopped responding. Check the 12 V supply.",
    "driver_reset": "The stepper driver lost power and restarted. Home the rail again.",
    "overtemp": "The stepper driver overheated, so the motor was switched off.",
    "short": "The stepper driver detected a short circuit, so the motor was switched off.",
}


class RailAxis:
    def __init__(
        self,
        config: RailConfig,
        open_transport: Callable[[], Transport],
        log: ActivityLog,
        on_change: Callable[[], None],
    ) -> None:
        self._config = config
        self._open_transport = open_transport
        self._log = log
        self._on_change = on_change
        self.steps_per_mm = config.steps_per_mm
        self.min_position = round(config.min_mm * config.steps_per_mm)
        self.max_position = round(config.travel_mm * config.steps_per_mm)
        self._state = AxisState(problem="Connecting to the rail controller…")
        self._link: Link | None = None
        self._current = (600, 200)

    @property
    def state(self) -> AxisState:
        return self._state

    # -- connection ---------------------------------------------------------------------------

    async def run(self) -> None:
        last_problem: str | None = None
        while True:
            try:
                await self._session()
                problem = "Lost connection to the rail controller."
            except (LinkError, OSError, AxisError) as exc:
                problem = self._describe_failure(exc)
            if self._state.connected or problem != last_problem:
                self._log.warning(problem)
            last_problem = problem
            self._update(connected=False, moving=False, problem=problem)
            await asyncio.sleep(RETRY_INTERVAL_S)

    async def _session(self) -> None:
        link, ready = await Link.open(self._open_transport, self._on_event)
        try:
            if ready.data.get("proto") != str(PROTOCOL_VERSION):
                raise AxisError(
                    f"The rail firmware speaks protocol {ready.data.get('proto')}, but this app "
                    f"needs {PROTOCOL_VERSION}. Flash the firmware that ships with this version."
                )
            await link.request("CURRENT", *self._current)
            await link.request("LIMITS", self.min_position, self.max_position)
            self._link = link
            self._apply_status(await link.request("STATUS"), firmware=ready.data.get("fw"))
            self._log.info(f"Rail controller connected (firmware {self._state.firmware}).")
            while True:
                await asyncio.sleep(STATUS_INTERVAL_S)
                self._apply_status(await link.request("STATUS"))
        finally:
            self._link = None
            await link.close()

    def _describe_failure(self, exc: Exception) -> str:
        if isinstance(exc, AxisError):
            return str(exc)
        if isinstance(exc, OSError):
            return f"Rail controller not found on {self._config.port}. Is the Nano plugged in?"
        return f"Lost connection to the rail controller ({exc})."

    def _on_event(self, event: Event) -> None:
        if event.name == "POS":
            self._update(position=int(event.data["pos"]))
        elif event.name == "FAULT":
            code = event.data.get("code", "")
            self._log.error(_FAULTS.get(code, f"Stepper driver fault: {code}."))
            if code == "driver_lost":
                self._update(enabled=False, homed=False, driver_ok=False, problem=_ERRORS["DRIVER"])
            else:
                self._update(enabled=False, homed=False)
        elif event.name == "READY" and self._link is not None:
            self._link.abort("the controller restarted")

    def _apply_status(self, data: dict[str, str], firmware: str | None = None) -> None:
        driver_ok = data["driver"] == "ok"
        self._update(
            connected=True,
            driver_ok=driver_ok,
            enabled=data["enabled"] == "1",
            homed=data["homed"] == "1",
            moving=data["moving"] == "1",
            endstop=data["endstop"] == "1",
            position=int(data["pos"]),
            firmware=firmware or self._state.firmware,
            problem=None if driver_ok else _ERRORS["DRIVER"],
        )

    def _update(self, **changes: object) -> None:
        new = replace(self._state, **changes)  # type: ignore[arg-type]
        if new != self._state:
            self._state = new
            self._on_change()

    # -- commands -----------------------------------------------------------------------------

    async def _request(self, command: str, *args: int, timeout: float = 1.0) -> dict[str, str]:
        link = self._link
        if link is None:
            raise AxisError(self._state.problem or "The rail controller is not connected.")
        try:
            data = await link.request(command, *args, timeout=timeout)
        except DeviceError as exc:
            if "pos" in exc.data:
                self._update(position=int(exc.data["pos"]))
            if exc.code in ("STOPPED", "HALTED"):
                raise MotionInterrupted("Stopped.") from None
            raise AxisError(_ERRORS.get(exc.code, f"Rail controller error {exc.code}.")) from None
        except LinkError as exc:
            raise AxisError(f"Lost connection to the rail controller ({exc}).") from None
        if "pos" in data:
            self._update(position=int(data["pos"]))
        return data

    async def _motion(self, command: str, *args: int, timeout: float) -> int:
        self._update(moving=True)
        try:
            await self._request(command, *args, timeout=timeout)
        finally:
            self._update(moving=False)
        return self._state.position

    async def set_current(self, run_ma: int, hold_ma: int) -> None:
        self._current = (run_ma, hold_ma)
        if self._link is not None:
            await self._request("CURRENT", run_ma, hold_ma)

    async def enable(self) -> None:
        await self._request("ENABLE")
        self._update(enabled=True)

    async def disable(self) -> None:
        await self._request("DISABLE")
        self._update(enabled=False, homed=False)

    async def home(self) -> None:
        c, spm = self._config, self.steps_per_mm
        fast = round(c.homing_speed_mm_s * spm)
        slow = round(c.homing_probe_speed_mm_s * spm)
        backoff = round(c.homing_backoff_mm * spm)
        accel = round(c.homing_accel_mm_s2 * spm)
        max_steps = self.max_position + round(20 * spm)
        timeout = _motion_time(max_steps, fast, accel) + _motion_time(3 * backoff, slow, accel)
        await self._motion("HOME", fast, slow, backoff, max_steps, accel, timeout=timeout)
        self._update(homed=True)
        await self.move_to(self.min_position, fast, accel)

    async def move_to(self, target: int, speed: float, accel: float) -> int:
        if not self._state.homed:
            raise AxisError(_ERRORS["NOT_HOMED"])
        if not self.min_position <= target <= self.max_position:
            raise AxisError(_ERRORS["LIMIT"])
        distance = abs(target - self._state.position)
        return await self._motion(
            "MOVE", target, round(speed), round(accel), timeout=_motion_time(distance, speed, accel)
        )

    async def jog(self, delta: int, speed: float, accel: float) -> int:
        if self._state.homed and not (
            self.min_position <= self._state.position + delta <= self.max_position
        ):
            raise AxisError(_ERRORS["LIMIT"])
        return await self._motion(
            "JOG", delta, round(speed), round(accel), timeout=_motion_time(abs(delta), speed, accel)
        )

    async def stop(self) -> None:
        if self._link is not None and self._state.moving:
            await self._request("STOP")

    async def halt(self) -> None:
        if self._link is not None and self._state.moving:
            await self._request("HALT")


def _motion_time(distance: float, speed: float, accel: float) -> float:
    """A generous upper bound for how long a move may take before the link is presumed dead."""
    return 3.0 + 1.5 * (distance / speed + speed / accel)
