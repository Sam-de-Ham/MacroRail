from __future__ import annotations

import asyncio

import pytest

from macrorail.config import RailConfig
from macrorail.log import ActivityLog
from macrorail.motion.base import AxisError, MotionInterrupted
from macrorail.motion.protocol import Event
from macrorail.motion.rail import RailAxis
from macrorail.sim.firmware import SimRail

from .conftest import until

SPEED = 800.0  # steps/s (2 mm/s)
ACCEL = 4000.0  # steps/s² (10 mm/s²)


async def test_connects_and_reports_firmware(rail: RailAxis) -> None:
    state = rail.state
    assert state.connected
    assert state.driver_ok
    assert state.firmware == "1.0.0-sim"
    assert not state.homed
    assert state.problem is None


async def test_absolute_moves_require_homing(rail: RailAxis) -> None:
    await rail.enable()
    with pytest.raises(AxisError, match="Home the rail"):
        await rail.move_to(1000, SPEED, ACCEL)


async def test_home_parks_with_the_switch_released(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    await rail.home()
    assert rail.state.homed
    # The simulated switch releases 0.6 mm out, so the park lands past it (+0.5 mm clearance).
    # The release is measured to within one simulator tick at this speed-up (~30 steps).
    assert 240 + 200 <= rail.state.position <= 240 + 200 + 30
    assert sim_rail.physical == pytest.approx(rail.state.position, abs=1)
    await until(lambda: not rail.state.endstop)


async def test_move_reaches_exact_target(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    await rail.home()
    assert await rail.move_to(4001, SPEED, ACCEL) == 4001
    assert sim_rail.physical == pytest.approx(4001, abs=1e-6)


async def test_move_outside_limits_is_refused(rail: RailAxis) -> None:
    await rail.enable()
    await rail.home()
    with pytest.raises(AxisError, match="outside"):
        await rail.move_to(rail.max_position + 1, SPEED, ACCEL)


async def test_jog_into_switch_stops_and_clears_homed(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    with pytest.raises(AxisError, match="home switch"):
        await rail.jog(-round(sim_rail.physical) - 400, SPEED, ACCEL)
    assert sim_rail.physical == pytest.approx(0, abs=2)
    assert not rail.state.homed


async def test_stop_interrupts_motion(rail: RailAxis) -> None:
    await rail.enable()
    await rail.home()
    move = asyncio.create_task(rail.move_to(rail.max_position, SPEED, ACCEL))
    await until(lambda: rail.state.position > 2000)
    await rail.stop()
    with pytest.raises(MotionInterrupted):
        await move
    assert rail.min_position < rail.state.position < rail.max_position


async def test_disable_requires_homing_again(rail: RailAxis) -> None:
    await rail.enable()
    await rail.home()
    await rail.disable()
    assert not rail.state.homed
    assert not rail.state.enabled


async def test_controller_restart_reconnects_unhomed(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    await rail.home()
    sim_rail.open()  # another open resets the controller and steals the port
    await until(lambda: not rail.state.connected)
    await until(lambda: rail.state.connected, timeout=10)
    assert not rail.state.homed


async def test_driver_power_loss_is_reported(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    sim_rail.cut_driver_power()
    await until(lambda: not rail.state.driver_ok)
    assert rail.state.problem is not None
    assert "12 V" in rail.state.problem
    with pytest.raises(AxisError, match="12 V"):
        await rail.enable()


async def test_switch_stops_motion_in_any_direction(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    await rail.home()
    move = asyncio.create_task(rail.move_to(rail.max_position, SPEED, ACCEL))  # away from it
    await until(lambda: rail.state.position > 2000)
    sim_rail.hold_switch(True)  # e.g. a cable snagging the lever
    with pytest.raises(AxisError, match="home switch"):
        await move
    assert not rail.state.homed


async def test_switch_state_follows_the_switch(rail: RailAxis, sim_rail: SimRail) -> None:
    sim_rail.hold_switch(True)
    await until(lambda: rail.state.endstop)
    sim_rail.hold_switch(False)
    await until(lambda: not rail.state.endstop)


def test_switch_events_update_state_without_polling() -> None:
    axis = RailAxis(RailConfig(port="sim"), SimRail().open, ActivityLog(), lambda: None)
    axis._on_event(Event("SWITCH", {"pressed": "1"}))
    assert axis.state.endstop
    axis._on_event(Event("SWITCH", {"pressed": "0"}))
    assert not axis.state.endstop


async def test_pressed_switch_allows_only_backing_off(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    sim_rail.hold_switch(True)
    await until(lambda: rail.state.endstop)
    with pytest.raises(AxisError, match="home switch"):
        await rail.jog(-40, SPEED, ACCEL)
    position = await rail.jog(400, SPEED, ACCEL)  # backing off is not stopped by the switch
    assert position == 400


async def test_homing_reports_a_stuck_switch(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    sim_rail.hold_switch(True)
    await until(lambda: rail.state.endstop)
    with pytest.raises(AxisError, match="stayed pressed"):
        await rail.home()


async def test_switch_rearms_after_release(rail: RailAxis, sim_rail: SimRail) -> None:
    await rail.enable()
    await rail.home()
    sim_rail.hold_switch(True)
    await until(lambda: rail.state.endstop)
    move = asyncio.create_task(rail.move_to(rail.max_position, SPEED, ACCEL))  # starts pressed
    await until(lambda: rail.state.position > 2000)
    sim_rail.hold_switch(False)  # released: the switch must be armed again
    await until(lambda: not rail.state.endstop)
    sim_rail.hold_switch(True)
    with pytest.raises(AxisError, match="home switch"):
        await move
    assert rail.state.position < rail.max_position
