"""The scan module's calibrations, end to end against the simulator."""

from __future__ import annotations

import asyncio

import pytest

from macrorail.log import ActivityLog
from macrorail.machine import Machine, OperationError
from macrorail.motion.module import ScanModule
from macrorail.scan.pose import Poser
from macrorail.sim.module import SimModule
from macrorail.sim.specimen import SimSpecimen

from .conftest import SPEEDUP, idle, until
from .test_module import CONFIG, GEOMETRY


async def test_measures_the_real_yaw_turn() -> None:
    sim = SimModule(steps_per_rev=4083.0, speedup=SPEEDUP, yaw_start_deg=40.0)
    driver = ScanModule(CONFIG, sim.open, lambda: GEOMETRY, ActivityLog(), lambda: None)
    task = asyncio.create_task(driver.run())
    try:
        await until(lambda: driver.state.connected)
        poser = Poser(driver, CONFIG, lambda: None, ActivityLog())
        found = await poser.measure_turn(3)
        assert found / 3 == pytest.approx(4083.0, abs=1.0)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_machine_saves_the_yaw_calibration(machine: Machine) -> None:
    await until(lambda: machine.module.state.connected)
    machine.calibrate_yaw()
    await idle(machine, timeout=60)
    calibration = machine.module_settings
    assert calibration.yaw_calibrated
    # The simulator's gearbox has the nominal ratio.
    assert calibration.half_steps_per_turn == pytest.approx(4075.77, abs=1.0)
    assert machine.module.state.yaw_homed


async def test_tilt_calibration_needs_the_rig_ready(machine: Machine) -> None:
    await until(lambda: machine.module.state.connected)
    with pytest.raises(OperationError, match="Home"):
        machine.calibrate_tilt()


def needle(machine: Machine) -> SimSpecimen:
    view = machine.camera._specimen()  # type: ignore[attr-defined]
    specimen: SimSpecimen = view[0]
    specimen.kind = "needle"
    specimen.offset_mm = (0.2, -0.1, 0.0)
    return specimen


async def test_tilt_calibration_finds_the_switch_angle(machine: Machine) -> None:
    await until(lambda: machine.module.state.connected and machine.camera.state.connected)
    # The app believes the switch trips at 95 degrees; on the simulated rig it trips at 97.
    await machine._save_module(machine.module_settings.model_copy(update={"tilt_switch_deg": 95}))
    machine.home()
    await idle(machine, timeout=30)
    machine.home_module(("tilt", "yaw"))
    await idle(machine, timeout=30)
    specimen = needle(machine)
    machine.set_point("start", round(specimen.focus_ref_mm * machine.axis.steps_per_mm))
    machine.go_to("start")
    await idle(machine, timeout=30)

    machine.calibrate_tilt()
    await idle(machine, timeout=120)
    calibration = machine.module_settings
    assert calibration.tilt_calibrated, machine.log.entries()[-1]
    # Within the gearbox backlash (homing approaches the switch the other way round).
    assert calibration.tilt_switch_deg == pytest.approx(97.0, abs=0.5)
    assert abs(machine.module.tilt_deg()) < 0.2  # and it ends level
