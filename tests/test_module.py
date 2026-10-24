"""The scan module driver, posing and its Machine/API commands, against the simulated module."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from macrorail.api import create_app
from macrorail.config import Config, ModuleConfig, RailConfig
from macrorail.log import ActivityLog
from macrorail.machine import Machine, OperationError, build_machine
from macrorail.motion.base import AxisError, MotionInterrupted
from macrorail.motion.module import Geometry, ScanModule
from macrorail.motion.ports import PortFinder
from macrorail.motion.rail import RailAxis
from macrorail.scan.pose import Poser
from macrorail.settings import NOMINAL_HALF_STEPS_PER_TURN
from macrorail.sim.firmware import SimRail
from macrorail.sim.module import SimModule

from .conftest import SPEEDUP, idle, until

CONFIG = ModuleConfig(port="sim")
GEOMETRY = Geometry(
    half_steps_per_turn=NOMINAL_HALF_STEPS_PER_TURN,
    tilt_half_steps_per_turn=NOMINAL_HALF_STEPS_PER_TURN,
    tilt_switch_deg=97.0,
    tilt_min_deg=-33.0,
    tilt_max_deg=90.0,
    takeup_deg=CONFIG.takeup_deg,
    switch_clearance_deg=CONFIG.tilt_homing_clearance_deg,
)


@pytest.fixture
def sim_module() -> SimModule:
    return SimModule(speedup=SPEEDUP, tilt_start_deg=10.0, yaw_start_deg=200.0)


@pytest.fixture
async def module(sim_module: SimModule) -> AsyncIterator[ScanModule]:
    driver = ScanModule(CONFIG, sim_module.open, lambda: GEOMETRY, ActivityLog(), lambda: None)
    task = asyncio.create_task(driver.run())
    await until(lambda: driver.state.connected)
    yield driver
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def poser(module: ScanModule, stop: list[bool] | None = None) -> Poser:
    def check_stop() -> None:
        if stop and stop[0]:
            raise MotionInterrupted("Stopped.")

    return Poser(module, CONFIG, check_stop, ActivityLog())


# -- driver ---------------------------------------------------------------------------------


async def test_connects_and_reports_status(module: ScanModule) -> None:
    state = module.state
    assert state.firmware
    assert state.problem is None
    assert not state.tilt_homed
    assert not state.yaw_homed
    assert state.hall is not None
    assert 0 <= state.hall <= 1023


async def test_homing_puts_the_axes_at_their_references(
    module: ScanModule, sim_module: SimModule
) -> None:
    await poser(module).home(("tilt", "yaw"))
    assert module.state.tilt_homed
    assert module.state.yaw_homed
    # Tilt parks clear of the switch, at the top of what the controller may reach.
    assert module.tilt_deg() == pytest.approx(GEOMETRY.tilt_top_deg, abs=0.1)
    assert abs(sim_module.tilt_deg - module.tilt_deg()) < 0.5
    # Yaw 0 is the magnet over the sensor.
    assert module.yaw_deg() == 0.0
    assert min(sim_module.yaw_deg, 360 - sim_module.yaw_deg) < 0.3


async def test_poses_land_where_asked_from_either_side(
    module: ScanModule, sim_module: SimModule
) -> None:
    p = poser(module)
    await p.home(("tilt", "yaw"))
    landed: dict[tuple[float, float], tuple[float, float]] = {}
    # Each pose is reached from both sides; the take-up makes the result the same.
    for tilt, yaw in [(0.0, 90.0), (45.0, 30.0), (-20.0, 300.0), (0.0, 90.0), (89.0, -45.0)]:
        await p.go(tilt=tilt, yaw=yaw)
        # Tilt is homed against the switch turning one way and posed turning the other, so it
        # sits one gearbox backlash (0.3° here) off: the same at every pose, and absorbed by
        # the tilt calibration, which measures level arriving the way poses do.
        assert -0.05 < sim_module.tilt_deg - tilt < 0.35, (tilt, sim_module.tilt_deg)
        # Yaw homes onto the magnet turning the way poses arrive, so it has no such offset.
        assert abs((sim_module.yaw_deg - yaw + 180) % 360 - 180) < 0.15, (yaw, sim_module.yaw_deg)
        here = (sim_module.tilt_deg, sim_module.yaw_deg)
        if (tilt, yaw) in landed:  # came back from the other side: lands in the same place
            assert abs(here[0] - landed[tilt, yaw][0]) < 0.05
            assert abs(here[1] - landed[tilt, yaw][1]) < 0.05
        landed[tilt, yaw] = here


async def test_yaw_takes_the_short_way_round(module: ScanModule) -> None:
    p = poser(module)
    await p.home(("yaw",))
    await p.yaw_to(350.0)
    assert module.state.yaw_steps < 0  # -10°, not +350°
    await p.yaw_to(10.0)
    assert 0 < module.yaw_deg() < 11


async def test_tilt_outside_the_range_is_refused(module: ScanModule) -> None:
    p = poser(module)
    await p.home(("tilt",))
    with pytest.raises(AxisError, match="Tilt goes from"):
        await p.tilt_to(-40.0)
    with pytest.raises(AxisError, match="Tilt goes from"):
        await p.tilt_to(91.0)


async def test_moves_need_homing(module: ScanModule) -> None:
    with pytest.raises(AxisError, match="Home tilt"):
        await module.move("tilt", 100, 100, 400)


async def test_stop_interrupts_a_turn(module: ScanModule) -> None:
    p = poser(module)
    await p.home(("yaw",))
    turn = asyncio.create_task(p.yaw_to(170.0))
    await until(lambda: module.state.moving == "yaw")
    await module.stop()
    with pytest.raises(MotionInterrupted):
        await turn
    assert 0 < module.yaw_deg() < 170


async def test_rail_driver_refuses_the_module_port(sim_module: SimModule) -> None:
    rail = RailAxis(RailConfig(port="sim"), sim_module.open, ActivityLog(), lambda: None)
    task = asyncio.create_task(rail.run())
    await until(lambda: rail.state.problem is not None and "scan module" in rail.state.problem)
    assert not rail.state.connected
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_module_driver_refuses_the_rail_port() -> None:
    rail = SimRail(speedup=SPEEDUP)
    driver = ScanModule(CONFIG, rail.open, lambda: GEOMETRY, ActivityLog(), lambda: None)
    task = asyncio.create_task(driver.run())
    await until(lambda: driver.state.problem is not None and "rail" in driver.state.problem)
    assert not driver.state.connected
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


# -- port finding ---------------------------------------------------------------------------


def test_port_finder_skips_the_other_controllers_port() -> None:
    probed: list[str] = []
    roles = {"/a": "rail", "/b": "module", "/c": None}

    def probe(port: str):  # type: ignore[no-untyped-def]
        probed.append(port)
        return roles[port]

    finder = PortFinder(candidates=lambda: ["/a", "/b", "/c"], probe_port=probe)
    assert finder.find("rail") == "/a"
    probed.clear()
    assert finder.find("module") == "/b"
    assert probed == ["/b"]  # the rail's port isn't opened (that would reset its Nano)
    probed.clear()
    assert finder.find("rail") == "/a"
    assert probed == ["/a"]  # nor the module's; /c answered nothing and is left alone a while


def test_port_finder_reports_a_missing_controller() -> None:
    finder = PortFinder(candidates=lambda: ["/a"], probe_port=lambda port: "rail")
    with pytest.raises(OSError, match="no scan module controller"):
        finder.find("module")


def test_port_finder_resolves_a_fixed_port_at_every_search(tmp_path: Path) -> None:
    # The rail's config names a link that only appears once its Nano is plugged in.
    rail_link = tmp_path / "rail"
    target = tmp_path / "ttyUSB1"
    target.touch()
    probed: list[str] = []

    def probe(port: str):  # type: ignore[no-untyped-def]
        probed.append(port)
        return None

    finder = PortFinder(candidates=lambda: [str(target)], probe_port=probe)
    finder.claim("rail", str(rail_link))
    try:
        rail_link.symlink_to(target)  # plugged in after the app started
    except OSError:
        pytest.skip("this system can't make symlinks")
    with pytest.raises(OSError, match="no scan module"):
        finder.find("module")
    assert probed == []  # the rail's live port is never opened


def test_port_finder_remembers_the_other_controller() -> None:
    probed: list[str] = []
    roles = {"/a": "rail", "/b": "module"}

    def probe(port: str):  # type: ignore[no-untyped-def]
        probed.append(port)
        return roles[port]

    finder = PortFinder(candidates=lambda: ["/a", "/b"], probe_port=probe)
    assert finder.find("module") == "/b"  # on the way it met the rail on /a
    probed.clear()
    assert finder.find("module") == "/b"
    assert probed == ["/b"]  # the rail's port isn't opened again


def test_port_finder_follows_a_controller_that_moved() -> None:
    # The rail was on /b and the module on /a; both were replugged and swapped ports.
    roles = {"/a": "module", "/b": "rail"}
    finder = PortFinder(candidates=lambda: ["/a", "/b"], probe_port=lambda port: roles[port])
    assert finder.find("module") == "/a"
    assert finder.find("rail") == "/b"
    roles = {"/a": "rail", "/b": "module"}
    assert finder.find("module") == "/b"  # it meets the rail on /a on the way...
    assert finder.find("rail") == "/a"  # ...and the rail's search no longer skips /a


def test_yaw_calibration_leaves_tilt_alone() -> None:
    measured = replace(GEOMETRY, half_steps_per_turn=4083.0)
    assert measured.tilt_steps(0.0) == GEOMETRY.tilt_steps(0.0)
    assert measured.yaw_steps(90.0) != GEOMETRY.yaw_steps(90.0)


def test_port_finder_respects_a_fixed_port() -> None:
    probed: list[str] = []

    def probe(port: str):  # type: ignore[no-untyped-def]
        probed.append(port)
        return "module"

    finder = PortFinder(candidates=lambda: ["/fixed", "/other"], probe_port=probe)
    finder.claim("rail", "/fixed")
    assert finder.find("module") == "/other"
    assert probed == ["/other"]


# -- machine and API ------------------------------------------------------------------------


async def module_ready(machine: Machine) -> None:
    await until(lambda: machine.module.state.connected)


async def test_machine_homes_and_poses(machine: Machine) -> None:
    await module_ready(machine)
    with pytest.raises(OperationError, match="Home tilt"):
        machine.pose(0.0, None)
    machine.home_module(("tilt", "yaw"))
    await idle(machine, timeout=20)
    snapshot = machine.snapshot()["module"]
    assert snapshot["tilt_homed"]
    assert snapshot["yaw_homed"]
    # Until tilt is calibrated, the belly side stops short of the full range.
    assert snapshot["tilt_min_deg"] == -20.0
    with pytest.raises(OperationError, match="Tilt goes from -20"):
        machine.pose(-25.0, None)
    machine.pose(0.0, 90.0)
    await idle(machine, timeout=20)
    snapshot = machine.snapshot()["module"]
    assert abs(snapshot["tilt_deg"]) < 0.2
    assert abs(snapshot["yaw_deg"] - 90) < 0.2


async def test_calibrated_tilt_opens_the_full_range(machine: Machine) -> None:
    await module_ready(machine)
    await machine._save_module(machine.module_settings.model_copy(update={"tilt_calibrated": True}))
    assert machine.snapshot()["module"]["tilt_min_deg"] == -33.0


async def test_calibration_is_not_a_settings_edit(machine: Machine) -> None:
    with pytest.raises(OperationError, match="unknown settings section"):
        await machine.update_settings({"module": {"tilt_calibrated": True}})


async def test_calibration_has_its_own_file(machine: Machine) -> None:
    # The 2D settings file stays readable by the 2D-only app (it forbids unknown sections).
    await module_ready(machine)
    await machine._save_module(machine.module_settings.model_copy(update={"tilt_switch_deg": 96}))
    await machine.update_settings({"stack": {"step": 8}})
    data_dir = machine.config.data_dir
    assert "module" not in json.loads((data_dir / "settings.json").read_text())
    assert json.loads((data_dir / "module.json").read_text())["tilt_switch_deg"] == 96


async def test_tilt_top_stays_clear_of_the_switch(machine: Machine) -> None:
    # A switch calibrated low leaves less room above 90 degrees than the take-up wants.
    await module_ready(machine)
    await machine._save_module(machine.module_settings.model_copy(update={"tilt_switch_deg": 92}))
    machine.home_module(("tilt",))
    await idle(machine, timeout=20)
    machine.pose(90.0, None)
    await idle(machine, timeout=20)
    snapshot = machine.snapshot()["module"]
    assert snapshot["tilt_homed"]  # the switch wasn't hit
    assert abs(snapshot["tilt_deg"] - 90) < 0.2
    with pytest.raises(OperationError, match="Tilt goes from"):
        machine.jog_module("tilt", 5.0)


async def test_jog_limits(machine: Machine) -> None:
    await module_ready(machine)
    with pytest.raises(OperationError, match="limited to 10"):
        machine.jog_module("tilt", 15.0)  # tilt isn't homed yet
    with pytest.raises(OperationError, match="limited to 45"):
        machine.jog_module("yaw", 50.0)
    machine.jog_module("yaw", -20.0)
    await idle(machine)


async def test_stop_also_stops_the_module(machine: Machine) -> None:
    await module_ready(machine)
    machine.jog_module("yaw", 45.0)
    await until(lambda: machine.module.state.moving == "yaw")
    await machine.stop()
    await idle(machine)
    assert machine.module.state.moving is None


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    machine = build_machine(
        Config(rail=RailConfig(port="sim"), data_dir=tmp_path), sim=True, sim_speedup=SPEEDUP
    )
    with TestClient(create_app(machine)) as test_client:
        deadline = time.monotonic() + 5
        while not test_client.get("/api/state").json()["module"]["connected"]:
            assert time.monotonic() < deadline, "simulated module did not connect"
            time.sleep(0.05)
        yield test_client


def test_api_module_commands(client: TestClient) -> None:
    headers = {"X-Client-Id": "phone"}
    client.post("/api/control/take", headers=headers)
    response = client.post("/api/module/home", json={"axes": ["yaw"]}, headers=headers)
    assert response.status_code == 204
    deadline = time.monotonic() + 20
    while client.get("/api/state").json()["activity"] != "idle":
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert client.get("/api/state").json()["module"]["yaw_homed"]
    response = client.post("/api/module/pose", json={"tilt": 0}, headers=headers)
    assert response.status_code == 409
    assert "Home tilt" in response.json()["detail"]


def test_api_rejects_bad_angles_and_strangers(client: TestClient) -> None:
    headers = {"X-Client-Id": "phone"}
    client.post("/api/control/take", headers=headers)
    for body in ({"axis": "roll", "delta_deg": 5}, {"axis": "yaw", "delta_deg": "nan"}):
        assert client.post("/api/module/jog", json=body, headers=headers).status_code == 422
    assert client.post("/api/module/pose", json={"yaw": "inf"}, headers=headers).status_code == 422
    response = client.post("/api/module/home", json={"axes": ["roll"]}, headers=headers)
    assert response.status_code == 422
    stranger = {"X-Client-Id": "laptop"}
    assert client.post("/api/module/home", json={}, headers=stranger).status_code == 403
