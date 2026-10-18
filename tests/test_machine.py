from __future__ import annotations

import asyncio
import json
from typing import cast

import pytest

from macrorail.machine import Machine, OperationError
from macrorail.sim.camera import SimCamera

from .conftest import homed, idle, until


async def test_commands_need_homing(machine: Machine) -> None:
    with pytest.raises(OperationError, match="Home the rail"):
        machine.go_to("start")
    with pytest.raises(OperationError, match="Home the rail"):
        machine.start_stack()


async def test_home_and_jog(machine: Machine) -> None:
    await homed(machine)
    before = machine.axis.state.position
    machine.jog(40)
    await idle(machine)
    assert machine.axis.state.position == before + 40


async def test_one_operation_at_a_time(machine: Machine) -> None:
    machine.home()
    with pytest.raises(OperationError, match="Busy"):
        machine.jog(4)
    await idle(machine)


async def test_jog_size_is_limited(machine: Machine) -> None:
    with pytest.raises(OperationError, match="limited"):
        machine.jog(machine.axis.steps_per_mm * 6)


async def test_set_and_go_to_points(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4400)
    machine.go_to("end")
    await idle(machine)
    assert machine.axis.state.position == 4400
    assert machine.settings.stack.start == 4000


async def test_approach_ends_moving_in_stack_direction(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4400)
    machine.move_to(5000)  # past the start, so arriving there needs an overshoot
    await idle(machine)
    targets: list[int] = []
    original = machine.axis.move_to

    async def record(target: int, speed: float, accel: float) -> int:
        targets.append(target)
        return await original(target, speed, accel)

    machine.axis.move_to = record  # type: ignore[method-assign]
    machine.go_to("start")
    await idle(machine)
    backlash = round(machine.settings.motion.backlash_mm * machine.axis.steps_per_mm)
    assert targets == [4000 - backlash, 4000]


async def test_points_persist(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    store_path = machine.config.data_dir / "settings.json"
    assert json.loads(store_path.read_text())["stack"]["start"] == 4000


async def test_complete_stack_returns_to_start(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4041)
    machine.start_stack()
    await idle(machine, timeout=20)
    stack = machine.stack
    assert stack is not None
    assert stack.phase == "done"
    assert [s.position for s in stack.shots] == list(range(4000, 4045, 4))
    assert machine.axis.state.position == 4000
    records = list((machine.config.data_dir / "stacks").glob("stack-*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text())["outcome"] == "done"


async def test_pause_and_resume(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4080)
    machine.start_stack()
    stack = machine.stack
    assert stack is not None
    await until(lambda: len(stack.shots) >= 2)
    machine.pause_stack()
    await until(lambda: stack.phase == "paused")
    taken = len(stack.shots)
    await asyncio.sleep(0.3)
    assert len(stack.shots) == taken
    machine.resume_stack()
    await idle(machine, timeout=20)
    assert stack.phase == "done"
    assert len(stack.shots) == stack.plan.count


async def test_stop_returns_to_start(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4400)
    machine.start_stack()
    stack = machine.stack
    assert stack is not None
    await until(lambda: len(stack.shots) >= 3)
    await machine.stop()
    await idle(machine, timeout=20)
    assert stack.phase == "stopped"
    assert len(stack.shots) < stack.plan.count
    assert machine.axis.state.position == 4000


async def test_camera_failure_pauses_and_retakes(machine: Machine) -> None:
    camera = cast(SimCamera, machine.camera)
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4020)
    camera.fail_next_captures = 1
    machine.start_stack()
    stack = machine.stack
    assert stack is not None
    await until(lambda: stack.phase == "camera_error")
    assert stack.error is not None
    machine.resume_stack()
    await idle(machine, timeout=20)
    assert stack.phase == "done"
    assert [s.position for s in stack.shots] == [4000, 4004, 4008, 4012, 4016, 4020]


async def test_stack_needs_camera(machine: Machine) -> None:
    camera = cast(SimCamera, machine.camera)
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4020)
    camera.disconnect("No camera found.")
    with pytest.raises(OperationError, match="No camera"):
        machine.start_stack()


async def test_preview_sweeps_until_stopped(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4400)
    machine.preview_range()
    await until(lambda: machine.axis.state.position >= 4300)
    await until(lambda: machine.axis.state.position <= 4100)
    await machine.stop()
    await idle(machine)
    assert machine.activity == "idle"


async def test_idle_lowers_hold_current_and_motion_restores_it(machine: Machine) -> None:
    await homed(machine)
    currents: list[tuple[int, int]] = []
    original = machine.axis.set_current

    async def record(run_ma: int, hold_ma: int) -> None:
        currents.append((run_ma, hold_ma))
        await original(run_ma, hold_ma)

    machine.axis.set_current = record  # type: ignore[method-assign]
    machine._last_active -= 1000
    await until(lambda: bool(currents))
    assert currents == [(600, 200)]
    machine.jog(4)
    await idle(machine)
    assert currents == [(600, 200), (600, 600)]


async def test_motor_off_requires_homing(machine: Machine) -> None:
    await homed(machine)
    await machine.set_motors(False)
    assert not machine.axis.state.homed
    with pytest.raises(OperationError, match="Home the rail"):
        machine.go_to("start")


async def test_current_change_rejected_while_busy(machine: Machine) -> None:
    machine.home()
    with pytest.raises(OperationError, match="Busy"):
        await machine.update_settings({"motion": {"run_current_ma": 700}})
    await idle(machine)
    await machine.update_settings({"motion": {"run_current_ma": 700}})
    assert machine.settings.motion.run_current_ma == 700


async def test_invalid_settings_are_rejected(machine: Machine) -> None:
    with pytest.raises(OperationError, match="Invalid"):
        await machine.update_settings({"motion": {"hold_current_ma": 900}})
