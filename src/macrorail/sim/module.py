"""A simulated scan-module controller that speaks the real protocol (docs/protocol-module.md).

It models the module Nano's firmware, the two 28BYJ-48 geared steppers and the physical
fork: trapezoidal motion, gearbox backlash, the tilt switch at +97° (past +90°), the yaw
magnet over the KY-024 hall sensor, and unknown starting angles. Like `SimRail`, the host
can't tell it apart from the hardware, apart from `speedup`.
"""

from __future__ import annotations

import math
import queue
import random
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto

FIRMWARE_VERSION = "1.0.0-sim"
PROTOCOL_VERSION = 1
TICK_S = 0.002
LINK_TIMEOUT_S = 2.0
POS_REPORT_S = 0.1
COILS_OFF_S = 0.3  # firmware time: idle this long after a motion, then both coils go off
COIL_SETTLE_S = 0.01  # firmware time: coils hold the position this long before a motor steps
MAX_LINE = 63
MIN_SPEED, MAX_SPEED = 1, 1000  # half-steps/s
MIN_ACCEL, MAX_ACCEL = 1, 4000  # half-steps/s²
POSITION_MAX = 1_000_000  # largest absolute target or limit (half-steps, either sign)
DISTANCE_MAX = 20_000  # largest jog, homing distance or take-up (half-steps)
TILT_UNHOMED_JOG_MAX = 170  # about 15°: tilt jogs before tilt is homed
NUMBER = re.compile(r"[+-]?\d+")  # what the firmware's strtol accepts, as a whole token
LONG_MIN, LONG_MAX = -(2**31), 2**31 - 1  # the firmware's `long`; beyond is ERANGE

# Finding the magnet (HOME YAW), as the firmware does it.
BIN_STEPS = 8  # half-steps averaged into one stored sample
MAX_BINS = 672  # the firmware's sample buffer (bytes): the longest sweep is 5376 half-steps
MIN_BINS = 2  # the shortest sweep covers this many bins (16 half-steps)
NOMINAL_TURN = 4076  # half-steps per output turn the firmware assumes ("more than a turn")
HIST_BUCKETS = 64
MIN_DEVIATION = 40  # ADC counts
ADC_BASELINE = 512  # the KY-024's reading with no field


class _Motion(Enum):
    NONE = auto()
    MOVE = auto()
    JOG = auto()
    HOME_SEEK = auto()
    HOME_BACKOFF = auto()
    HOME_PROBE = auto()
    YAW_SWEEP = auto()
    YAW_TAKEUP = auto()
    YAW_APPROACH = auto()


@dataclass
class _Axis:
    """One motor: the firmware's step counter and the physical gearbox behind it."""

    name: str  # "yaw" or "tilt"
    sign: float  # output degrees per positive half-step: +1 (yaw) or -1 (tilt)
    motor: float  # physical angle the gear train is driven to (degrees, output side)
    output: float  # physical output angle (degrees); lags `motor` inside the backlash
    position: float = 0.0  # firmware half-step counter (float while moving)
    homed: bool = False
    energised: bool = False
    motions: int = 0

    @property
    def pos(self) -> int:
        return round(self.position)


@dataclass
class _Pending:
    id: int = 0
    motion: _Motion = _Motion.NONE
    axis: _Axis | None = None
    abort: str | None = None
    ignore_switch: bool = False  # backing off a pressed switch
    settle_until: float = 0.0  # firmware time: the coils hold the position until then
    fast: float = 0
    slow: float = 0
    clearance: int = 0
    seek_max: int = 0
    release_max: int = 0
    sought: bool = False  # the seek has run (homing that starts pressed backs off first)
    trip_pos: int = 0
    release_pos: int | None = None
    # HOME YAW
    takeup: int = 0
    sweep_start: int = 0
    sweep_steps: int = 0
    sampled: int = -1  # offset of the last reading
    bin_sum: int = 0
    bin_count: int = 0
    samples: list[int] = field(default_factory=list)
    peak: int = 0
    deviation: int = 0
    width: int = 0


@dataclass(frozen=True)
class Peak:
    position: float  # deviation-weighted centroid, in the sweep's half-step frame
    deviation: float  # ADC counts from the baseline
    width: int  # half-steps at half height


def find_peak(samples: list[int], start: int, sweep_steps: int) -> Peak | None:
    """The firmware's magnet search over the stored bytes (ADC/4, one per `BIN_STEPS`), with
    the same integer arithmetic.

    One reading at every position of the sweep, its start included: sample i is the mean of
    the readings at start+8i … start+8i+7, so its centre is start+8i+3.5. Returns None for
    NO_MAGNET.
    """
    n = len(samples)
    if n < MIN_BINS:
        return None
    histogram = [0] * HIST_BUCKETS
    for value in samples:
        histogram[value * HIST_BUCKETS // 256] += 1
    mode = histogram.index(max(histogram))  # the first of equal ones, like the firmware
    in_mode = [v for v in samples if v * HIST_BUCKETS // 256 == mode]
    baseline = (4 * sum(in_mode) + len(in_mode) // 2) // len(in_mode)
    deviation = [abs(4 * v - baseline) for v in samples]

    def run_around(top: int) -> tuple[int, int]:
        """The contiguous samples around `top` at least half as high."""
        lo = hi = top
        while lo > 0 and 2 * deviation[lo - 1] >= deviation[top]:
            lo -= 1
        while hi < n - 1 and 2 * deviation[hi + 1] >= deviation[top]:
            hi += 1
        return lo, hi

    top = max(range(n), key=deviation.__getitem__)  # the first of equal ones
    if deviation[top] < MIN_DEVIATION:
        return None
    lo, hi = run_around(top)
    if sweep_steps > NOMINAL_TURN and (lo == 0 or hi == n - 1):
        # Over a turn the magnet passes twice: use the highest bin whose run lies fully inside.
        best: tuple[int, int, int] | None = None
        for i in range(n):
            if deviation[i] < MIN_DEVIATION:
                continue
            if best is not None and deviation[i] <= deviation[best[0]]:
                continue
            i_lo, i_hi = run_around(i)
            if i_lo > 0 and i_hi < n - 1:
                best = (i, i_lo, i_hi)
        if best is not None:
            top, lo, hi = best
    run = range(lo, hi + 1)
    weight = sum(deviation[i] for i in run)
    centre = sum(deviation[i] * (BIN_STEPS * i + (BIN_STEPS - 1) / 2) for i in run) / weight
    return Peak(start + centre, deviation[top], len(run) * BIN_STEPS)


class SimTransport:
    """The host's end of the simulated USB serial connection (as for `SimRail`)."""

    def __init__(self, module: SimModule) -> None:
        self._module = module
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
        self._module.receive(self, line)

    def close(self) -> None:
        self.closed = True


class SimModule:
    def __init__(
        self,
        steps_per_rev: float = 4075.7728,
        speedup: float = 1.0,
        *,
        tilt_start_deg: float = 20.0,
        yaw_start_deg: float = 123.0,
        tilt_switch_deg: float = 97.0,
        switch_hysteresis_deg: float = 0.6,
        backlash_deg: float = 0.3,
        magnet_yaw_deg: float = 0.0,
        hall_peak_counts: int = 180,
        hall_width_deg: float = 14.0,
        hall_noise_counts: int = 2,
        seed: int = 0,
    ) -> None:
        self.steps_per_rev = steps_per_rev
        self.steps_per_deg = steps_per_rev / 360
        self.speedup = speedup
        self.switch_deg = tilt_switch_deg
        # Like a roller lever: trips at the switch angle, releases only this far below it.
        self.hysteresis = switch_hysteresis_deg
        # Gearbox backlash: the motor turns freely inside this gap before the output follows.
        self.backlash = backlash_deg
        self.magnet_deg = magnet_yaw_deg
        self.magnet_present = True
        self.hall_peak = hall_peak_counts  # negative for the other pole
        self.hall_sigma = hall_width_deg / (2 * math.sqrt(2 * math.log(2)))  # from the FWHM
        self.hall_noise = hall_noise_counts
        self._rng = random.Random(seed)
        self.switch_held = False  # tests: someone holds the switch down by hand
        self.switch_blip = False  # tests: a closing spike too short for the firmware's filter
        self.yaw = _Axis("yaw", 1.0, yaw_start_deg, yaw_start_deg)
        self.tilt = _Axis("tilt", -1.0, tilt_start_deg, tilt_start_deg)
        self.lever_closed = tilt_start_deg >= tilt_switch_deg
        self.clock = 0.0  # firmware time (s), runs `speedup` times faster than the wall
        self._lock = threading.Lock()
        self._transport: SimTransport | None = None
        self._inbox: list[tuple[SimTransport, str]] = []
        self._reset()
        self._thread = threading.Thread(target=self._run, name="sim-module", daemon=True)
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
        with self._lock:
            self._inbox.append((transport, line))

    @property
    def tilt_deg(self) -> float:
        """Physical tilt: 0 = level, + = the insect's back toward the camera."""
        return self.tilt.output

    @property
    def yaw_deg(self) -> float:
        """Physical yaw in [0, 360); the magnet is over the sensor at `magnet_yaw_deg`."""
        return self.yaw.output % 360

    @property
    def coils_on(self) -> bool:
        return self.yaw.energised or self.tilt.energised

    @property
    def motions(self) -> dict[str, int]:
        """Motions started per axis (homings count once)."""
        return {"yaw": self.yaw.motions, "tilt": self.tilt.motions}

    def hold_switch(self, held: bool) -> None:
        with self._lock:
            self.switch_held = held

    def blip_switch(self) -> None:
        """Noise on the switch line: a closing edge that is gone a few µs later."""
        with self._lock:
            self.switch_blip = True

    def remove_magnet(self) -> None:
        with self._lock:
            self.magnet_present = False

    # -- physics ------------------------------------------------------------------------------

    def _hall(self) -> int:
        """One ADC reading of the KY-024 at the current yaw."""
        field_counts = 0.0
        if self.magnet_present:
            offset = (self.yaw.output - self.magnet_deg + 180) % 360 - 180
            field_counts = self.hall_peak * math.exp(-((offset / self.hall_sigma) ** 2) / 2)
        noise = self._rng.randint(-self.hall_noise, self.hall_noise)
        return max(0, min(1023, round(ADC_BASELINE + field_counts + noise)))

    def _turn(self, axis: _Axis, steps: float) -> None:
        """Drive the gear train by `steps` half-steps; the output follows across the backlash."""
        axis.motor += axis.sign * steps / self.steps_per_deg
        axis.output = min(max(axis.output, axis.motor - self.backlash), axis.motor)

    # -- firmware -----------------------------------------------------------------------------

    def _reset(self) -> None:
        self.velocity = 0.0
        self.target = 0
        self.max_speed = 1.0
        self.accel = 1.0
        for axis in (self.yaw, self.tilt):
            axis.position = 0.0
            axis.homed = False
            axis.energised = False
        self.tilt_min = 0
        self.tilt_max = 0
        self.pending = _Pending()
        self.idle_since = self.clock
        self.last_rx = time.monotonic()
        self.last_pos_report = 0.0
        self.switch_reported = self._endstop

    def _identity(self) -> str:
        return f"fw={FIRMWARE_VERSION} proto={PROTOCOL_VERSION} role=module"

    def _emit(self, line: str) -> None:
        if self._transport is not None and not self._transport.closed:
            self._transport.outbox.put(line)

    @property
    def _endstop(self) -> bool:
        return self.lever_closed or self.switch_held

    def _run(self) -> None:
        last = time.monotonic()
        while True:
            time.sleep(TICK_S)
            now = time.monotonic()
            with self._lock:
                inbox, self._inbox = self._inbox, []
                for transport, line in inbox:
                    if transport is self._transport:
                        self.last_rx = now
                        self._handle(line)
                dt = (now - last) * self.speedup
                self.clock += dt
                self._step(dt)
                tripped = self._check_switch()
                if self.pending.motion is not _Motion.NONE:
                    self._service(tripped)
                self._timers(now)
            last = now

    def _timers(self, now: float) -> None:
        p = self.pending
        if p.axis is None:
            if self.coils_on and self.clock - self.idle_since >= COILS_OFF_S:
                self.yaw.energised = self.tilt.energised = False
            return
        if p.abort is None and now - self.last_rx > LINK_TIMEOUT_S:
            self._abort("LINK")
        if now - self.last_pos_report >= POS_REPORT_S:
            self.last_pos_report = now
            self._emit(f"! POS axis={p.axis.name} pos={p.axis.pos}")

    # Motion: constant acceleration toward `target`, braking in time to stop on it.
    def _step(self, dt: float) -> None:
        axis = self.pending.axis
        if axis is None or self.clock < self.pending.settle_until:
            return
        remaining = self.target - axis.position
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
        self._advance(axis, delta)

    def _advance(self, axis: _Axis, delta: float) -> None:
        """Move in pieces of at most one half-step, as the firmware sees every step: the switch
        trips exactly where it is, homing sees it release at the step it does, and HOME YAW
        reads the hall sensor after every half-step."""
        while delta:
            here = axis.position
            edge = math.floor(here) + 1 if delta > 0 else math.ceil(here) - 1
            piece = delta if abs(delta) < abs(edge - here) else edge - here
            before = axis.output
            self._turn(axis, piece)
            if axis is self.tilt and before < self.switch_deg <= axis.output:
                overshoot = axis.output - self.switch_deg  # pushed, so the output turned 1:1
                axis.motor -= overshoot
                axis.output = self.switch_deg
                axis.position = here + piece + overshoot * self.steps_per_deg
                return  # the switch stops the motion before its next step
            delta -= piece
            axis.position = edge if piece == edge - here else here + piece
            if self.pending.motion is _Motion.YAW_SWEEP and piece > 0 and axis.position == edge:
                self._sample(edge)
            if axis is self.tilt and self._released():
                return  # retargeted: decelerate from the next tick

    def _released(self) -> bool:
        """Homing backs off: note the step where the switch released, then add the clearance."""
        self._update_lever()
        p = self.pending
        if p.motion is not _Motion.HOME_BACKOFF or p.release_pos is not None or self._endstop:
            return False
        assert p.axis is not None
        p.release_pos = p.axis.pos
        self.target = p.axis.pos + p.clearance
        return True

    def _sample(self, position: int) -> None:
        """One hall reading at sweep offset 0 … `sweep_steps`; bin i holds offsets 8i … 8i+7."""
        p = self.pending
        taken = position - p.sweep_start
        if p.abort is not None or taken == p.sampled or not 0 <= taken <= p.sweep_steps:
            return
        p.sampled = taken
        while len(p.samples) < taken // BIN_STEPS:
            self._close_bin()
        p.bin_sum += self._hall()
        p.bin_count += 1

    def _close_bin(self) -> None:
        p = self.pending
        if p.bin_count:  # one byte: the rounded mean ADC / 4
            mean = min(255, (p.bin_sum + 2 * p.bin_count) // (4 * p.bin_count))
        else:  # a bin skipped between two readings repeats its predecessor
            mean = p.samples[-1] if p.samples else 128
        p.samples.append(mean)
        p.bin_sum = p.bin_count = 0

    def _check_switch(self) -> bool:
        """Report level changes; return True if the switch stops the current tilt motion: an
        edge (the seek takes any, other motions only one that stays closed), or its level
        while tilt moves toward it."""
        self._update_lever()
        pressed = self._endstop
        edge = pressed and not self.switch_reported
        blip, self.switch_blip = self.switch_blip, False
        if pressed != self.switch_reported:
            self.switch_reported = pressed
            self._emit(f"! SWITCH pressed={int(pressed)}")
        p = self.pending
        if p.axis is not self.tilt:
            return False  # the switch only stops tilt
        if p.motion in (_Motion.MOVE, _Motion.JOG) and p.ignore_switch and not pressed:
            p.ignore_switch = False  # released: armed again
        if p.ignore_switch:
            return False
        toward = self.target < self.tilt.position
        return (toward and pressed) or edge or (blip and p.motion is _Motion.HOME_SEEK)

    def _update_lever(self) -> None:
        if self.tilt.output >= self.switch_deg:
            self.lever_closed = True
        elif self.tilt.output < self.switch_deg - self.hysteresis:
            self.lever_closed = False

    def _running(self, axis: _Axis) -> bool:
        return self.velocity != 0 or axis.pos != self.target

    def _halt(self, axis: _Axis) -> None:
        self.velocity = 0.0
        axis.position = float(axis.pos)
        self.target = axis.pos

    def _service(self, tripped: bool) -> None:
        p = self.pending
        axis = p.axis
        assert axis is not None
        if tripped:
            self._halt(axis)
        done = not self._running(axis)
        linear = p.motion in (_Motion.MOVE, _Motion.JOG)
        if tripped and linear:  # also while aborting: the host must learn that homed is lost
            axis.homed = False
            self._finish("ERR ENDSTOP")
            return
        if p.abort is not None:
            if done or tripped:
                self._finish(f"ERR {p.abort}")
            return
        if p.motion is _Motion.HOME_SEEK:
            if tripped:
                self._start_backoff()
            elif done:
                self._finish("ERR NO_SWITCH")
        elif p.motion is _Motion.HOME_BACKOFF:
            retargeted = self._released()  # also catches a held switch let go (tests)
            if done and not retargeted:
                if p.release_pos is None:
                    self._finish("ERR SWITCH_STUCK")
                elif not p.sought:  # started on the pressed switch: seek its trip point now
                    self._start_seek()
                else:
                    self._start(_Motion.HOME_PROBE, p.trip_pos - p.clearance, p.slow)
        elif p.motion is _Motion.HOME_PROBE:
            if tripped and axis.pos > p.trip_pos + p.clearance // 2:
                self._finish("ERR SWITCH_EARLY")  # noise, or a switch that moved
            elif tripped:
                release = (p.release_pos or 0) - p.trip_pos
                self._zero(axis, f"OK pos=0 release={release}")
            elif done:
                self._finish("ERR NO_SWITCH")
        elif p.motion is _Motion.YAW_SWEEP:
            if done:
                self._end_sweep()
        elif p.motion is _Motion.YAW_TAKEUP:
            if done:
                self._start(_Motion.YAW_APPROACH, p.peak, p.fast)
        elif p.motion is _Motion.YAW_APPROACH:
            if done:
                reply = f"OK pos=0 from={p.peak} dev={p.deviation} width={p.width}"
                self._zero(axis, reply)
        elif linear:
            if tripped:
                self._finish("ERR ENDSTOP")
            elif done:
                self._finish("OK")

    def _end_sweep(self) -> None:
        p = self.pending
        while len(p.samples) < (p.sweep_steps + 1) // BIN_STEPS:  # a partial last bin is dropped
            self._close_bin()
        peak = find_peak(p.samples, p.sweep_start, p.sweep_steps)
        if peak is None:
            self._finish("ERR NO_MAGNET")
            return
        p.peak = p.sweep_start + math.floor(peak.position - p.sweep_start + 0.5)  # lround
        p.deviation = round(peak.deviation)
        p.width = peak.width
        self._start(_Motion.YAW_TAKEUP, p.peak - p.takeup, p.fast)

    def _zero(self, axis: _Axis, reply: str) -> None:
        """A homing succeeded: this point is 0."""
        axis.position = 0.0
        self.target = 0
        axis.homed = True
        self._emit(f"{self.pending.id} {reply}")
        self._idle()

    def _start_seek(self) -> None:
        self.pending.sought = True
        self._start(_Motion.HOME_SEEK, self.tilt.pos - self.pending.seek_max, self.pending.fast)

    def _start_backoff(self) -> None:
        assert self.pending.axis is not None
        self.pending.trip_pos = self.pending.axis.pos
        self.pending.release_pos = None
        target = self.pending.trip_pos + self.pending.release_max
        self._start(_Motion.HOME_BACKOFF, target, self.pending.fast)

    def _start(self, motion: _Motion, target: int, speed: float) -> None:
        self.pending.motion = motion
        self.pending.ignore_switch = motion is _Motion.HOME_BACKOFF
        self.target = target
        self.max_speed = speed

    def _finish(self, status: str) -> None:
        assert self.pending.axis is not None
        self._emit(f"{self.pending.id} {status} pos={self.pending.axis.pos}")
        self._idle()

    def _idle(self) -> None:
        self.pending = _Pending()
        self.idle_since = self.clock

    def _abort(self, reason: str) -> None:
        """Decelerate: retarget to the stopping point, but never past the motion's target (nor
        so past the tilt limits); at once if the motor hasn't started yet."""
        assert self.pending.axis is not None
        self.pending.abort = reason
        here = self.pending.axis.position
        stopping = self.velocity**2 / (2 * self.accel)
        if self.velocity > 0:
            self.target = min(round(here + stopping), self.target)
        elif self.velocity < 0:
            self.target = max(round(here - stopping), self.target)
        else:
            self.target = round(here)

    def _begin(self, request_id: int, axis: _Axis, accel: float) -> _Pending:
        """A motion starts: energise its motor. Coils that were off hold its position for
        COIL_SETTLE_S before it steps."""
        self.pending = _Pending(request_id, axis=axis)
        self.accel = accel
        if not axis.energised:
            axis.energised = True
            self.pending.settle_until = self.clock + COIL_SETTLE_S
        axis.motions += 1
        return self.pending

    # Commands
    def _handle(self, line: str) -> None:
        line = line.rstrip("\r")
        if len(line) > MAX_LINE:
            self._emit("0 ERR TOOLONG")
            return
        tokens = line.split()
        if len(tokens) < 2 or not tokens[0].isdigit() or not 1 <= int(tokens[0]) <= 65535:
            self._emit("0 ERR SYNTAX")
            return
        request_id, name, words = int(tokens[0]), tokens[1], tokens[2:]
        arity = {"INFO": 0, "STATUS": 0, "HALL": 0, "STOP": 0, "LIMITS": 2, "MOVE": 3,
                 "JOG": 3, "HOME": 4}  # fmt: skip
        if name not in arity:
            self._emit(f"{request_id} ERR UNKNOWN")
            return
        axis: _Axis | None = None
        if name in ("LIMITS", "MOVE", "JOG", "HOME"):
            axis = {"YAW": self.yaw, "TILT": self.tilt}.get(words[0]) if words else None
            if axis is None:
                self._emit(f"{request_id} ERR ARG")
                return
            words = words[1:]
        if name == "HOME" and axis is self.tilt:
            arity["HOME"] = 6
        args = [int(t) for t in words if NUMBER.fullmatch(t)]
        numbers = len(args) == len(words) and all(LONG_MIN <= a <= LONG_MAX for a in args)
        if not numbers or len(args) != arity[name] or not self._valid(name, axis, args):
            self._emit(f"{request_id} ERR ARG")
            return
        busy = self.pending.motion is not _Motion.NONE
        if busy and name not in ("INFO", "STATUS", "HALL", "STOP"):
            self._emit(f"{request_id} ERR BUSY")
            return
        handler = getattr(self, f"_cmd_{name.lower()}")
        reply = handler(request_id, *args) if axis is None else handler(request_id, axis, *args)
        if reply is not None:
            self._emit(f"{request_id} {reply}")

    def _valid(self, name: str, axis: _Axis | None, args: list[int]) -> bool:
        """Argument ranges: checked before BUSY, like the firmware."""
        if name == "LIMITS":  # yaw has no limits
            low, high = args
            return axis is self.tilt and -POSITION_MAX <= low <= high <= POSITION_MAX
        if name == "MOVE":
            return abs(args[0]) <= POSITION_MAX and self._check_profile(*args[1:])
        if name == "JOG":
            return abs(args[0]) <= DISTANCE_MAX and self._check_profile(*args[1:])
        if name == "HOME" and axis is self.tilt:
            fast, slow, clearance, max_steps, release_max, accel = args
            profiles = self._check_profile(fast, accel) and self._check_profile(slow, accel)
            distances = 0 < clearance < release_max <= DISTANCE_MAX
            return profiles and distances and 0 < max_steps <= DISTANCE_MAX
        if name == "HOME":
            speed, accel, max_steps, takeup = args
            sweep = MIN_BINS * BIN_STEPS <= max_steps <= MAX_BINS * BIN_STEPS
            return self._check_profile(speed, accel) and sweep and 0 < takeup <= DISTANCE_MAX
        return True

    def _cmd_info(self, _id: int) -> str:
        return f"OK {self._identity()}"

    def _cmd_status(self, _id: int) -> str:
        moving = self.pending.axis.name if self.pending.axis is not None else "none"
        return (
            f"OK yaw={self.yaw.pos} tilt={self.tilt.pos} yhomed={int(self.yaw.homed)} "
            f"thomed={int(self.tilt.homed)} moving={moving} switch={int(self._endstop)} "
            f"hall={self._hall()}"
        )

    def _cmd_hall(self, _id: int) -> str:
        return f"OK hall={self._hall()}"

    def _cmd_stop(self, _id: int) -> str:
        if self.pending.motion is not _Motion.NONE and self.pending.abort is None:
            self._abort("STOPPED")
        return "OK"

    def _cmd_limits(self, _id: int, _axis: _Axis, low: int, high: int) -> str:
        self.tilt_min, self.tilt_max = low, high
        return "OK"

    @staticmethod
    def _check_profile(speed: int, accel: int) -> bool:
        return MIN_SPEED <= speed <= MAX_SPEED and MIN_ACCEL <= accel <= MAX_ACCEL

    def _cmd_home(self, request_id: int, axis: _Axis, *args: int) -> str | None:
        if axis is self.tilt:
            return self._home_tilt(request_id, *args)
        return self._home_yaw(request_id, *args)

    def _home_tilt(self, request_id: int, fast: int, slow: int, clearance: int, max_steps: int,
                   release_max: int, accel: int) -> str | None:  # fmt: skip
        """If the switch is pressed at the start, back off first, then seek and probe."""
        self.tilt.homed = False
        p = self._begin(request_id, self.tilt, accel)
        p.fast, p.slow, p.clearance, p.release_max = fast, slow, clearance, release_max
        p.seek_max = max_steps
        if self._endstop:
            self._start_backoff()
        else:
            self._start_seek()
        return None

    def _home_yaw(self, request_id: int, speed: int, accel: int, max_steps: int,
                  takeup: int) -> str | None:  # fmt: skip
        self.yaw.homed = False
        p = self._begin(request_id, self.yaw, accel)
        p.fast, p.takeup, p.sweep_start, p.sweep_steps = speed, takeup, self.yaw.pos, max_steps
        self._start(_Motion.YAW_SWEEP, p.sweep_start + max_steps, speed)
        self._sample(p.sweep_start)  # offset 0, before the first step
        return None

    def _cmd_move(self, request_id: int, axis: _Axis, target: int, speed: int,
                  accel: int) -> str | None:  # fmt: skip
        if not axis.homed:
            return "ERR NOT_HOMED"
        if axis is self.tilt and not self.tilt_min <= target <= self.tilt_max:
            return "ERR LIMIT"
        return self._begin_linear(request_id, _Motion.MOVE, axis, target, speed, accel)

    def _cmd_jog(self, request_id: int, axis: _Axis, delta: int, speed: int,
                 accel: int) -> str | None:  # fmt: skip
        """Before tilt is homed its jogs are short; once homed, the limits apply."""
        target = axis.pos + delta
        if axis is self.tilt and not axis.homed and abs(delta) > TILT_UNHOMED_JOG_MAX:
            return "ERR LIMIT"
        if axis is self.tilt and axis.homed and not self.tilt_min <= target <= self.tilt_max:
            return "ERR LIMIT"
        return self._begin_linear(request_id, _Motion.JOG, axis, target, speed, accel)

    def _begin_linear(self, request_id: int, motion: _Motion, axis: _Axis, target: int,
                      speed: int, accel: int) -> str | None:  # fmt: skip
        """Like the firmware: with the switch pressed, a tilt move may only start away from it;
        one toward it is refused with PRESSED (homed kept)."""
        pressed = axis is self.tilt and self._endstop
        if pressed and target < axis.pos:
            return f"ERR PRESSED pos={axis.pos}"
        if target == axis.pos:
            return f"OK pos={axis.pos}"
        self._begin(request_id, axis, accel)
        self._start(motion, target, speed)
        self.pending.ignore_switch = pressed
        return None
