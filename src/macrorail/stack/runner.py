"""Runs one focus stack: move → settle → trigger → wait for the camera → next.

The stage only ever moves in the stack direction while shooting, so lead-screw backlash
never shifts a slice. A camera failure pauses the stack (the user fixes it and resumes,
which retakes the same slice); a stop or the last shot returns the stage to the start.

When the camera sends a JPEG for each shot, a small copy is downloaded for review while the
stage moves on, and a quick preview stack is made at the end.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Literal

from ..camera.base import Camera, CameraError, Capture
from ..log import ActivityLog
from ..motion.base import Axis, AxisError, MotionInterrupted
from ..review.store import ReviewError, ReviewStore
from .plan import StackPlan

logger = logging.getLogger(__name__)

Phase = Literal[
    "preparing", "running", "paused", "camera_error", "returning", "done", "stopped", "failed"
]
ACTIVE_PHASES: frozenset[Phase] = frozenset(
    {"preparing", "running", "paused", "camera_error", "returning"}
)

Approach = Callable[[int, int], Awaitable[None]]


class _StopRequested(Exception):
    pass


@dataclass(frozen=True)
class Shot:
    index: int
    position: int
    file: str
    time: float
    capture_s: float


class StackRun:
    def __init__(
        self,
        plan: StackPlan,
        *,
        axis: Axis,
        camera: Camera,
        approach: Approach,
        speed: float,
        accel: float,
        settle_s: float,
        log: ActivityLog,
        on_change: Callable[[], None],
        store: ReviewStore,
        name: str = "",
        download_previews: bool = True,
    ) -> None:
        self.plan = plan
        self.name = name
        self._axis = axis
        self._camera = camera
        self._approach = approach
        self._speed = speed
        self._accel = accel
        self._settle_s = settle_s
        self._log = log
        self._on_change = on_change
        self._store = store
        self._download_previews = download_previews
        self._downloads: list[asyncio.Task[None]] = []
        self._preview_task: asyncio.Task[None] | None = None  # kept so it isn't collected
        self._download_problem_logged = False
        self.previews = 0  # small JPEG copies downloaded so far
        self.latest_preview: int | None = None  # shot number of the newest one
        self.phase: Phase = "preparing"
        self.shots: list[Shot] = []
        self.error: str | None = None
        self.started_at = time.time()
        self.finished_at: float | None = None
        self._active_s = 0.0
        self._active_since: float | None = time.monotonic()
        self._pause_requested = False
        self._stop_requested = False
        self._resume = asyncio.Event()
        self._shot_clock: list[float] = []  # active time at each shot, for the ETA
        self.id = store.create(self.started_at)

    # -- control (from the event loop, any time) ----------------------------------------------

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE_PHASES

    def pause(self) -> None:
        if self.phase in ("preparing", "running"):
            self._pause_requested = True
            self._on_change()

    def resume(self) -> None:
        if self.phase in ("paused", "camera_error") or self._pause_requested:
            self._pause_requested = False
            self._resume.set()

    async def stop(self) -> None:
        if not self.active or self._stop_requested:
            return
        self._stop_requested = True
        self._resume.set()
        if self.phase in ("preparing", "running", "returning"):
            await self._axis.stop()  # interrupts a move in progress; otherwise a no-op

    # -- progress -----------------------------------------------------------------------------

    @property
    def elapsed_s(self) -> float:
        running = time.monotonic() - self._active_since if self._active_since else 0.0
        return self._active_s + running

    @property
    def remaining_s(self) -> float | None:
        clock = self._shot_clock
        if len(clock) < 2 or self.phase not in ("running", "paused", "camera_error"):
            return None
        per_shot = (clock[-1] - clock[0]) / (len(clock) - 1)
        return per_shot * (self.plan.count - len(clock))

    def snapshot(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "previews": self.previews,
            "latest_preview": self.latest_preview,
            "phase": self.phase,
            "pausing": self._pause_requested and self.phase == "running",
            "stopping": self._stop_requested and self.active,
            "taken": len(self.shots),
            "total": self.plan.count,
            "start": self.plan.start,
            "end": self.plan.end,
            "step": self.plan.step,
            "last_file": self.shots[-1].file if self.shots else None,
            "elapsed_s": round(self.elapsed_s, 1),
            "remaining_s": None if self.remaining_s is None else round(self.remaining_s),
            "error": self.error,
        }

    # -- the run ------------------------------------------------------------------------------

    async def run(self) -> None:
        outcome: Phase = "done"
        self._log.info(f"Stack started: {self.plan.count} shots.")
        try:
            if self._stop_requested:
                raise _StopRequested
            await self._approach(self.plan.start, self.plan.direction)
            self._set_phase("running")
            while len(self.shots) < self.plan.count:
                await self._checkpoint()
                await self._shoot(len(self.shots))
        except (_StopRequested, MotionInterrupted):
            outcome = "stopped"
        except AxisError as exc:
            self.error = str(exc)
            outcome = "failed"
        if outcome != "failed" and self.phase != "preparing":  # stopped before reaching the start
            await self._return_to_start()
        await self._finish(outcome)

    async def _shoot(self, index: int) -> None:
        position = self.plan.positions[index]
        if self._axis.state.position != position:
            await self._axis.move_to(position, self._speed, self._accel)
        await asyncio.sleep(self._settle_s)
        try:
            capture = await self._camera.capture()
        except CameraError as exc:
            self.error = str(exc)
            self._log.error(f"Stack paused at shot {index + 1}: {exc}")
            self._set_phase("camera_error")
            return  # the checkpoint waits for resume, then this slice is retaken
        self.shots.append(Shot(index, position, capture.name, time.time(), capture.duration_s))
        self._shot_clock.append(self.elapsed_s)
        self._on_change()
        if self._download_previews:
            self._fetch_later(index + 1, capture)

    def _fetch_later(self, number: int, capture: Capture) -> None:
        """Download the shot's JPEG while the stage moves on (the camera queues it before
        the next shot)."""
        if not capture.is_jpeg:
            self._download_problem(
                f"The camera sends {capture.name.rsplit('.', 1)[-1].upper()} files to the Pi, so "
                "there are no previews. Set it to send JPEGs to the computer to get them."
            )
            return
        self._downloads.append(asyncio.create_task(self._fetch(number, capture)))

    async def _fetch(self, number: int, capture: Capture) -> None:
        try:
            jpeg = await self._camera.download(capture)
            await self._store.add_frame(self.id, number, jpeg)
        except (CameraError, OSError, ValueError) as exc:
            self._download_problem(f"Could not download a preview ({exc}). Stacking continues.")
            return
        self.previews += 1
        self.latest_preview = max(number, self.latest_preview or 0)
        self._on_change()

    def _download_problem(self, message: str) -> None:
        if not self._download_problem_logged:
            self._download_problem_logged = True
            self._log.warning(message)

    async def _checkpoint(self) -> None:
        if self._stop_requested:
            raise _StopRequested
        if self._pause_requested and self.phase == "running":
            self._set_phase("paused")
            self._log.info(f"Stack paused after {len(self.shots)} of {self.plan.count} shots.")
        if self.phase in ("paused", "camera_error"):
            self._pause_clock()
            self._resume.clear()
            await self._resume.wait()
            if self._stop_requested:
                raise _StopRequested
            self._log.info("Stack resumed.")
            self.error = None
            self._pause_requested = False
            self._active_since = time.monotonic()
            self._set_phase("running")

    async def _return_to_start(self) -> None:
        self._set_phase("returning")
        try:
            await self._approach(self.plan.start, self.plan.direction)
        except MotionInterrupted:
            self._log.info("Return to the start was stopped.")
        except AxisError as exc:
            self.error = f"Could not return to the start: {exc}"
            self._log.error(self.error)

    async def _finish(self, outcome: Phase) -> None:
        await asyncio.gather(*self._downloads)
        self._pause_clock()
        self.finished_at = time.time()
        self._set_phase(outcome)
        taken = f"{len(self.shots)} of {self.plan.count} shots"
        if outcome == "done":
            self._log.info(f"Stack complete: {taken} in {_duration(self.elapsed_s)}.")
        elif outcome == "stopped":
            self._log.info(f"Stack stopped after {taken}.")
        else:
            self._log.error(f"Stack failed after {taken}: {self.error}")
        self._save_record()
        if self.previews >= 2:
            self._preview_task = asyncio.create_task(self._build_preview())

    async def _build_preview(self) -> None:
        try:
            await self._store.build_preview(self.id)
        except ReviewError as exc:
            self._log.warning(f"No preview stack: {exc}")
        except Exception:
            logger.exception("preview stack failed")
            self._log.warning("The preview stack could not be made.")

    def _pause_clock(self) -> None:
        if self._active_since is not None:
            self._active_s += time.monotonic() - self._active_since
            self._active_since = None

    def _set_phase(self, phase: Phase) -> None:
        self.phase = phase
        self._on_change()

    def _save_record(self) -> None:
        record = {
            "name": self.name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.phase,
            "error": self.error,
            "steps_per_mm": self._axis.steps_per_mm,
            "plan": {
                "start": self.plan.start,
                "end": self.plan.end,
                "step": self.plan.step,
                "count": self.plan.count,
            },
            "settle_s": self._settle_s,
            "active_s": round(self.elapsed_s, 1),
            "shots": [asdict(shot) for shot in self.shots],
        }
        try:
            self._store.write_record(self.id, record)
        except (OSError, ReviewError) as exc:
            self._log.warning(f"Could not save the stack record: {exc}")


def _duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"
