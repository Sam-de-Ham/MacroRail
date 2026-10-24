"""Runs a 3D scan: for every pose, turn the specimen there, find its front and back with a
focus scan, and shoot a stack through it.

Each pose's stack is an ordinary stack in the review store (marked with the scan, so the 2D
Review leaves it out), so its frames, preview, depth map and zip work as for any stack. The
scan's own record, `scans/<id>/scan.json`, is rewritten after every pose: after a power cut
or a restart the scan resumes where it stopped, skipping the poses already done.

A pose whose focus scan finds nothing uses the last range that was found (the specimen is
centred, so its depth barely moves between neighbouring poses); the very first pose has none
to fall back on, so then the scan pauses for the user. After a pose's stack its preview and
depth map are made, and only every n-th frame is kept to save the Pi's card.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from ..focus.analysis import AnalysisError, RangeResult
from ..log import ActivityLog
from ..motion.base import AxisError, MotionInterrupted
from ..stack.plan import PlanError
from ..stack.runner import StackRun
from .plan import Pose

logger = logging.getLogger(__name__)

RECORD = "scan.json"
Phase = Literal["running", "pausing", "paused", "stopping", "done", "stopped", "failed"]
ACTIVE: frozenset[Phase] = frozenset({"running", "pausing", "paused", "stopping"})


@dataclass(frozen=True)
class ScanSteps:
    """What the scan needs from the machine, one call per step of a pose."""

    go: Callable[[Pose], Awaitable[None]]  # turn the module to the pose and let it settle
    find_range: Callable[[], Awaitable[RangeResult]]  # where the subject is in focus
    stack: Callable[[RangeResult, Pose, str], StackRun]  # a stack through the range
    keep_frames: Callable[[str, int], None]  # thin a finished stack's frames to every n-th


class ScanRun:
    def __init__(
        self,
        scan_id: str,
        folder: Path,
        poses: list[Pose],
        plan: dict[str, Any],
        steps: ScanSteps,
        log: ActivityLog,
        on_change: Callable[[], None],
        done: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.id = scan_id
        self._folder = folder
        self.poses = poses
        self.plan = plan  # the settings it was planned with, kept in the record
        self._steps = steps
        self._log = log
        self._on_change = on_change
        self.results: dict[int, dict[str, Any]] = dict(done or {})  # pose index -> outcome
        self.phase: Phase = "running"
        self.current: Pose | None = None
        self.stage = ""  # what the current pose is doing, for the user
        self.stack: StackRun | None = None
        self.error: str | None = None
        self.started_at = time.time()
        self._last_range: RangeResult | None = None
        self._resume = asyncio.Event()
        self._pause_requested = False
        self._stop_requested = False

    # -- control ------------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE

    @property
    def shooting(self) -> bool:
        """A stack is running (live view must be off then; the focus scans need it on)."""
        return self.stack is not None and self.stack.active

    def pause(self) -> None:
        """Pause after the current pose's stack, or at once inside it."""
        if self.phase != "running":
            return
        self._pause_requested = True
        if self.stack is not None and self.stack.active:
            self.stack.pause()
        self._set_phase("pausing")

    def resume(self) -> None:
        stack_held = self.stack is not None and self.stack.phase in ("paused", "camera_error")
        if self.phase not in ("pausing", "paused") and not stack_held:
            return
        if self.stack is not None and self.stack.active:
            self.stack.resume()  # also cancels a pause it hasn't reached yet
        self._pause_requested = False
        self._resume.set()
        self._set_phase("running")

    async def stop(self) -> None:
        if not self.active:
            return
        self._stop_requested = True
        self._set_phase("stopping")
        self._resume.set()
        if self.stack is not None and self.stack.active:
            await self.stack.stop()

    # -- the run ------------------------------------------------------------------------------

    async def run(self, check_stop: Callable[[], None]) -> None:
        """`check_stop` raises MotionInterrupted once the machine's Stop has been pressed."""
        self._write_record()
        outcome: Phase = "done"
        try:
            for pose in self.poses:
                if pose.index in self.results and self.results[pose.index]["outcome"] == "done":
                    continue
                await self._checkpoint()
                check_stop()
                await self._pose(pose)
        except (MotionInterrupted, _Stopped):
            outcome = "stopped"
        except AxisError as exc:
            self.error = str(exc)
            outcome = "failed"
        self.current = None
        self.stage = ""
        self._set_phase(outcome)
        self._write_record()
        done = sum(1 for r in self.results.values() if r["outcome"] == "done")
        message = f"{done} of {len(self.poses)} poses"
        if outcome == "done":
            self._log.info(f"Scan complete: {message}.")
        elif outcome == "stopped":
            self._log.info(f"Scan stopped after {message}. Resume it from the Scan tab.")
        else:
            self._log.error(f"Scan failed after {message}: {self.error}")

    async def _pose(self, pose: Pose) -> None:
        self.current = pose
        label = (
            f"Pose {pose.index + 1} of {len(self.poses)} "
            f"(tilt {pose.tilt_deg:g}°, yaw {pose.yaw_deg:g}°)"
        )
        self._log.info(f"{label}…")
        self._stage("turning")
        await self._steps.go(pose)
        self._stage("finding the range")
        found = await self._range(pose)
        while found is None:  # nothing to fall back on: the user has to help
            self.error = "The specimen wasn't found. Focus on it, then resume."
            self._log.warning(f"{label}: {self.error}")
            self._pause_requested = True
            await self._checkpoint()
            self.error = None
            found = await self._range(pose)
        self._stage("shooting")
        try:
            stack = self._steps.stack(found, pose, f"Pose {pose.index + 1}")
        except PlanError as exc:
            raise AxisError(f"{label}: {exc}") from None
        self.stack = stack
        self._on_change()
        try:
            await stack.run()
        finally:
            self.stack = None
        await stack.preview_ready()
        if stack.phase != "done":
            self.results[pose.index] = {"outcome": stack.phase, "stack": stack.id}
            self._write_record()
            if self._stop_requested:
                raise _Stopped
            raise AxisError(stack.error or f"the stack ended {stack.phase}")
        self._stage("saving")
        keep = int(self.plan.get("keep_every", 1))
        await asyncio.to_thread(self._steps.keep_frames, stack.id, keep)
        self.results[pose.index] = {
            "outcome": "done",
            "stack": stack.id,
            "range": [found.start, found.end],
            "shots": len(stack.shots),
            "files": [shot.file for shot in stack.shots],
            "finished_at": time.time(),
        }
        self._write_record()

    async def _range(self, pose: Pose) -> RangeResult | None:
        try:
            found = await self._steps.find_range()
        except AnalysisError as exc:
            if self._last_range is None:
                return None
            self._log.warning(f"Pose {pose.index + 1}: {exc} Using the last range found instead.")
            return self._last_range
        if found.clipped:
            self._log.warning(
                f"Pose {pose.index + 1}: the specimen reached the edge of the focus scan; "
                "the stack may not cover all of it."
            )
        self._last_range = found
        return found

    async def _checkpoint(self) -> None:
        if self._stop_requested:
            raise _Stopped
        if not self._pause_requested:
            return
        self._set_phase("paused")
        self._log.info("Scan paused.")
        self._resume.clear()
        await self._resume.wait()
        if self._stop_requested:
            raise _Stopped
        self._log.info("Scan resumed.")
        self._set_phase("running")

    # -- state --------------------------------------------------------------------------------

    def _stage(self, stage: str) -> None:
        self.stage = stage
        self._on_change()

    def _set_phase(self, phase: Phase) -> None:
        self.phase = phase
        self._on_change()

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "stage": self.stage,
            "current": asdict(self.current) if self.current else None,
            "poses": [asdict(p) for p in self.poses],
            "results": {str(i): r["outcome"] for i, r in self.results.items()},
            "stacks": {str(i): r.get("stack") for i, r in self.results.items()},
            "done": sum(1 for r in self.results.values() if r["outcome"] == "done"),
            "total": len(self.poses),
            "error": self.error,
            "stack": self.stack.snapshot() if self.stack else None,
        }

    def record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at,
            "updated_at": time.time(),
            "outcome": self.phase,
            "error": self.error,
            "plan": self.plan,
            "poses": [asdict(p) for p in self.poses],
            "results": {str(i): r for i, r in sorted(self.results.items())},
        }

    def _write_record(self) -> None:
        try:
            write_record(self._folder, self.record())
        except OSError as exc:
            self._log.warning(f"Could not save the scan record: {exc}")


class _Stopped(Exception):
    pass


def write_record(folder: Path, record: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (RECORD + ".tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(tmp, folder / RECORD)


def read_record(folder: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
