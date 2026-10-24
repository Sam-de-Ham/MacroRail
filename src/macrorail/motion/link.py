"""Request/response link to the rail controller over a line-based transport.

A reader thread turns incoming lines into replies (matched to requests by id) and events.
Because every request carries its own id, a late or missing reply can never be confused
with another one. A request that gets no reply within its timeout means the link is broken,
so the whole link is closed and the owner reconnects.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from .protocol import Event, ProtocolError, Reply, format_request, parse_line

log = logging.getLogger(__name__)

MAX_REQUEST_ID = 65535


class LinkError(Exception):
    """The link is unusable: closed, disconnected or unresponsive."""


class DeviceError(Exception):
    """The controller rejected a request (an `ERR` reply)."""

    def __init__(self, code: str, data: dict[str, str]) -> None:
        super().__init__(code)
        self.code = code
        self.data = data


class Transport(Protocol):
    def read_line(self) -> str | None:
        """Wait briefly for one line. Returns None if none arrived; raises OSError if gone."""

    def write_line(self, line: str) -> None: ...

    def close(self) -> None: ...


class SerialTransport:
    def __init__(self, port: str, baudrate: int = 115200) -> None:
        import serial

        self.port = port
        # Exclusive (flock on Linux): a port another controller's link holds can't be opened
        # a second time, so a port search can never read another link's replies.
        self._serial = serial.Serial(port, baudrate, timeout=0.1, write_timeout=1.0, exclusive=True)
        self._buffer = bytearray()

    def read_line(self) -> str | None:
        self._buffer += self._serial.read_until(b"\n")
        if not self._buffer.endswith(b"\n"):
            return None
        line = self._buffer.decode("ascii", errors="replace").strip()
        self._buffer.clear()
        return line

    def write_line(self, line: str) -> None:
        self._serial.write(line.encode("ascii") + b"\n")

    def close(self) -> None:
        self._serial.close()


class Link:
    def __init__(
        self, transport: Transport, on_event: Callable[[Event], None], name: str = "rail"
    ) -> None:
        self._transport = transport
        self._on_event = on_event
        self._loop = asyncio.get_running_loop()
        self._pending: dict[int, asyncio.Future[Reply]] = {}
        self._line = asyncio.Lock()
        self._last_id = 0
        self._ready: asyncio.Future[Event] = self._loop.create_future()
        self._closed = asyncio.Event()
        self._close_reason = LinkError("link closed")
        self._stopping = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, name=f"{name}-link", daemon=True)
        self._reader.start()

    @classmethod
    async def open(
        cls,
        open_transport: Callable[[], Transport],
        on_event: Callable[[Event], None],
        ready_timeout: float = 5.0,
        name: str = "rail",
    ) -> tuple[Link, Event]:
        """Open the transport and wait for the controller's READY event."""
        transport = await asyncio.to_thread(open_transport)
        link = cls(transport, on_event, name)
        try:
            ready = await asyncio.wait_for(link._ready, ready_timeout)
        except TimeoutError:
            await link.close()
            raise LinkError("controller did not report READY") from None
        return link, ready

    @property
    def port(self) -> str | None:
        """The serial port in use (None for the simulator)."""
        return getattr(self._transport, "port", None)

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    async def wait_closed(self) -> LinkError:
        await self._closed.wait()
        return self._close_reason

    async def request(
        self, command: str, *args: int | str, timeout: float = 1.0, motion: bool = False
    ) -> dict[str, str]:
        """Send a request and return its reply data. Raises DeviceError or LinkError.

        The line is half-duplex around the controller's driver UART, which blocks the Nano's
        interrupts and would drop incoming bytes: a request holds the line until its reply
        arrives. A `motion` request replies only when the motion ends, and releases the line
        once sent, so STATUS and STOP can follow (the controller never uses the driver UART
        while moving).
        """
        async with self._line:
            if self.closed:
                raise self._close_reason
            request_id = self._next_id()
            future: asyncio.Future[Reply] = self._loop.create_future()
            self._pending[request_id] = future
            try:
                self._transport.write_line(format_request(request_id, command, *args))
            except OSError as exc:
                self._fail(LinkError(f"write failed: {exc}"))
            if not motion:
                reply = await self._reply(command, request_id, future, timeout)
        if motion:
            reply = await self._reply(command, request_id, future, timeout)
        if not reply.ok:
            raise DeviceError(reply.code or "UNKNOWN", reply.data)
        return reply.data

    async def _reply(
        self, command: str, request_id: int, future: asyncio.Future[Reply], timeout: float
    ) -> Reply:
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            self._fail(LinkError(f"no reply to {command} within {timeout:.1f} s"))
            raise self._close_reason from None
        finally:
            self._pending.pop(request_id, None)

    def abort(self, reason: str) -> None:
        """Close the link from the event loop thread, failing anything in flight."""
        self._fail(LinkError(reason))

    async def close(self) -> None:
        self._fail(LinkError("link closed"))
        await asyncio.to_thread(self._reader.join, 1.0)

    def _next_id(self) -> int:
        while True:
            self._last_id = self._last_id % MAX_REQUEST_ID + 1
            if self._last_id not in self._pending:
                return self._last_id

    def _read_loop(self) -> None:
        try:
            while not self._stopping.is_set():
                line = self._transport.read_line()
                if line:
                    self._loop.call_soon_threadsafe(self._handle_line, line)
        except Exception as exc:  # any transport failure ends the link
            if not self._stopping.is_set():
                with contextlib.suppress(RuntimeError):  # loop already closed
                    self._loop.call_soon_threadsafe(
                        self._fail, LinkError(f"connection lost: {exc}")
                    )

    def _handle_line(self, line: str) -> None:
        try:
            message = parse_line(line)
        except ProtocolError:
            log.debug("ignoring unparseable line %r", line)  # e.g. bootloader noise after reset
            return
        if isinstance(message, Reply):
            future = self._pending.get(message.id)
            if future is None:
                log.warning("reply for unknown request: %r", line)
            elif not future.done():
                future.set_result(message)
        elif message.name == "READY" and not self._ready.done():
            self._ready.set_result(message)
        else:
            self._on_event(message)

    def _fail(self, reason: LinkError) -> None:
        if self.closed:
            return
        self._close_reason = reason
        self._closed.set()
        self._stopping.set()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(reason)
        if not self._ready.done():
            self._ready.set_exception(reason)
            self._ready.exception()  # mark retrieved; open() reports its own error
        try:
            self._transport.close()
        except OSError as exc:
            log.debug("error closing transport: %s", exc)
