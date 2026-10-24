"""The orchestrator: owns the axis, camera and stack, and runs one operation at a time.

Every command arrives here. Commands are checked up front (raising OperationError with a
reason for the user); long ones then run as a background operation, whose progress and
outcome reach the UI through state updates and the activity log.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import asdict
from typing import Any, Literal

from . import __version__
from .camera.base import Camera, CameraError
from .camera.liveview import LiveView
from .config import Config
from .control import ControlLease
from .diagnostics import Diagnostics
from .focus.analysis import AnalysisError
from .focus.scan import FocusScanner
from .focus.scan import Motion as ScanMotion
from .log import ActivityLog
from .motion.base import Axis, AxisError, MotionInterrupted
from .motion.module import Geometry, Rotary, ScanModule
from .optics import Optics
from .review.store import ReviewError, ReviewStore
from .scan import calibrate
from .scan.measure import row_focus
from .scan.pose import Poser
from .settings import ModuleSettings, ModuleStore, Settings, SettingsStore
from .stack.plan import PlanError, StackPlan, estimate_seconds, plan_count, plan_range
from .stack.runner import StackRun

log = logging.getLogger(__name__)

Activity = Literal[
    "idle", "homing", "moving", "previewing", "stacking", "capturing", "scanning", "rotating"
]
Point = Literal["start", "end"]

MAX_JOG_MM = 5.0
MAX_ROTARY_JOG_DEG = 45.0
MAX_UNHOMED_TILT_JOG_DEG = 10.0  # before homing the module can't tell where the lens is
NEEDLE_SPAN_MM = 2.0  # focus sweep around the needle when levelling tilt
NEEDLE_TOP_ROWS = (0, 1)  # tile rows (of 6) that see the needle's top and bottom
NEEDLE_BOTTOM_ROWS = (4, 5)
SIM_BACKLASH_MM = 0.04  # a realistic lead-screw backlash for the simulator
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
        module: Callable[[Callable[[], Geometry]], ScanModule],
        module_store: ModuleStore,
    ) -> None:
        self.config = config
        self.axis = axis
        self.camera = camera
        self.log = activity_log
        self._store = store
        self.settings = store.load()
        self._module_store = module_store
        self.module_settings = module_store.load()  # the scan module's calibration
        self.activity: Activity = "idle"
        self.stack: StackRun | None = None
        self.control = ControlLease(self.changed)
        self.live_view = LiveView(
            camera, config.camera.liveview_max_fps, paused=lambda: self.activity == "stacking"
        )
        self.scanner = FocusScanner(axis, camera, self._approach, self._check_stop, self.changed)
        self.review = ReviewStore(config.data_dir / "stacks", activity_log, self.changed)
        self.diagnostics = Diagnostics(
            axis, camera, config.data_dir, self._driver_idle, self.changed
        )
        self.module = module(self._module_geometry)
        self.poser = Poser(self.module, config.module, self._check_stop, activity_log)
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
            group.create_task(self.module.run())
            group.create_task(self.camera.run())
            group.create_task(self.live_view.run())
            group.create_task(self._idle_current_loop())
            group.create_task(self.diagnostics.run())

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
            "module": self._module_snapshot(),
            "camera": asdict(camera),
            "live_view": {
                "available": camera.connected and camera.live_view,
                "paused": self.activity == "stacking",
            },
            "settings": self.settings.model_dump(),
            "optics": {
                "dof_um": round(self._optics().depth_of_field_um, 1),
                "suggested_step": self._optics().suggested_step(self.axis.steps_per_mm),
            },
            "scan": self.scanner.snapshot(),
            "review": self.review.snapshot(),
            "diagnostics": self.diagnostics.snapshot(),
            "plan": self._plan_summary(),
            "stack": self.stack.snapshot() if self.stack else None,
        }

    # -- units --------------------------------------------------------------------------------

    def _steps(self, mm: float) -> int:
        return round(mm * self.axis.steps_per_mm)

    def _profile(self, speed_mm_s: float) -> tuple[float, float]:
        spm = self.axis.steps_per_mm
        return speed_mm_s * spm, self.settings.motion.accel_mm_s2 * spm

    def _mm(self, steps: float) -> str:
        return f"{steps / self.axis.steps_per_mm:.3f}"

    def _optics(self) -> Optics:
        o = self.settings.optics
        return Optics(o.magnification, o.na, o.pixel_um)

    def _dof_steps(self) -> int:
        return max(1, round(self._optics().depth_of_field_um * self.axis.steps_per_mm / 1000))

    # -- commands -----------------------------------------------------------------------------

    def home(self) -> None:
        self._require_rail()
        self._start("homing", self._home())

    def jog(self, delta: int) -> None:
        self._require_rail()
        if abs(delta) > self._steps(MAX_JOG_MM):
            raise OperationError(f"Jogs are limited to {MAX_JOG_MM:g} mm at a time.")
        self._start("moving", self._jog(delta))

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

    def preview_range(self) -> None:
        self._require_homed()
        plan = self._plan()
        self._start("previewing", self._sweep(plan))

    def find_range(self) -> None:
        """Scan around the current position for where the subject comes into and out of focus."""
        self._require_homed()
        self._require_live_view()
        span = self._steps(self.settings.scan.span_mm)
        self._start("scanning", self._find_range(span, self._dof_steps()))

    def apply_range(self) -> None:
        result = self.scanner.range
        if result is None:
            raise OperationError("Run a range scan first.")
        low, high = self.axis.min_position, self.axis.max_position
        start, end = max(result.start, low), min(result.end, high)
        self._save(self.settings.merged({"stack": {"mode": "range", "start": start, "end": end}}))

    def measure_backlash(self) -> None:
        """Measure the lead screw's backlash from where a sharp detail peaks going each way."""
        self._require_homed()
        self._require_live_view()
        self._start("scanning", self._measure_backlash(self._dof_steps()))

    def apply_backlash(self) -> None:
        result = self.scanner.backlash
        if result is None:
            raise OperationError("Measure the backlash first.")
        # Rounded up to 0.01 mm, as the UI shows it.
        takeup_mm = min(
            2.0, math.ceil(result.suggested_takeup / self.axis.steps_per_mm * 100) / 100
        )
        self._save(self.settings.merged({"motion": {"backlash_mm": takeup_mm}}))

    def start_stack(self) -> None:
        self._require_idle()  # never replace a running stack, e.g. on a double tap
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
            store=self.review,
            name=self.settings.stack.name,
            download_previews=self.settings.camera.download_previews,
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
            # Both at once: the module's stop mustn't wait on a slow rail link.
            await asyncio.gather(_quietly(self.axis.stop()), _quietly(self.module.stop()))

    # -- the scan module ----------------------------------------------------------------------

    def home_module(self, axes: tuple[Rotary, ...]) -> None:
        self._require_module()
        if not axes:
            raise OperationError("Choose tilt, yaw or both.")
        self._start("rotating", self.poser.home(axes))

    def jog_module(self, axis: Rotary, delta_deg: float) -> None:
        self._require_module()
        homed = self.module.state.tilt_homed if axis == "tilt" else self.module.state.yaw_homed
        limit = MAX_ROTARY_JOG_DEG if homed or axis == "yaw" else MAX_UNHOMED_TILT_JOG_DEG
        if not 0 < abs(delta_deg) <= limit:
            raise OperationError(f"{axis.capitalize()} jogs are limited to {limit:g} degrees.")
        if axis == "tilt" and homed:
            low, high = self.poser.tilt_range()
            if not low - 1e-6 <= self.module.tilt_deg() + delta_deg <= high + 1e-6:
                raise OperationError(f"Tilt goes from {low:g} to {high:g} degrees.")
        self._start("rotating", self.poser.jog(axis, delta_deg))

    def pose(self, tilt: float | None, yaw: float | None) -> None:
        """Go to a pose. Each angle given needs its axis homed; tilt must be in range."""
        self._require_module()
        state = self.module.state
        if tilt is None and yaw is None:
            raise OperationError("Give a tilt, a yaw or both.")
        if tilt is not None:
            if not state.tilt_homed:
                raise OperationError("Home tilt first.")
            low, high = self.poser.tilt_range()
            if not low <= tilt <= high:
                raise OperationError(f"Tilt goes from {low:g} to {high:g} degrees.")
        if yaw is not None and not state.yaw_homed:
            raise OperationError("Home yaw first.")
        self._start("rotating", self.poser.go(tilt, yaw))

    def calibrate_yaw(self) -> None:
        """Measure the half-steps per yaw turn (needs nothing on the holder)."""
        self._require_module()
        self._start("rotating", self._calibrate_yaw())

    def calibrate_tilt(self) -> None:
        """Measure where the tilt switch trips against level, from a straight needle on the
        holder, in focus at the current rail position."""
        self._require_module()
        self._require_homed()
        self._require_live_view()
        state = self.module.state
        if not (state.tilt_homed and state.yaw_homed):
            raise OperationError("Home the scan module first.")
        self._start("scanning", self._calibrate_tilt())

    async def set_camera_setting(self, key: str, value: str) -> None:
        self._require_camera()
        self._require_idle()
        try:
            await self.camera.set_setting(key, value)
        except CameraError as exc:
            raise OperationError(str(exc)) from None

    async def refresh_camera_settings(self) -> None:
        self._require_camera()
        try:
            await self.camera.refresh_settings()
        except CameraError as exc:
            raise OperationError(str(exc)) from None

    async def build_preview(self, stack_id: str) -> None:
        try:
            await self.review.build_preview(stack_id)
        except ReviewError as exc:
            raise OperationError(str(exc)) from None

    def delete_stack(self, stack_id: str) -> None:
        if self.stack is not None and self.stack.active and self.stack.id == stack_id:
            raise OperationError("That stack is still running.")
        try:
            self.review.delete(stack_id)
        except ReviewError as exc:
            raise OperationError(str(exc)) from None

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
        except (AxisError, CameraError, PlanError, AnalysisError) as exc:
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

    def _driver_idle(self) -> bool:
        """Whether the driver may be queried now (the controller only answers while idle)."""
        rail = self.axis.state
        return not self.busy and rail.connected and rail.driver_ok

    def _check_stop(self) -> None:
        if self._stop_requested:
            raise MotionInterrupted("Stopped.")

    async def _home(self) -> None:
        await self._prepare_motion()
        self._check_stop()
        self.log.info("Homing…")
        await self.axis.home()

    async def _jog(self, delta: int) -> None:
        await self._prepare_motion()
        self._check_stop()
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
                self._check_stop()
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

    def _scan_motion(self) -> ScanMotion:
        speed, accel = self._profile(self.settings.motion.stack_speed_mm_s)
        return ScanMotion(speed, accel, self.settings.scan.settle_s)

    async def _find_range(self, span: int, step: int) -> None:
        await self._prepare_motion()
        self.log.info("Scanning for the subject's front and back…")
        center = self.axis.state.position
        try:
            result = await self.scanner.find_range(center, span, step, self._scan_motion())
        except AnalysisError:
            await self._approach(center, self._stack_direction())
            raise
        await self._approach(center, self._stack_direction())  # back to where the scan began
        self.log.info(
            f"Subject in focus from {self._mm(result.start)} to {self._mm(result.end)} mm."
        )
        if result.clipped:
            self.log.warning(
                "The subject was still in focus at the edge of the scan. Widen the scan span "
                "or start nearer the middle of the subject."
            )

    async def _measure_backlash(self, dof: int) -> None:
        await self._prepare_motion()
        self.log.info("Measuring backlash…")
        start = self.axis.state.position
        try:
            result = await self.scanner.measure_backlash(start, dof, self._scan_motion())
        except AnalysisError:
            await self._approach(start, self._stack_direction())
            raise
        await self._approach(start, self._stack_direction())  # back to where the scan began
        um = 1000 / self.axis.steps_per_mm
        self.log.info(
            f"Backlash is about {result.backlash * um:.0f} µm (repeatability "
            f"±{result.spread * um / 2:.0f} µm). Suggested take-up: "
            f"{result.suggested_takeup * um / 1000:.2f} mm."
        )

    async def _calibrate_yaw(self) -> None:
        self.log.info(
            f"Measuring a yaw turn: homing, turning {calibrate.YAW_TURNS} turns, homing again…"
        )
        previous = self.module_settings
        found = await self.poser.measure_turn(calibrate.YAW_TURNS)
        turn = calibrate.half_steps_per_turn(
            found, calibrate.YAW_TURNS, previous.half_steps_per_turn
        )
        await self._save_module(
            previous.model_copy(update={"half_steps_per_turn": turn, "yaw_calibrated": True})
        )
        # The second homing set yaw 0 on the magnet again, so poses need nothing redone.
        self.log.info(
            f"Yaw calibrated: {turn:.2f} half-steps per turn "
            f"(was {previous.half_steps_per_turn:.2f})."
        )

    async def _calibrate_tilt(self) -> None:
        await self._prepare_motion()
        self.log.info("Levelling tilt from the needle: four focus sweeps…")
        probe = calibrate.TILT_PROBE_DEG
        dof = self._dof_steps()
        span = self._steps(NEEDLE_SPAN_MM)
        center = self.axis.state.position
        rises: dict[float, list[float]] = {probe: [], -probe: []}
        for tilt in (probe, -probe):
            for yaw in (0.0, 180.0):
                await self.poser.go(tilt, yaw)
                samples = await self.scanner.sweep(
                    "tilt level", center, span, dof, self._scan_motion()
                )
                top = row_focus(samples, NEEDLE_TOP_ROWS)
                bottom = row_focus(samples, NEEDLE_BOTTOM_ROWS)
                rises[tilt].append(top - bottom)
                center = round((top + bottom) / 2)  # follow the needle if it is off the axis
        up, down = (sum(r) / len(r) for r in (rises[probe], rises[-probe]))
        error = calibrate.tilt_error_deg(up, down, probe, least=2 * dof)
        previous = self.module_settings
        switch = previous.tilt_switch_deg + error
        await self._save_module(
            previous.model_copy(
                update={"tilt_switch_deg": round(switch, 2), "tilt_calibrated": True}
            )
        )
        await self.poser.go(0.0, None)
        self.log.info(
            f"Tilt calibrated: the switch trips at {switch:.2f}° (was "
            f"{previous.tilt_switch_deg:.2f}°). Tilt is now level."
        )

    async def _run_stack(self, run: StackRun) -> None:
        await self._prepare_motion()
        await run.run()  # a stop during preparation is seen by the run itself

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

    def _require_module(self) -> None:
        state = self.module.state
        if not state.connected:
            raise OperationError(state.problem or "The scan module is not connected.")

    def _module_geometry(self) -> Geometry:
        c, calibration = self.config.module, self.module_settings
        low = c.tilt_min_deg
        if not calibration.tilt_calibrated:
            low = max(low, c.tilt_min_uncalibrated_deg)
        return Geometry(
            half_steps_per_turn=calibration.half_steps_per_turn,
            tilt_switch_deg=calibration.tilt_switch_deg,
            tilt_min_deg=low,
            tilt_max_deg=c.tilt_max_deg,
            takeup_deg=c.takeup_deg,
            switch_clearance_deg=c.tilt_homing_clearance_deg,
        )

    async def _save_module(self, calibration: ModuleSettings) -> None:
        """Store a new calibration and send the controller its new tilt limits. Only called
        by the calibrations, at their end, while the module is idle."""
        self.module_settings = calibration
        self._module_store.save(calibration)
        self.changed()
        await self.module.apply_limits()

    def _module_snapshot(self) -> dict[str, Any]:
        state = self.module.state
        geometry = self.module.geometry
        return {
            **asdict(state),
            "tilt_deg": round(geometry.tilt_deg(state.tilt_steps), 2),
            "yaw_deg": round(geometry.yaw_deg(state.yaw_steps) % 360.0, 2),
            "tilt_min_deg": geometry.tilt_min_deg,
            "tilt_max_deg": geometry.tilt_max_deg,
            "calibration": self.module_settings.model_dump(),
            "link": self.module.diagnostics(),
        }

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

    def _require_camera(self) -> None:
        if not self.camera.state.connected:
            raise OperationError(self.camera.state.problem or "The camera is not connected.")

    def _require_live_view(self) -> None:
        camera = self.camera.state
        if not camera.connected:
            raise OperationError(camera.problem or "The camera is not connected.")
        if not camera.live_view:
            raise OperationError("This needs live view, which this camera doesn't provide.")

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


async def _quietly(stop: Awaitable[None]) -> None:
    with contextlib.suppress(AxisError):
        await stop


def build_machine(config: Config, *, sim: bool = False, sim_speedup: float = 1.0) -> Machine:
    """Wire up the real hardware, or the simulator for `--sim`, tests and screenshots."""
    from .motion.rail import RailAxis

    activity_log = ActivityLog()
    store = SettingsStore(config.data_dir / "settings.json")
    machine: Machine

    def changed() -> None:
        machine.changed()

    camera: Camera
    module: Callable[[Callable[[], Geometry]], ScanModule]
    if sim:
        from .sim.camera import SimCamera
        from .sim.firmware import SimRail
        from .sim.module import SimModule
        from .sim.specimen import SimSpecimen

        sim_rail = SimRail(
            steps_per_mm=config.rail.steps_per_mm, backlash_mm=SIM_BACKLASH_MM, speedup=sim_speedup
        )
        axis = RailAxis(config.rail, sim_rail.open, activity_log, changed)
        sim_module = SimModule(speedup=sim_speedup)
        specimen = SimSpecimen()

        def specimen_view() -> tuple[SimSpecimen, float, float] | None:
            # A homed module stands for the 3D rig: the camera then sees the insect on it.
            if sim_module.tilt.homed and sim_module.yaw.homed:
                return specimen, sim_module.tilt_deg, sim_module.yaw_deg
            return None

        # The camera sees the carriage, which trails the motor by the backlash after a reversal.
        camera = SimCamera(
            lambda: sim_rail.physical_mm, speedup=sim_speedup, specimen=specimen_view
        )

        def module(geometry: Callable[[], Geometry]) -> ScanModule:
            return ScanModule(config.module, sim_module.open, geometry, activity_log, changed)
    else:
        from .camera.gphoto import GPhotoCamera
        from .motion.ports import PortFinder, opener

        finder = PortFinder()
        axis = RailAxis(
            config.rail, opener(finder, "rail", config.rail.port), activity_log, changed
        )
        camera = GPhotoCamera(config.camera, activity_log, changed)

        def module(geometry: Callable[[], Geometry]) -> ScanModule:
            port = opener(finder, "module", config.module.port)
            return ScanModule(config.module, port, geometry, activity_log, changed)

    module_store = ModuleStore(config.data_dir / "module.json")
    machine = Machine(config, axis, camera, store, activity_log, module, module_store)
    return machine
