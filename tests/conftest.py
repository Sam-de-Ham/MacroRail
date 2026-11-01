from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from macrorail.config import Config, RailConfig
from macrorail.log import ActivityLog
from macrorail.machine import Machine, build_machine
from macrorail.motion.rail import RailAxis
from macrorail.sim.firmware import SimRail

SPEEDUP = 25.0
# A wait ends as soon as its condition holds; its ceiling only catches a hang. The simulators
# run on the wall clock, so a loaded machine slows them down: ceilings are generous on purpose.
CEILING_S = 120.0
POLL_S = 0.01


async def until(predicate: Callable[[], bool], timeout: float = CEILING_S) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail(f"condition still false after {timeout} s")
        await asyncio.sleep(POLL_S)


def wait(predicate: Callable[[], bool], timeout: float = CEILING_S) -> None:
    """`until` for synchronous tests (the test client, raw protocol lines)."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail(f"condition still false after {timeout} s")
        time.sleep(POLL_S)


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
    # Settle pauses wait for vibration to die down. The simulator has none, and they run on
    # the wall clock, unscaled: without this the 3D tests spend most of their time waiting.
    await m.update_settings({"stack": {"settle_s": 0.0}, "scan": {"settle_s": 0.0}})
    m.update_scan_plan({"settle_s": 0.0})
    task = asyncio.create_task(m.run())
    await until(lambda: m.axis.state.connected)
    yield m
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def idle(machine: Machine, timeout: float = CEILING_S) -> None:
    await until(lambda: not machine.busy, timeout)


async def homed(machine: Machine) -> Machine:
    machine.home()
    await idle(machine)
    assert machine.axis.state.homed
    return machine
