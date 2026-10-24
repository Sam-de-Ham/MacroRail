"""Planning 3D scans, and the scan runner's flow against stand-in steps."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from macrorail.focus.analysis import AnalysisError, RangeResult
from macrorail.log import ActivityLog
from macrorail.scan.plan import ScanPlanError, estimate, plan_poses
from macrorail.scan.runner import ScanRun, ScanSteps, read_record

RANGE = (-33.0, 90.0)


def test_rings_top_down_yaw_forwards() -> None:
    poses = plan_poses([0.0, 60.0, -30.0, 30.0], 36.0, RANGE)
    assert len(poses) == 40
    assert [p.tilt_deg for p in poses[::10]] == [60.0, 30.0, 0.0, -30.0]
    assert [p.yaw_deg for p in poses[:10]] == [36.0 * k for k in range(10)]
    assert [p.index for p in poses] == list(range(40))


def test_a_yaw_step_that_doesnt_divide_the_circle_is_evened_out() -> None:
    poses = plan_poses([0.0], 50.0, RANGE)
    assert len(poses) == 7
    assert poses[1].yaw_deg == pytest.approx(360 / 7, abs=1e-3)


def test_tilts_outside_the_range_are_refused() -> None:
    with pytest.raises(ScanPlanError, match="Calibrate tilt"):
        plan_poses([-30.0], 36.0, (-20.0, 90.0))
    with pytest.raises(ScanPlanError, match="at least one"):
        plan_poses([], 36.0, RANGE)


def test_estimate_keeps_every_nth_frame() -> None:
    e = estimate(poses=40, shots_per_pose=95, seconds_per_pose=200.0, keep_every=10)
    assert e.shots == 3800
    assert e.seconds == 8000.0
    assert e.pi_bytes == 40 * (600_000 + 500_000) + 40 * 10 * 250_000


# -- the runner, with stand-ins for the machine ----------------------------------------------


class FakeStack:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.id = name
        self.phase = "preparing"
        self.shots: list[Any] = []
        self.error: str | None = "camera gone" if fail else None
        self._fail = fail
        self.paused = asyncio.Event()

    @property
    def active(self) -> bool:
        return self.phase in ("preparing", "running", "paused")

    async def run(self) -> None:
        self.phase = "running"
        await asyncio.sleep(0)
        self.phase = "failed" if self._fail else "done"

    async def preview_ready(self) -> None:
        pass

    def snapshot(self) -> dict[str, Any]:
        return {"id": self.id, "phase": self.phase}


def found(start: int = 100, end: int = 200) -> RangeResult:
    return RangeResult(start, end, (), (), clipped=False)


def runner(
    tmp_path: Path,
    ranges: list[Any],
    poses: int = 3,
    fail_at: int | None = None,
    done: dict[int, dict[str, Any]] | None = None,
) -> tuple[ScanRun, list[str]]:
    calls: list[str] = []
    queue = list(ranges)

    async def go(pose: Any) -> None:
        calls.append(f"go {pose.index}")

    async def find_range() -> RangeResult:
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def stack(rng: RangeResult, pose: Any, name: str) -> Any:
        calls.append(f"stack {pose.index} {rng.start}-{rng.end}")
        return FakeStack(f"s{pose.index}", fail=pose.index == fail_at)

    async def keep(stack_id: str, every: int) -> None:
        calls.append(f"keep {stack_id} {every}")

    async def begin() -> None:
        calls.append("begin")

    run = ScanRun(
        "20261024-120000",
        tmp_path / "scan",
        plan_poses([0.0], 360.0 / poses, RANGE),
        {"keep_every": 10},
        ScanSteps(begin=begin, go=go, find_range=find_range, stack=stack, keep_frames=keep),
        ActivityLog(),
        lambda: None,
        done=done,
    )
    return run, calls


async def test_every_pose_is_shot_and_recorded(tmp_path: Path) -> None:
    run, calls = runner(tmp_path, [found(), found(110, 210), found(120, 220)])
    await run.run(lambda: None)
    assert run.phase == "done"
    assert calls[:4] == ["begin", "go 0", "stack 0 100-200", "keep s0 10"]
    record = read_record(tmp_path / "scan")
    assert record is not None
    assert record["outcome"] == "done"
    assert {i: r["outcome"] for i, r in record["results"].items()} == {
        "0": "done",
        "1": "done",
        "2": "done",
    }


async def test_a_lost_range_falls_back_to_the_last_one(tmp_path: Path) -> None:
    run, calls = runner(tmp_path, [found(), AnalysisError("nothing"), found(130, 230)])
    await run.run(lambda: None)
    assert "stack 1 100-200" in calls


async def test_no_range_at_the_first_pose_stops_for_the_user(tmp_path: Path) -> None:
    # Focusing needs the rail, which only moves once the scan has stopped; Continue then
    # picks up at this pose.
    run, calls = runner(tmp_path, [AnalysisError("nothing")])
    await run.run(lambda: None)
    assert run.phase == "stopped"
    assert run.error
    assert "Focus on it" in run.error
    assert not any(c.startswith("stack") for c in calls)


async def test_continuing_skips_the_poses_done_and_keeps_their_range(tmp_path: Path) -> None:
    done = {
        0: {"outcome": "done", "range": [100, 200]},
        1: {"outcome": "done", "range": [140, 240]},
    }
    run, calls = runner(tmp_path, [AnalysisError("nothing")], poses=3, done=done)
    await run.run(lambda: None)
    assert [c for c in calls if c.startswith("go")] == ["go 2"]
    assert "stack 2 140-240" in calls  # the last range found before falls in
    assert run.phase == "done"


async def test_an_unexpected_error_still_ends_the_scan(tmp_path: Path) -> None:
    run, _ = runner(tmp_path, [OSError("card full")])
    await run.run(lambda: None)
    assert run.phase == "failed"
    assert not run.active
    assert run.error == "card full"
    record = read_record(tmp_path / "scan")
    assert record is not None
    assert record["outcome"] == "failed"


async def test_a_failed_stack_fails_the_scan(tmp_path: Path) -> None:
    run, _ = runner(tmp_path, [found(), found()], fail_at=1)
    await run.run(lambda: None)
    assert run.phase == "failed"
    assert run.error == "camera gone"
    record = read_record(tmp_path / "scan")
    assert record is not None
    assert record["results"]["1"]["outcome"] == "failed"
