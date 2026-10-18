from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from macrorail.config import Config, RailConfig
from macrorail.log import ActivityLog
from macrorail.machine import Machine, build_machine
from macrorail.motion.rail import RailAxis
from macrorail.sim.firmware import SimRail

SPEEDUP = 25.0


async def until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)


@pytest.fixture
def sim_rail() -> SimRail:
    return SimRail(speedup=SPEEDUP, start_mm=30.0)


@pytest.fixture
async def rail(sim_rail: SimRail) -> AsyncIterator[RailAxis]:
    axis = RailAxis(RailConfig(port="sim"), sim_rail.open, ActivityLog(), lambda: None)
    task = asyncio.create_task(axis.run())
    await until(lambda: axis.state.connected)
    yield axis
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.fixture
async def machine(tmp_path: Path) -> AsyncIterator[Machine]:
    config = Config(rail=RailConfig(port="sim"), data_dir=tmp_path)
    m = build_machine(config, sim=True, sim_speedup=SPEEDUP)
    await m.update_settings({"stack": {"settle_s": 0.0}})
    task = asyncio.create_task(m.run())
    await until(lambda: m.axis.state.connected)
    yield m
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def idle(machine: Machine, timeout: float = 10.0) -> None:
    await until(lambda: not machine.busy, timeout)


async def homed(machine: Machine) -> Machine:
    machine.home()
    await idle(machine)
    assert machine.axis.state.homed
    return machine
