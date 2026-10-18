from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from macrorail.config import RailConfig
from macrorail.log import ActivityLog
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
