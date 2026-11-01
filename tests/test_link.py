from __future__ import annotations

import asyncio
import queue

import pytest

from macrorail.motion.link import DeviceError, Link, LinkError
from macrorail.motion.protocol import Event
from macrorail.sim.firmware import SimRail

from .conftest import until


class ScriptedTransport:
    """A transport whose replies the test writes by hand."""

    def __init__(self) -> None:
        self.incoming: queue.Queue[str] = queue.Queue()
        self.sent: list[str] = []
        self.closed = False

    def read_line(self) -> str | None:
        if self.closed:
            raise OSError("closed")
        try:
            return self.incoming.get(timeout=0.02)
        except queue.Empty:
            return None

    def write_line(self, line: str) -> None:
        self.sent.append(line)

    def close(self) -> None:
        self.closed = True


async def open_scripted() -> tuple[Link, ScriptedTransport, list[Event]]:
    transport = ScriptedTransport()
    events: list[Event] = []
    transport.incoming.put("garbage from the bootloader")
    transport.incoming.put("! READY fw=1.0.0 proto=2 driver=ok")
    link, _ = await Link.open(lambda: transport, events.append)
    return link, transport, events


async def test_requests_take_turns_on_the_line() -> None:
    link, transport, _ = await open_scripted()
    first = asyncio.create_task(link.request("STATUS"))
    second = asyncio.create_task(link.request("INFO"))
    await until(lambda: bool(transport.sent))
    await asyncio.sleep(0.05)
    assert transport.sent == ["1 STATUS"]  # INFO waits: the controller may be busy answering
    transport.incoming.put("1 OK pos=5")
    assert await first == {"pos": "5"}
    await until(lambda: len(transport.sent) == 2)
    assert transport.sent == ["1 STATUS", "2 INFO"]
    transport.incoming.put("2 OK fw=x")
    assert await second == {"fw": "x"}
    await link.close()


async def test_motion_frees_the_line_and_replies_match_by_id() -> None:
    link, transport, _ = await open_scripted()
    move = asyncio.create_task(link.request("MOVE", 100, 400, 4000, timeout=60, motion=True))
    await until(lambda: len(transport.sent) == 1)
    status = asyncio.create_task(link.request("STATUS"))
    await until(lambda: len(transport.sent) == 2)
    assert transport.sent == ["1 MOVE 100 400 4000", "2 STATUS"]
    transport.incoming.put("2 OK pos=50")
    transport.incoming.put("1 OK pos=100")
    assert await status == {"pos": "50"}
    assert await move == {"pos": "100"}
    await link.close()


async def test_error_reply_raises_device_error() -> None:
    link, transport, _ = await open_scripted()
    request = asyncio.create_task(link.request("MOVE", 1, 2, 3))
    await until(lambda: bool(transport.sent))
    transport.incoming.put("1 ERR NOT_HOMED")
    with pytest.raises(DeviceError) as error:
        await request
    assert error.value.code == "NOT_HOMED"
    assert not link.closed
    await link.close()


async def test_missing_reply_closes_the_link() -> None:
    link, _, _ = await open_scripted()
    with pytest.raises(LinkError, match="no reply"):
        await link.request("STATUS", timeout=0.1)
    assert link.closed
    with pytest.raises(LinkError):
        await link.request("STATUS")


async def test_events_are_delivered() -> None:
    link, transport, events = await open_scripted()
    transport.incoming.put("! POS pos=42")
    await until(lambda: bool(events))
    assert events == [Event("POS", {"pos": "42"})]
    await link.close()


async def test_no_ready_means_no_link() -> None:
    transport = ScriptedTransport()
    with pytest.raises(LinkError, match="READY"):
        await Link.open(lambda: transport, lambda _: None, ready_timeout=0.2)
    assert transport.closed


async def test_controller_stops_motion_when_the_host_goes_quiet() -> None:
    rail = SimRail(start_mm=30.0)  # real time: homing from 30 mm takes ~15 s
    link, _ = await Link.open(rail.open, lambda _: None)
    await link.request("ENABLE")
    with pytest.raises(DeviceError) as error:  # no STATUS polling, so the watchdog fires
        await link.request("HOME", 800, 80, 200, 60000, 2000, 4000, timeout=60)
    assert error.value.code == "LINK"
    await link.close()


class RunningTransport(ScriptedTransport):
    """A controller the open didn't reset: no READY, but it answers INFO."""

    def write_line(self, line: str) -> None:
        super().write_line(line)
        request_id, command = line.split()[:2]
        if command == "INFO":
            self.incoming.put(f"{request_id} OK fw=1.0.0 proto=1 role=module")


async def test_a_controller_that_kept_running_is_asked_instead() -> None:
    transport = RunningTransport()
    link, ready = await Link.open(lambda: transport, lambda event: None, ask_after=0.1)
    assert ready == Event("READY", {"fw": "1.0.0", "proto": "1", "role": "module"})
    assert transport.sent == ["1 INFO"]
    await link.close()


async def test_a_reset_controller_still_says_ready_first() -> None:
    transport = RunningTransport()
    transport.incoming.put("! READY fw=1.0.0 proto=1 role=module")
    link, ready = await Link.open(lambda: transport, lambda event: None, ask_after=30.0)
    assert ready.data["role"] == "module"
    assert transport.sent == []  # no need to ask
    await link.close()
