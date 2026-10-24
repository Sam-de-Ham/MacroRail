"""Finding each controller's serial port.

The rail and the scan module each have an Arduino Nano. Both are CH340 clones without serial
numbers, so their `/dev/serial/by-id` names collide. Each controller says what it is when it
starts: the module's READY carries `role=module`, the rail's carries no role. A port set to
`auto` is therefore found by opening the candidate ports and reading READY.

Opening a port resets that Nano, so a port known to be the other controller's is never
probed, and every port is opened exclusively, so one the other link holds can't be opened at
all. Only USB serial ports are tried. The finder is shared by both controllers' supervisors and
serialises their searches.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Literal

from .link import SerialTransport, Transport
from .protocol import ProtocolError, parse_line

log = logging.getLogger(__name__)

AUTO = "auto"
PROBE_TIMEOUT_S = 3.0  # READY arrives about 1.6 s after the port opens
IGNORE_FOR_S = 60.0  # how long a port that isn't one of ours is left alone

Role = Literal["rail", "module"]


def role_of(ready_data: dict[str, str]) -> Role:
    return "module" if ready_data.get("role") == "module" else "rail"


# USB serial chips found on Arduino Nanos: WCH CH340, FTDI, Silicon Labs CP210x, Arduino.
NANO_USB_VENDORS = {0x1A86, 0x0403, 0x10C4, 0x2341}


def candidate_ports() -> list[str]:
    """Serial ports that may be a Nano. Built-in UARTs (the Pi's Bluetooth one, for instance)
    and other USB devices are never opened, since opening a port resets what is on it."""
    from serial.tools import list_ports

    return sorted(p.device for p in list_ports.comports() if p.vid in NANO_USB_VENDORS)


def probe(port: str, timeout: float = PROBE_TIMEOUT_S) -> Role | None:
    """Open `port`, wait for READY and say which controller it is (None: not one of ours)."""
    transport = SerialTransport(port)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = transport.read_line()
            if not line:
                continue
            try:
                message = parse_line(line)
            except ProtocolError:
                continue  # bootloader noise after the reset
            if getattr(message, "name", None) == "READY":
                return role_of(message.data)
        return None
    finally:
        transport.close()


class PortFinder:
    """Finds and remembers which port each controller is on."""

    def __init__(
        self,
        candidates: Callable[[], list[str]] = candidate_ports,
        probe_port: Callable[[str], Role | None] = probe,
    ) -> None:
        self._candidates = candidates
        self._probe = probe_port
        self._lock = threading.Lock()
        self._fixed: dict[Role, str] = {}  # ports set in the config, as written there
        self._claims: dict[Role, str] = {}  # where each controller was last found
        self._ignored: dict[str, float] = {}  # not ours: port -> when to try it again

    def claim(self, role: Role, port: str) -> None:
        """Record a port fixed in the config, so the other controller's search skips it. It is
        resolved at every search, since its device node can change after a replug."""
        with self._lock:
            self._fixed[role] = port

    def find(self, role: Role) -> str:
        """Search the ports for `role`'s controller. Raises OSError if it isn't plugged in."""
        with self._lock:
            ports = self._candidates()
            present = {_same(port) for port in ports}
            # A claim on a port that is gone (unplugged) no longer protects anything.
            self._claims = {owner: p for owner, p in self._claims.items() if p in present}
            now = time.monotonic()
            tried: set[str] = set()
            # Probing can move a claim (a replug swapped the controllers), which may free a
            # port skipped earlier in the same search, so go round until nothing new is tried.
            while True:
                port = next((p for p in ports if self._may_probe(role, p, tried, now)), None)
                if port is None:
                    break
                real = _same(port)
                tried.add(real)
                try:
                    found = self._probe(port)
                except OSError as exc:  # also: held open by the other controller's link
                    log.debug("could not probe %s: %s", port, exc)
                    continue
                if found is None:
                    self._ignored[real] = now + IGNORE_FOR_S
                    continue
                # One controller per port: a replug may have moved the other one here.
                self._claims = {owner: p for owner, p in self._claims.items() if p != real}
                self._claims[found] = real
                if found == role:
                    return port
            name = "scan module" if role == "module" else "rail"
            raise OSError(f"no {name} controller found ({', '.join(ports) or 'no serial ports'})")

    def _may_probe(self, role: Role, port: str, tried: set[str], now: float) -> bool:
        real = _same(port)
        others = {
            _same(p) for owner, p in (*self._fixed.items(), *self._claims.items()) if owner != role
        }
        return real not in tried and real not in others and self._ignored.get(real, 0.0) <= now


def opener(finder: PortFinder, role: Role, port: str) -> Callable[[], Transport]:
    """The transport factory for one controller: a fixed port, or `auto` (searched afresh
    on every connection, since a reconnect may follow an unplug)."""
    if port != AUTO:
        finder.claim(role, port)
        return lambda: SerialTransport(port)
    return lambda: SerialTransport(finder.find(role))


def _same(port: str) -> str:
    """One name per device: by-path, by-id and /dev/ttyUSB0 links resolve to the same node."""
    return os.path.realpath(port)
