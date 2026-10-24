"""The 3D scan module: its own Arduino Nano driving the yaw and tilt 28BYJ-48s, reading the tilt
switch and the hall sensor (docs/protocol-module.md), reached through a Link.

Angles are in degrees. Tilt 0 is level and + turns the insect's back towards the camera; the
switch trips past +90, at the calibrated `tilt_switch_deg`. Yaw is unlimited, and 0 is where
the magnet in the head passes over the hall sensor. The controller counts half-steps: tilt
counts up away from the switch (towards the lens side), yaw up in the direction homing turns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from ..config import ModuleConfig
from ..log import ActivityLog
from .base import AxisError, MotionInterrupted, motion_time
from .link import DeviceError, Link, LinkError, Transport
from .ports import AUTO
from .protocol import Event

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
STATUS_INTERVAL_S = 0.5
YAW_SWEEP_MAX = 5376  # the most half-steps the controller's yaw homing sweeps
HALL_STEP = 4  # hall changes smaller than this (noise) don't update the pushed state
RETRY_INTERVAL_S = 2.0

Rotary = Literal["tilt", "yaw"]

_ERRORS = {
    "BUSY": "The scan module is busy.",
    "NOT_HOMED": "Home the scan module first.",
    "LIMIT": "That tilt is outside the safe range.",
    "ENDSTOP": "The tilt switch was hit unexpectedly. Home tilt again.",
    "PRESSED": "The tilt switch is pressed. Jog tilt away from it (down) first.",
    "NO_SWITCH": "Tilt homing did not find the switch. Check the switch and its wiring.",
    "SWITCH_EARLY": "Tilt homing met the switch earlier than expected (noise on its wire, or "
    "the switch moved). Home tilt again; if it repeats, check the switch and its wiring.",
    "SWITCH_STUCK": "The tilt switch stayed pressed after backing off. Check the switch.",
    "NO_MAGNET": "Yaw homing found no magnet. Check the hall sensor and the magnet in the head.",
    "LINK": "The module stopped its motor because it lost contact with the Pi.",
}


@dataclass(frozen=True)
class Geometry:
    """Converts between the controller's half-steps and degrees, from the calibration."""

    half_steps_per_turn: float
    tilt_switch_deg: float  # where the switch trips, i.e. tilt half-step 0
    tilt_min_deg: float  # the safe range, already narrowed if tilt isn't calibrated yet
    tilt_max_deg: float
    # How far above tilt_max_deg the controller may go: arrivals at the top come from above,
    # by the take-up. Never closer to the switch than `switch_clearance_deg`.
    takeup_deg: float = 0.0
    switch_clearance_deg: float = 0.0

    @property
    def per_deg(self) -> float:
        return self.half_steps_per_turn / 360.0

    def tilt_deg(self, steps: int) -> float:
        return self.tilt_switch_deg - steps / self.per_deg

    def tilt_steps(self, deg: float) -> int:
        return round((self.tilt_switch_deg - deg) * self.per_deg)

    def yaw_deg(self, steps: int) -> float:
        return steps / self.per_deg

    def yaw_steps(self, deg: float) -> int:
        return round(deg * self.per_deg)

    @property
    def tilt_top_deg(self) -> float:
        """The highest tilt the controller may reach: room for the take-up above the safe
        range, but clear of the switch."""
        return min(
            self.tilt_max_deg + self.takeup_deg, self.tilt_switch_deg - self.switch_clearance_deg
        )

    def tilt_limits(self) -> tuple[int, int]:
        """The controller's tilt soft limits, in half-steps (low = the top angle)."""
        return max(self.tilt_steps(self.tilt_top_deg), 0), self.tilt_steps(self.tilt_min_deg)


@dataclass(frozen=True)
class ModuleState:
    connected: bool = False
    firmware: str | None = None
    problem: str | None = None  # why it is offline or unusable, for the user
    moving: Rotary | None = None
    switch: bool = False  # the tilt switch is pressed
    hall: int | None = None  # the hall sensor's raw reading (0-1023)
    tilt_homed: bool = False
    yaw_homed: bool = False
    tilt_steps: int = 0
    yaw_steps: int = 0


@dataclass(frozen=True)
class YawHome:
    """What yaw homing measured: where the magnet was in the previous frame, how strongly and
    how widely it showed."""

    previous_position: int
    deviation: int
    width: int


class ScanModule:
    def __init__(
        self,
        config: ModuleConfig,
        open_transport: Callable[[], Transport],
        geometry: Callable[[], Geometry],
        log: ActivityLog,
        on_change: Callable[[], None],
    ) -> None:
        self._config = config
        self._open_transport = open_transport
        self._geometry = geometry
        self._log = log
        self._on_change = on_change
        self._state = ModuleState(problem="Connecting to the scan module…")
        self._link: Link | None = None
        self._connections = 0
        self._connected_since: float | None = None
        self._status_ms: float | None = None  # smoothed STATUS round trip
        self._local_motion: Rotary | None = None  # a motion request of ours is outstanding

    @property
    def state(self) -> ModuleState:
        return self._state

    @property
    def geometry(self) -> Geometry:
        return self._geometry()

    def tilt_deg(self) -> float:
        return self.geometry.tilt_deg(self._state.tilt_steps)

    def yaw_deg(self) -> float:
        return self.geometry.yaw_deg(self._state.yaw_steps)

    # -- connection ---------------------------------------------------------------------------

    async def run(self) -> None:
        last_problem: str | None = None
        while True:
            try:
                await self._session()
                problem = "Lost connection to the scan module."
            except (LinkError, OSError, AxisError) as exc:
                problem = self._describe_failure(exc)
            except Exception as exc:  # the supervisor must outlive any bug: reconnect instead
                logger.exception("scan module session failed")
                problem = f"Scan module error ({exc}). Reconnecting."

            # Unplugged is a normal state for the module, so only a lost connection is a warning.
            if self._state.connected:
                self._log.warning(problem)
            elif problem != last_problem:
                logger.info(problem)
            last_problem = problem
            self._update(connected=False, moving=None, problem=problem)
            await asyncio.sleep(RETRY_INTERVAL_S)

    async def _session(self) -> None:
        link, ready = await Link.open(self._open_transport, self._on_event, name="module")
        try:
            if ready.data.get("role") != "module":
                raise AxisError(
                    "That port is the rail's controller, not the scan module's. Set the "
                    'module\'s port to "auto" in config.toml.'
                )
            if ready.data.get("proto") != str(PROTOCOL_VERSION):
                raise AxisError(
                    f"The scan module firmware speaks protocol {ready.data.get('proto')}, but "
                    f"this app needs {PROTOCOL_VERSION}. Flash the firmware that ships with "
                    "this version."
                )
            self._link = link
            await self.apply_limits()
            self._apply_status(await link.request("STATUS"), firmware=ready.data.get("fw"))
            self._connections += 1
            self._connected_since = time.time()
            self._log.info(f"Scan module connected (firmware {self._state.firmware}).")
            while True:
                await asyncio.sleep(STATUS_INTERVAL_S)
                sent = time.perf_counter()
                status = await link.request("STATUS")
                ms = (time.perf_counter() - sent) * 1000
                self._status_ms = (
                    ms if self._status_ms is None else 0.8 * self._status_ms + 0.2 * ms
                )
                self._apply_status(status)
        finally:
            self._link = None
            self._connected_since = None
            await link.close()

    def _describe_failure(self, exc: Exception) -> str:
        if isinstance(exc, AxisError):
            return str(exc)
        if isinstance(exc, OSError):
            if self._config.port == AUTO:
                return "Scan module not connected. Plug in its Nano to use the 3D workspace."
            return f"Scan module not found on {self._config.port}. Is its Nano plugged in?"
        return f"Lost connection to the scan module ({exc})."

    def _on_event(self, event: Event) -> None:
        if event.name == "POS":
            position = int(event.data["pos"])
            if event.data.get("axis") == "tilt":
                self._update(tilt_steps=position)
            elif event.data.get("axis") == "yaw":
                self._update(yaw_steps=position)
        elif event.name == "SWITCH":
            self._update(switch=event.data.get("pressed") == "1")
        elif event.name == "READY" and self._link is not None:
            self._link.abort("the module's controller restarted")

    def _apply_status(self, data: dict[str, str], firmware: str | None = None) -> None:
        reported = data["moving"]
        # A STATUS answered just before our motion request was sent still says idle.
        moving = self._local_motion or (reported if reported in ("tilt", "yaw") else None)
        hall = int(data["hall"])
        if self._state.hall is not None and abs(hall - self._state.hall) < HALL_STEP:
            hall = self._state.hall  # sensor noise alone isn't worth a state push
        self._update(
            connected=True,
            firmware=firmware or self._state.firmware,
            problem=None,
            moving=moving,
            switch=data["switch"] == "1",
            hall=hall,
            tilt_homed=data["thomed"] == "1",
            yaw_homed=data["yhomed"] == "1",
            tilt_steps=int(data["tilt"]),
            yaw_steps=int(data["yaw"]),
        )

    def _update(self, **changes: object) -> None:
        new = replace(self._state, **changes)  # type: ignore[arg-type]
        if new != self._state:
            self._state = new
            self._on_change()

    # -- commands -----------------------------------------------------------------------------

    async def _request(
        self,
        command: str,
        *args: int | str,
        timeout: float = 1.0,
        motion: Rotary | None = None,
    ) -> dict[str, str]:
        """Send a request; for a motion of axis `motion`, keep its position from the reply,
        also when the motion ended early."""
        link = self._link
        if link is None:
            raise AxisError(self._state.problem or "The scan module is not connected.")
        try:
            data = await link.request(command, *args, timeout=timeout, motion=motion is not None)
        except DeviceError as exc:
            if motion is not None and "pos" in exc.data:
                self._update(**{f"{motion}_steps": int(exc.data["pos"])})
            if exc.code == "ENDSTOP":
                self._update(tilt_homed=False)  # as the controller just did
            if exc.code == "STOPPED":
                raise MotionInterrupted("Stopped.") from None
            raise AxisError(_ERRORS.get(exc.code, f"Scan module error {exc.code}.")) from None
        except LinkError as exc:
            raise AxisError(f"Lost connection to the scan module ({exc}).") from None
        if motion is not None and "pos" in data:
            self._update(**{f"{motion}_steps": int(data["pos"])})
        return data

    async def _motion(
        self, axis: Rotary, command: str, *args: int | str, timeout: float
    ) -> dict[str, str]:
        self._local_motion = axis
        self._update(moving=axis)
        try:
            return await self._request(command, *args, timeout=timeout, motion=axis)
        finally:
            self._local_motion = None
            self._update(moving=None)

    def diagnostics(self) -> dict[str, object]:
        link = self._link
        return {
            "port": (link.port if link is not None else None) or self._config.port,
            "protocol": PROTOCOL_VERSION,
            "connections": self._connections,
            "connected_since": self._connected_since,
            "status_ms": None if self._status_ms is None else round(self._status_ms, 1),
        }

    async def apply_limits(self) -> None:
        """Send the tilt soft limits for the current calibration (after it changes, too)."""
        if self._link is not None:
            low, high = self.geometry.tilt_limits()
            await self._request("LIMITS", "TILT", low, high)

    async def home_tilt(self, check_stop: Callable[[], None]) -> float:
        """Find the tilt switch, then park clear of it (unless stopped in between). Returns
        the switch's hysteresis in degrees (how far past its trip point it releases)."""
        c, per_deg = self._config, self.geometry.per_deg
        fast = _rate(c.tilt_homing_speed_deg_s * per_deg)
        slow = _rate(c.tilt_homing_probe_speed_deg_s * per_deg)
        accel = _accel(c.accel_deg_s2 * per_deg)
        clearance = round(c.tilt_homing_clearance_deg * per_deg)
        release_max = round(c.tilt_homing_release_max_deg * per_deg)
        max_steps = round(c.tilt_homing_max_deg * per_deg)
        # Starting on the pressed switch it backs off first, then seeks, backs off and probes.
        timeout = (
            motion_time(max_steps, fast, accel)
            + 2 * motion_time(release_max, fast, accel)
            + motion_time(release_max + 2 * clearance, slow, accel)
        )
        reply = await self._motion(
            "tilt",
            "HOME",
            "TILT",
            fast,
            slow,
            clearance,
            max_steps,
            release_max,
            accel,
            timeout=timeout,
        )
        self._update(tilt_homed=True)
        release = int(reply.get("release", 0))
        # Park where the switch is open again, so it rests released and armed, and inside
        # the soft limits (as the rail parks at whichever is further).
        check_stop()
        park = max(release + clearance, self.geometry.tilt_limits()[0])
        await self.move("tilt", park, fast, accel)
        return release / per_deg

    async def home_yaw(self) -> YawHome:
        """Find the magnet's field peak, approached from one side: that is yaw 0."""
        c, per_deg = self._config, self.geometry.per_deg
        speed = _rate(c.yaw_homing_speed_deg_s * per_deg)
        accel = _accel(c.accel_deg_s2 * per_deg)
        sweep = min(round(c.yaw_homing_turns * self.geometry.half_steps_per_turn), YAW_SWEEP_MAX)
        takeup = round(c.takeup_deg * per_deg)
        timeout = motion_time(sweep + 3 * takeup, speed, accel) + motion_time(sweep, speed, accel)
        reply = await self._motion(
            "yaw", "HOME", "YAW", speed, accel, sweep, takeup, timeout=timeout
        )
        self._update(yaw_homed=True)
        return YawHome(
            previous_position=int(reply.get("from", 0)),
            deviation=int(reply.get("dev", 0)),
            width=int(reply.get("width", 0)),
        )

    async def move(self, axis: Rotary, target: int, speed: float, accel: float) -> int:
        """Absolute move in half-steps. The axis must be homed."""
        state = self._state
        if not (state.tilt_homed if axis == "tilt" else state.yaw_homed):
            raise AxisError(f"Home {axis} first.")
        if axis == "tilt":
            low, high = self.geometry.tilt_limits()
            if not low <= target <= high:
                raise AxisError(_ERRORS["LIMIT"])
        current = state.tilt_steps if axis == "tilt" else state.yaw_steps
        rate, ramp = _rate(speed), _accel(accel)
        await self._motion(
            axis,
            "MOVE",
            axis.upper(),
            target,
            rate,
            ramp,
            timeout=motion_time(abs(target - current), rate, ramp),
        )
        return self._state.tilt_steps if axis == "tilt" else self._state.yaw_steps

    async def jog(self, axis: Rotary, delta: int, speed: float, accel: float) -> int:
        """Relative move in half-steps; allowed before homing (to free a stuck axis)."""
        state = self._state
        if axis == "tilt" and state.tilt_homed:
            low, high = self.geometry.tilt_limits()
            if not low <= state.tilt_steps + delta <= high:
                raise AxisError(_ERRORS["LIMIT"])
        rate, ramp = _rate(speed), _accel(accel)
        await self._motion(
            axis,
            "JOG",
            axis.upper(),
            delta,
            rate,
            ramp,
            timeout=motion_time(abs(delta), rate, ramp),
        )
        return self._state.tilt_steps if axis == "tilt" else self._state.yaw_steps

    async def read_hall(self) -> int:
        reading = int((await self._request("HALL"))["hall"])
        self._update(hall=reading)
        return reading

    async def stop(self) -> None:
        # Always sent: the controller ignores it when idle, and the local `moving` flag can
        # briefly lag a motion that has just been started.
        if self._link is not None:
            await self._request("STOP")


def _rate(half_steps_per_s: float) -> int:
    return min(max(round(half_steps_per_s), 1), 1000)


def _accel(half_steps_per_s2: float) -> int:
    return min(max(round(half_steps_per_s2), 1), 4000)
