"""The orchestrator: owns the axis, camera and stack, and runs one operation at a time.

Every command arrives here. Commands are checked up front (raising OperationError with a
reason for the user); long ones then run as a background operation, whose progress and
outcome reach the UI through state updates and the activity log.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import asdict
from typing import Any, Literal

from . import __version__
from .camera.base import Camera, CameraError
from .camera.liveview import LiveView
from .config import Config
from .control import ControlLease
from .log import ActivityLog
from .motion.base import Axis, AxisError, MotionInterrupted
from .settings import Settings, SettingsStore
from .stack.plan import PlanError, StackPlan, estimate_seconds, plan_count, plan_range
from .stack.runner import StackRun

log = logging.getLogger(__name__)

Activity = Literal["idle", "homing", "moving", "previewing", "stacking", "capturing"]
Point = Literal["start", "end"]

MAX_JOG_MM = 5.0
DEFAULT_CAPTURE_S = 1.5
IDLE_CHECK_S = 1.0


class OperationError(Exception):
    """A command was refused. The message is written for the user."""


class Machine:
    def __init__(
        self,
        config: Config,
        axis: Axis,
        camera: Camera,
        store: SettingsStore,
        activity_log: ActivityLog,
    ) -> None:
        self.config = config
        self.axis = axis
        self.camera = camera
        self.log = activity_log
        self._store = store
        self.settings = store.load()
        self.activity: Activity = "idle"
        self.stack: StackRun | None = None
        self.control = ControlLease(self.changed)
        self.live_view = LiveView(
            camera, config.camera.liveview_max_fps, paused=lambda: self.activity == "stacking"
        )
        self._listeners: list[Callable[[], None]] = []
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._full_hold = True
        self._last_active = time.monotonic()
        self._motor_lock = asyncio.Lock()

    # -- lifecycle and state ------------------------------------------------------------------

    async def run(self) -> None:
        motion = self.settings.motion
        await self.axis.set_current(motion.run_current_ma, motion.run_current_ma)
        async with asyncio.TaskGroup() as group:
            group.create_task(self.axis.run())
            group.create_task(self.camera.run())
            group.create_task(self.live_view.run())
            group.create_task(self._idle_current_loop())

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    @property
    def busy(self) -> bool:
        return self.activity != "idle"

    def snapshot(self) -> dict[str, Any]:
        camera = self.camera.state
        return {
            "version": __version__,
            "activity": self.activity,
            "rail": {
                **asdict(self.axis.state),
                "steps_per_mm": self.axis.steps_per_mm,
                "min": self.axis.min_position,
                "max": self.axis.max_position,
            },
            "camera": asdict(camera),
            "live_view": {
                "available": camera.connected and camera.live_view,
                "paused": self.activity == "stacking",
            },
            "settings": self.settings.model_dump(),
            "plan": self._plan_summary(),
            "stack": self.stack.snapshot() if self.stack else None,
        }

    # -- units --------------------------------------------------------------------------------

    def _steps(self, mm: float) -> int:
        return round(mm * self.axis.steps_per_mm)

    def _profile(self, speed_mm_s: float) -> tuple[float, float]:
        spm = self.axis.steps_per_mm
        return speed_mm_s * spm, self.settings.motion.accel_mm_s2 * spm

    # -- commands -----------------------------------------------------------------------------

    def home(self) -> None:
        self._require_rail()
        self._start("homing", self._home())

    def jog(self, delta: int) -> None:
        self._require_rail()
        if abs(delta) > self._steps(MAX_JOG_MM):
            raise OperationError(f"Jogs are limited to {MAX_JOG_MM:g} mm at a time.")
        self._start("moving", self._jog(delta))

    def move_to(self, position: int) -> None:
        self._require_homed()
        self._require_in_travel(position)
        self._start("moving", self._go(position))

    def go_to(self, point: Point) -> None:
        self._require_homed()
        position = getattr(self.settings.stack, point)
        if position is None:
            raise OperationError(f"Set the {point} point first.")
        self._start("moving", self._go(position))

    def set_point(self, point: Point, position: int | None = None) -> None:
        self._require_homed()
        if position is None:
            position = self.axis.state.position
        self._require_in_travel(position)
        self._save(self.settings.merged({"stack": {point: position}}))

    def clear_point(self, point: Point) -> None:
        self._save(self.settings.merged({"stack": {point: None}}))

    def preview_range(self) -> None:
        self._require_homed()
        plan = self._plan()
        self._start("previewing", self._sweep(plan))

    def start_stack(self) -> None:
        self._require_homed()
        plan = self._plan()
        if not self.camera.state.connected:
            raise OperationError(self.camera.state.problem or "The camera is not connected.")
        speed, accel = self._profile(self.settings.motion.stack_speed_mm_s)
        self.stack = StackRun(
            plan,
            axis=self.axis,
            camera=self.camera,
            approach=self._approach,
            speed=speed,
            accel=accel,
            settle_s=self.settings.stack.settle_s,
            log=self.log,
            on_change=self.changed,
            record_dir=self.config.data_dir / "stacks",
        )
        self._start("stacking", self._run_stack(self.stack))

    def pause_stack(self) -> None:
        self._require_stack().pause()

    def resume_stack(self) -> None:
        self._require_stack().resume()

    async def stop(self) -> None:
        if self.activity == "stacking" and self.stack is not None:
            await self.stack.stop()
        elif self.busy:
            self._stop_requested = True
            with contextlib.suppress(AxisError):
                await self.axis.stop()

    def capture_test(self) -> None:
        if not self.camera.state.connected:
            raise OperationError(self.camera.state.problem or "The camera is not connected.")
        self._start("capturing", self._capture_test())

    async def set_motors(self, enabled: bool) -> None:
        self._require_rail()
        self._require_idle()
        async with self._motor_lock:
            try:
                if enabled:
                    await self.axis.enable()
                else:
                    await self.axis.disable()
                    self.log.info("Motor off. Home the rail before the next move.")
            except AxisError as exc:
                raise OperationError(str(exc)) from None
        self._last_active = time.monotonic()

    async def update_settings(self, patch: dict[str, dict[str, Any]]) -> None:
        try:
            new = self.settings.merged(patch)
        except ValueError as exc:
            raise OperationError(f"Invalid settings: {exc}") from None
        old = self.settings.motion
        currents_changed = (new.motion.run_current_ma, new.motion.hold_current_ma) != (
            old.run_current_ma,
            old.hold_current_ma,
        )
        if currents_changed:
            self._require_idle()
            async with self._motor_lock:
                hold = new.motion.run_current_ma if self._full_hold else new.motion.hold_current_ma
                try:
                    await self.axis.set_current(new.motion.run_current_ma, hold)
                except AxisError as exc:
                    raise OperationError(str(exc)) from None
        self._save(new)

    # -- operations ---------------------------------------------------------------------------

    def _start(self, activity: Activity, operation: Coroutine[Any, Any, None]) -> None:
        if self.busy:
            operation.close()
            raise OperationError(f"Busy ({self.activity}). Stop first or wait for it to finish.")
        self.activity = activity
        self._stop_requested = False
        self._task = asyncio.create_task(self._operate(operation))
        self.changed()

    async def _operate(self, operation: Coroutine[Any, Any, None]) -> None:
        try:
            await operation
        except MotionInterrupted:
            self.log.info("Stopped.")
        except (AxisError, CameraError, PlanError) as exc:
            self.log.error(str(exc))
        except Exception as exc:
            log.exception("operation failed")
            self.log.error(f"Unexpected error: {exc}")
        finally:
            self.activity = "idle"
            self._task = None
            self._last_active = time.monotonic()
            self.changed()

    async def _prepare_motion(self) -> None:
        """Energise the motor at full current: no current change while positioning."""
        async with self._motor_lock:
            if not self.axis.state.enabled:
                await self.axis.enable()
            if not self._full_hold:
                run = self.settings.motion.run_current_ma
                await self.axis.set_current(run, run)
                self._full_hold = True

    async def _idle_current_loop(self) -> None:
        while True:
            await asyncio.sleep(IDLE_CHECK_S)
            motion = self.settings.motion
            idle_for = time.monotonic() - self._last_active
            if not self._full_hold or self.busy or idle_for < motion.idle_hold_after_s:
                continue
            async with self._motor_lock:
                if self.busy or not self.axis.state.connected:
                    continue
                try:
                    await self.axis.set_current(motion.run_current_ma, motion.hold_current_ma)
                    self._full_hold = False
                except AxisError:
                    continue

    def _check_stop(self) -> None:
        if self._stop_requested:
            raise MotionInterrupted("Stopped.")

    async def _home(self) -> None:
        await self._prepare_motion()
        self.log.info("Homing…")
        await self.axis.home()
        self.log.info("Homed.")

    async def _jog(self, delta: int) -> None:
        await self._prepare_motion()
        await self.axis.jog(delta, *self._profile(self.settings.motion.travel_speed_mm_s))

    async def _go(self, position: int) -> None:
        await self._prepare_motion()
        await self._approach(position, self._stack_direction())

    async def _approach(self, target: int, direction: int) -> None:
        """Arrive at `target` moving in `direction`, so backlash is taken up the same way
        as during a stack."""
        speed, accel = self._profile(self.settings.motion.travel_speed_mm_s)
        backlash = self._steps(self.settings.motion.backlash_mm)
        ahead = (target - self.axis.state.position) * direction
        if ahead < backlash:
            pre = target - direction * backlash
            pre = min(max(pre, self.axis.min_position), self.axis.max_position)
            if pre != target:
                await self.axis.move_to(pre, speed, accel)
                self._check_stop()
        await self.axis.move_to(target, speed, accel)

    async def _sweep(self, plan: StackPlan) -> None:
        await self._prepare_motion()
        speed, accel = self._profile(self.settings.motion.travel_speed_mm_s)
        self.log.info("Previewing the range. Press Stop to end.")
        await self._approach(plan.start, plan.direction)
        while True:
            for target in (plan.end, plan.start):
                self._check_stop()
                await self.axis.move_to(target, speed, accel)

    async def _run_stack(self, run: StackRun) -> None:
        await self._prepare_motion()
        await run.run()

    async def _capture_test(self) -> None:
        capture = await self.camera.capture()
        self.log.info(f"Test shot saved as {capture.name} ({capture.duration_s:.1f} s).")

    # -- planning -----------------------------------------------------------------------------

    def _stack_direction(self) -> int:
        stack = self.settings.stack
        if stack.mode == "range" and stack.start is not None and stack.end is not None:
            return 1 if stack.end >= stack.start else -1
        return stack.direction

    def _planned(self) -> StackPlan:
        stack = self.settings.stack
        low, high = self.axis.min_position, self.axis.max_position
        if stack.start is None:
            raise PlanError("Set the start point first.")
        if stack.mode == "range":
            if stack.end is None:
                raise PlanError("Set the end point first.")
            return plan_range(stack.start, stack.end, stack.step, low, high)
        return plan_count(stack.start, stack.step, stack.count, stack.direction, low, high)

    def _plan(self) -> StackPlan:
        try:
            return self._planned()
        except PlanError as exc:
            raise OperationError(str(exc)) from None

    def _plan_summary(self) -> dict[str, Any]:
        try:
            plan = self._planned()
        except PlanError as exc:
            return {"error": str(exc)}
        speed, accel = self._profile(self.settings.motion.stack_speed_mm_s)
        last = self.stack.shots if self.stack else []
        capture_s = sum(s.capture_s for s in last) / len(last) if last else DEFAULT_CAPTURE_S
        seconds = estimate_seconds(plan, speed, accel, self.settings.stack.settle_s, capture_s)
        return {
            "error": None,
            "count": plan.count,
            "start": plan.start,
            "end": plan.end,
            "direction": plan.direction,
            "estimate_s": round(seconds),
        }

    # -- guards -------------------------------------------------------------------------------

    def _require_rail(self) -> None:
        state = self.axis.state
        if not state.connected:
            raise OperationError(state.problem or "The rail controller is not connected.")
        if not state.driver_ok:
            raise OperationError(state.problem or "The stepper driver is not responding.")

    def _require_homed(self) -> None:
        self._require_rail()
        if not self.axis.state.homed:
            raise OperationError("Home the rail first.")

    def _require_idle(self) -> None:
        if self.busy:
            raise OperationError(f"Busy ({self.activity}). Stop first or wait for it to finish.")

    def _require_in_travel(self, position: int) -> None:
        if not self.axis.min_position <= position <= self.axis.max_position:
            raise OperationError("That position is outside the rail's travel.")

    def _require_stack(self) -> StackRun:
        if self.stack is None or not self.stack.active:
            raise OperationError("No stack is running.")
        return self.stack

    def _save(self, settings: Settings) -> None:
        self.settings = settings
        self._store.save(settings)
        self.changed()


def build_machine(config: Config, *, sim: bool = False, sim_speedup: float = 1.0) -> Machine:
    """Wire up the real hardware, or the simulator for `--sim`, tests and screenshots."""
    from .motion.rail import RailAxis

    activity_log = ActivityLog()
    store = SettingsStore(config.data_dir / "settings.json")
    machine: Machine

    def changed() -> None:
        machine.changed()

    camera: Camera
    if sim:
        from .sim.camera import SimCamera
        from .sim.firmware import SimRail

        sim_rail = SimRail(steps_per_mm=config.rail.steps_per_mm, speedup=sim_speedup)
        axis = RailAxis(config.rail, sim_rail.open, activity_log, changed)
        camera = SimCamera(lambda: axis.state.position / axis.steps_per_mm, speedup=sim_speedup)
    else:
        from .camera.gphoto import GPhotoCamera
        from .motion.link import SerialTransport

        port = config.rail.port
        axis = RailAxis(config.rail, lambda: SerialTransport(port), activity_log, changed)
        camera = GPhotoCamera(config.camera, activity_log, changed)
    machine = Machine(config, axis, camera, store, activity_log)
    return machine
