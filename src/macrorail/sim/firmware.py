"""A simulated rail controller that speaks the real protocol (docs/protocol.md).

It models the Nano firmware, the TMC2209 and the physical carriage: trapezoidal motion, a
home switch at physical position 0 and an unknown starting position. The host code under
test or in `--sim` mode cannot tell it apart from the hardware, apart from `speedup`.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto

from ..motion.protocol import PROTOCOL_VERSION

FIRMWARE_VERSION = "1.0.0-sim"
TICK_S = 0.002
LINK_TIMEOUT_S = 2.0
POS_REPORT_S = 0.1


class _Motion(Enum):
    NONE = auto()
    MOVE = auto()
    JOG = auto()
    HOME_SEEK = auto()
    HOME_BACKOFF = auto()
    HOME_PROBE = auto()


@dataclass
class _Pending:
    id: int = 0
    motion: _Motion = _Motion.NONE
    interrupt: str | None = None
    fast: float = 0
    slow: float = 0
    accel: float = 0
    backoff: int = 0


class SimTransport:
    """The host's end of the simulated USB serial connection."""

    def __init__(self, rail: SimRail) -> None:
        self._rail = rail
        self.outbox: queue.Queue[str] = queue.Queue()
        self.closed = False

    def read_line(self) -> str | None:
        if self.closed:
            raise OSError("port closed")
        try:
            return self.outbox.get(timeout=0.05)
        except queue.Empty:
            return None

    def write_line(self, line: str) -> None:
        if self.closed:
            raise OSError("port closed")
        self._rail.receive(self, line)

    def close(self) -> None:
        self.closed = True


class SimRail:
    def __init__(
        self,
        *,
        steps_per_mm: int = 400,
        travel_mm: float = 150.0,
        start_mm: float = 30.0,
        speedup: float = 1.0,
    ) -> None:
        self.steps_per_mm = steps_per_mm
        self.travel_steps = travel_mm * steps_per_mm
        self.speedup = speedup
        self.driver_powered = True
        self.physical = start_mm * steps_per_mm  # carriage position, switch at 0 (steps)
        self._lock = threading.Lock()
        self._transport: SimTransport | None = None
        self._inbox: queue.Queue[tuple[SimTransport, str]] = queue.Queue()
        self._reset()
        self._thread = threading.Thread(target=self._run, name="sim-rail", daemon=True)
        self._thread.start()

    # -- host side ----------------------------------------------------------------------------

    def open(self) -> SimTransport:
        """Open the port. Like a real Nano, this resets the controller."""
        with self._lock:
            if self._transport is not None:
                self._transport.closed = True
            self._transport = SimTransport(self)
            self._reset()
            self._emit(f"! READY {self._identity()}")
            return self._transport

    def receive(self, transport: SimTransport, line: str) -> None:
        self._inbox.put((transport, line))

    @property
    def physical_mm(self) -> float:
        return self.physical / self.steps_per_mm

    def cut_driver_power(self) -> None:
        with self._lock:
            self.driver_powered = False

    # -- firmware -----------------------------------------------------------------------------

    def _reset(self) -> None:
        self.position = 0.0  # firmware step counter (float while moving)
        self.velocity = 0.0
        self.target = 0
        self.max_speed = 1.0
        self.accel = 1.0
        self.enabled = False
        self.homed = False
        self.driver_ok = self.driver_powered
        self.min_limit = 0
        self.max_limit = 0
        self.pending = _Pending()
        self.last_rx = time.monotonic()
        self.last_pos_report = 0.0

    def _identity(self) -> str:
        driver = "ok" if self.driver_ok else "missing"
        return f"fw={FIRMWARE_VERSION} proto={PROTOCOL_VERSION} driver={driver}"

    def _emit(self, line: str) -> None:
        if self._transport is not None and not self._transport.closed:
            self._transport.outbox.put(line)

    @property
    def _endstop(self) -> bool:
        return self.physical <= 0

    @property
    def _pos(self) -> int:
        return round(self.position)

    def _run(self) -> None:
        last = time.monotonic()
        while True:
            time.sleep(TICK_S)
            now = time.monotonic()
            with self._lock:
                while not self._inbox.empty():
                    transport, line = self._inbox.get()
                    if transport is self._transport:
                        self.last_rx = now
                        self._handle(line)
                self._step((now - last) * self.speedup)
                self._timers(now)
            last = now

    def _timers(self, now: float) -> None:
        if self.pending.motion is _Motion.NONE:
            if self.driver_ok and not self.driver_powered:
                self.driver_ok = False
                self.enabled = self.homed = False
                self._emit("! FAULT code=driver_lost")
            return
        if self.pending.interrupt is None and now - self.last_rx > LINK_TIMEOUT_S:
            self._interrupt("LINK")
        if now - self.last_pos_report >= POS_REPORT_S:
            self.last_pos_report = now
            self._emit(f"! POS pos={self._pos}")

    # Motion: constant acceleration toward `target`, braking in time to stop on it.
    def _step(self, dt: float) -> None:
        if self.pending.motion is _Motion.NONE:
            return
        remaining = self.target - self.position
        direction = math.copysign(1.0, remaining) if remaining else 0.0
        braking = self.velocity**2 / (2 * self.accel)
        if direction == 0 or (abs(remaining) <= braking and self.velocity * direction > 0):
            self.velocity -= math.copysign(min(abs(self.velocity), self.accel * dt), self.velocity)
        else:
            self.velocity += direction * self.accel * dt
            self.velocity = max(-self.max_speed, min(self.max_speed, self.velocity))
        delta = self.velocity * dt
        if remaining and abs(delta) >= abs(remaining) and self.velocity * remaining > 0:
            delta, self.velocity = remaining, 0.0
        if self.physical > 0 >= self.physical + delta:
            delta = -self.physical  # the switch trips exactly where it is, whatever the tick size
        self.position += delta
        self.physical = min(self.physical + delta, self.travel_steps)
        self._service()

    def _running(self) -> bool:
        return self.velocity != 0 or self._pos != self.target

    def _halt(self) -> None:
        self.velocity = 0.0
        self.position = float(self._pos)
        self.target = self._pos

    def _service(self) -> None:
        p = self.pending
        hit = self._endstop and self.target < self.position
        if hit:
            self._halt()
        done = not self._running()
        linear = p.motion in (_Motion.MOVE, _Motion.JOG)
        if hit and linear:
            self.homed = False
        if p.interrupt is not None:
            if done or hit:
                self._finish(f"ERR {p.interrupt}")
            return
        if p.motion is _Motion.HOME_SEEK:
            if hit:
                self._start(_Motion.HOME_BACKOFF, self._pos + p.backoff, p.fast)
            elif done:
                self._finish("ERR NO_SWITCH")
        elif p.motion is _Motion.HOME_BACKOFF and done:
            if self._endstop:
                self._finish("ERR SWITCH_STUCK")
            else:
                self._start(_Motion.HOME_PROBE, self._pos - 2 * p.backoff, p.slow)
        elif p.motion is _Motion.HOME_PROBE:
            if hit:
                self.position = 0.0
                self.target = 0
                self.homed = True
                self._finish("OK")
            elif done:
                self._finish("ERR NO_SWITCH")
        elif linear:
            if hit:
                self._finish("ERR ENDSTOP")
            elif done:
                self._finish("OK")

    def _start(self, motion: _Motion, target: int, speed: float) -> None:
        self.pending.motion = motion
        self.target = target
        self.max_speed = speed

    def _finish(self, status: str) -> None:
        self._emit(f"{self.pending.id} {status} pos={self._pos}")
        self.pending = _Pending()

    def _interrupt(self, reason: str) -> None:
        """Decelerate: retarget to the stopping point."""
        self.pending.interrupt = reason
        stopping = self.velocity**2 / (2 * self.accel)
        self.target = round(self.position + math.copysign(stopping, self.velocity))

    # Commands
    def _handle(self, line: str) -> None:
        tokens = line.split()
        if len(tokens) < 2 or not tokens[0].isdigit() or not 1 <= int(tokens[0]) <= 65535:
            self._emit("0 ERR SYNTAX")
            return
        request_id, name = int(tokens[0]), tokens[1]
        try:
            args = [int(t) for t in tokens[2:]]
        except ValueError:
            self._emit(f"{request_id} ERR ARG")
            return
        arity = {"INFO": 0, "STATUS": 0, "STOP": 0, "ENABLE": 0, "DISABLE": 0,
                 "CURRENT": 2, "LIMITS": 2, "HOME": 5, "MOVE": 3, "JOG": 3}  # fmt: skip
        if name not in arity:
            self._emit(f"{request_id} ERR UNKNOWN")
            return
        if len(args) != arity[name]:
            self._emit(f"{request_id} ERR ARG")
            return
        busy = self.pending.motion is not _Motion.NONE
        if busy and name not in ("INFO", "STATUS", "STOP"):
            self._emit(f"{request_id} ERR BUSY")
            return
        reply = getattr(self, f"_cmd_{name.lower()}")(request_id, *args)
        if reply is not None:
            self._emit(f"{request_id} {reply}")

    def _cmd_info(self, _id: int) -> str:
        return f"OK {self._identity()}"

    def _cmd_status(self, _id: int) -> str:
        flags = {
            "homed": self.homed,
            "enabled": self.enabled,
            "moving": self.pending.motion is not _Motion.NONE,
            "endstop": self._endstop,
        }
        parts = " ".join(f"{k}={int(v)}" for k, v in flags.items())
        return f"OK pos={self._pos} {parts} driver={'ok' if self.driver_ok else 'missing'}"

    def _cmd_stop(self, _id: int) -> str:
        if self.pending.motion is not _Motion.NONE and self.pending.interrupt is None:
            self._interrupt("STOPPED")
        return "OK"

    def _cmd_enable(self, _id: int) -> str:
        self.driver_ok = self.driver_powered
        if not self.driver_ok:
            return "ERR DRIVER"
        self.enabled = True
        return "OK"

    def _cmd_disable(self, _id: int) -> str:
        self.enabled = self.homed = False
        return "OK"

    def _cmd_current(self, _id: int, run: int, hold: int) -> str:
        return "OK" if 100 <= run <= 1500 and 0 <= hold <= run else "ERR ARG"

    def _cmd_limits(self, _id: int, low: int, high: int) -> str:
        if low > high:
            return "ERR ARG"
        self.min_limit, self.max_limit = low, high
        return "OK"

    def _check_profile(self, speed: int, accel: int) -> bool:
        return 0 < speed <= 4000 and 0 < accel <= 40000

    def _cmd_home(self, request_id: int, fast: int, slow: int, backoff: int, max_steps: int,
                  accel: int) -> str | None:  # fmt: skip
        if not (self._check_profile(fast, accel) and self._check_profile(slow, accel)):
            return "ERR ARG"
        if backoff <= 0 or max_steps <= 0:
            return "ERR ARG"
        if not self.enabled:
            return "ERR DISABLED"
        self.homed = False
        self.accel = accel
        self.pending = _Pending(request_id, fast=fast, slow=slow, accel=accel, backoff=backoff)
        if self._endstop:
            self._start(_Motion.HOME_BACKOFF, self._pos + backoff, fast)
        else:
            self._start(_Motion.HOME_SEEK, self._pos - max_steps, fast)
        return None

    def _cmd_move(self, request_id: int, target: int, speed: int, accel: int) -> str | None:
        if not self._check_profile(speed, accel):
            return "ERR ARG"
        if not self.enabled:
            return "ERR DISABLED"
        if not self.homed:
            return "ERR NOT_HOMED"
        if not self.min_limit <= target <= self.max_limit:
            return "ERR LIMIT"
        if target == self._pos:
            return f"OK pos={self._pos}"
        self._begin_linear(request_id, _Motion.MOVE, target, speed, accel)
        return None

    def _cmd_jog(self, request_id: int, delta: int, speed: int, accel: int) -> str | None:
        target = self._pos + delta
        if not self._check_profile(speed, accel):
            return "ERR ARG"
        if not self.enabled:
            return "ERR DISABLED"
        if self.homed and not self.min_limit <= target <= self.max_limit:
            return "ERR LIMIT"
        if delta < 0 and self._endstop:
            return f"ERR ENDSTOP pos={self._pos}"
        if delta == 0:
            return f"OK pos={self._pos}"
        self._begin_linear(request_id, _Motion.JOG, target, speed, accel)
        return None

    def _begin_linear(self, request_id: int, motion: _Motion, target: int, speed: int,
                      accel: int) -> None:  # fmt: skip
        self.pending = _Pending(request_id)
        self.accel = accel
        self._start(motion, target, speed)
