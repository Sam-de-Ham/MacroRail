"""3D scans end to end against the simulated rig: poses, stacks, records, stop and continue."""

from __future__ import annotations

import io
import zipfile

import pytest

from macrorail.machine import Machine, OperationError

from .conftest import idle, until
from .test_centring_machine import rig


async def ready(machine: Machine) -> None:
    specimen = await rig(machine)
    specimen.offset_mm = (0.0, 0.0, 0.0)
    await machine.update_settings({"stack": {"step": 60, "settle_s": 0.0}})
    machine.update_scan_plan(
        {"tilts": [0.0], "yaw_step_deg": 180.0, "settle_s": 0.0, "keep_every": 4}
    )


async def test_scan_needs_the_rig(machine: Machine) -> None:
    await until(lambda: machine.module.state.connected)
    machine.update_scan_plan({"tilts": [0.0]})
    with pytest.raises(OperationError, match="Home"):
        machine.start_scan()


async def test_plan_settings_are_checked(machine: Machine) -> None:
    with pytest.raises(OperationError, match="Invalid scan plan"):
        machine.update_scan_plan({"yaw_step_deg": 1.0})
    snapshot = machine.snapshot()["scan3d"]
    assert snapshot["plan"]["tilts"] == [60.0, 30.0, 0.0, -30.0]
    # Until tilt is calibrated, -30 is out of reach.
    assert "Calibrate tilt" in snapshot["error"]


async def test_a_scan_shoots_every_pose(machine: Machine) -> None:
    await ready(machine)
    machine.start_scan()
    await idle(machine, timeout=300)
    run = machine.scan
    assert run is not None
    assert run.phase == "done", machine.log.entries[-1].message
    record = machine.scans.record(run.id)
    assert record is not None
    assert [r["outcome"] for r in record["results"].values()] == ["done", "done"]
    # The poses' stacks are kept for the scan, thinned, and left out of the 2D list.
    for result in record["results"].values():
        assert result["shots"] >= 2
        assert len(result["files"]) == result["shots"]
        frames = list(
            (machine.config.data_dir / "stacks" / result["stack"] / "frames").glob("*.jpg")
        )
        assert 1 <= len(frames) <= result["shots"] // 4 + 2
        assert (machine.config.data_dir / "stacks" / result["stack"] / "preview.jpg").exists()
    assert machine.review.stacks() == []
    assert machine.snapshot()["scan3d"]["unfinished"] == []

    # The export: one all-in-focus image per pose, named by angle, with a pose table.
    name, chunks = machine.scans.archive(run.id, machine.review)
    with zipfile.ZipFile(io.BytesIO(b"".join(chunks))) as archive:
        names = sorted(n.split("/", 1)[1] for n in archive.namelist())
        table = archive.read(f"{name[:-4]}/poses.csv").decode().splitlines()
    assert names == [
        "about.json",
        "depth/pose-001_tilt+000_yaw000-colour.jpg",
        "depth/pose-001_tilt+000_yaw000.png",
        "depth/pose-002_tilt+000_yaw180-colour.jpg",
        "depth/pose-002_tilt+000_yaw180.png",
        "images/pose-001_tilt+000_yaw000.jpg",
        "images/pose-002_tilt+000_yaw180.jpg",
        "poses.csv",
        "scan.json",
    ]
    assert table[0].startswith("pose,tilt_deg,yaw_deg,image")
    assert len(table) == 3


async def test_a_stopped_scan_continues_where_it_stopped(machine: Machine) -> None:
    await ready(machine)
    machine.start_scan()
    run = machine.scan
    assert run is not None
    await until(lambda: 0 in run.results, timeout=200)
    await machine.stop()
    await idle(machine, timeout=60)
    assert run.phase == "stopped"
    unfinished = machine.snapshot()["scan3d"]["unfinished"]
    assert [s["id"] for s in unfinished] == [run.id]

    machine.continue_scan(run.id)
    await idle(machine, timeout=300)
    assert machine.scan is not None
    assert machine.scan.phase == "done"
    record = machine.scans.record(run.id)
    assert record is not None
    assert len(record["results"]) == 2
    assert machine.snapshot()["scan3d"]["unfinished"] == []

    machine.delete_scan(run.id)
    assert machine.scans.scans() == []
    assert machine.review.stacks_of_scan(run.id) == []


async def test_one_test_pose(machine: Machine) -> None:
    await ready(machine)
    with pytest.raises(OperationError, match="Turn to a tilt"):
        machine.start_scan(test=True)  # homing parked tilt above the range
    machine.pose(0.0, 45.0)
    await idle(machine, timeout=30)
    machine.start_scan(test=True)
    await idle(machine, timeout=200)
    assert machine.scan is not None
    assert machine.scan.phase == "done"
    assert len(machine.scan.poses) == 1
    assert machine.snapshot()["scan3d"]["unfinished"] == []  # tests aren't offered to continue


async def test_stop_while_homing_yaw_ends_the_scan(machine: Machine) -> None:
    await ready(machine)
    machine.start_scan()
    run = machine.scan
    assert run is not None
    with pytest.raises(OperationError, match="can't change while a 3D scan runs"):
        await machine.update_settings({"stack": {"step": 30}})
    await until(lambda: machine.module.state.moving == "yaw", timeout=10)
    await machine.stop()
    await idle(machine, timeout=30)
    assert run.phase == "stopped"
    assert not run.active
    machine.delete_scan(run.id)  # not stuck "running"


async def test_a_damaged_record_is_refused(machine: Machine) -> None:
    folder = machine.scans.folder("20261024-120000")
    folder.mkdir(parents=True)
    (folder / "scan.json").write_text('{"poses": [], "plan": {"step": null}, "results": []}')
    with pytest.raises(OperationError, match="can't be read"):
        machine.continue_scan("20261024-120000")
