"""The simulated scan module, driven through raw protocol lines (docs/protocol-module.md)."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from macrorail.sim.module import SimModule, SimTransport, find_peak

SPEEDUP = 40.0
HOME_TILT = "HOME TILT 800 100 30 3000 200 4000"
HOME_YAW = "HOME YAW 800 4000 5300 60"  # about 1.3 turns
STEPS_PER_REV = 4075.7728


class Client:
    """Raw lines to and from the module; events are kept apart from replies."""

    def __init__(self, module: SimModule) -> None:
        self.transport: SimTransport = module.open()
        self.events: list[str] = []
        self.next_id = 1
        self.ready = self.read()

    def read(self, timeout: float = 5.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.transport.read_line()
            if line is not None:
                return line
        raise TimeoutError("no line from the module")

    def send(self, command: str) -> int:
        request_id = self.next_id
        self.next_id += 1
        self.transport.write_line(f"{request_id} {command}")
        return request_id

    def reply(self, request_id: int, timeout: float = 5.0) -> str:
        """The reply to `request_id`, without its id."""
        deadline = time.monotonic() + timeout
        while True:
            line = self.read(deadline - time.monotonic())
            if line.startswith("! "):
                self.events.append(line)
            elif line.startswith(f"{request_id} "):
                return line.split(" ", 1)[1]

    def request(self, command: str, timeout: float = 5.0) -> str:
        return self.reply(self.send(command), timeout)

    def data(self, command: str) -> dict[str, str]:
        reply = self.request(command)
        assert reply.startswith("OK"), reply
        return dict(token.split("=", 1) for token in reply.split()[1:])


def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


@pytest.fixture
def module() -> SimModule:
    return SimModule(speedup=SPEEDUP)


@pytest.fixture
def client(module: SimModule) -> Client:
    return Client(module)


def homed_tilt(client: Client) -> None:
    assert client.request(HOME_TILT).startswith("OK pos=0")
    assert client.request("LIMITS TILT 0 1400") == "OK"


# -- identity and immediate commands ----------------------------------------------------------


def test_ready_and_info_carry_the_module_role(client: Client) -> None:
    assert client.ready == "! READY fw=1.0.0-sim proto=1 role=module"
    assert client.data("INFO") == {"fw": "1.0.0-sim", "proto": "1", "role": "module"}


def test_status_reports_both_axes(client: Client) -> None:
    status = client.data("STATUS")
    assert set(status) == {"yaw", "tilt", "yhomed", "thomed", "moving", "switch", "hall"}
    assert status["yaw"] == status["tilt"] == "0"
    assert status["yhomed"] == status["thomed"] == status["switch"] == "0"
    assert status["moving"] == "none"
    assert 500 <= int(status["hall"]) <= 524  # away from the magnet: the baseline plus noise


def test_hall_rises_over_the_magnet() -> None:
    module = SimModule(speedup=SPEEDUP, yaw_start_deg=0.0)
    client = Client(module)
    assert int(client.data("HALL")["hall"]) > 512 + 150
    module.remove_magnet()
    assert abs(int(client.data("HALL")["hall"]) - 512) <= 2


@pytest.mark.parametrize(
    "line",
    [
        "MOVE ROLL 10 100 100",  # unknown axis
        "JOG 10 100 100",  # no axis
        "JOG YAW 10 0 100",  # speed below range
        "JOG YAW 10 1001 100",  # speed above range
        "JOG YAW 10 100 4001",  # accel above range
        "JOG YAW 10 100",  # missing argument
        "JOG YAW ten 100 100",
        "HOME YAW 800 4000 5377 60",  # sweep longer than the sample buffer (672 bins)
        "HOME YAW 800 4000 0 60",
        "HOME YAW 800 4000 15 60",  # under two bins
        "HOME YAW 800 4000 5300 20001",  # takeup over the distance bound
        "HOME TILT 800 100 30 20001 200 4000",  # max over the distance bound
        "JOG YAW 20001 100 100",  # over the distance bound
        "MOVE YAW -1000001 100 100",  # over the position bound
        "JOG YAW 99999999999 100 100",  # out of range for the firmware's long
        "JOG YAW 1_0 100 100",
        "LIMITS TILT 0 1000001",
        "HOME YAW 800 4000 5300 0",  # no takeup
        "HOME YAW 800 4000 5300",
        "HOME TILT 800 100 30 3000 20 4000",  # release_max not above the clearance
        "LIMITS YAW 0 100",  # yaw has no limits
        "LIMITS TILT 100 0",
    ],
)
def test_bad_arguments(client: Client, line: str) -> None:
    assert client.request(line) == "ERR ARG"


def test_malformed_lines(client: Client) -> None:
    client.transport.write_line("STATUS")
    assert client.read() == "0 ERR SYNTAX"
    client.transport.write_line("1 " + "X" * 70)
    assert client.read() == "0 ERR TOOLONG"
    assert client.request("DANCE") == "ERR UNKNOWN"
    assert client.request("STATUS\r").startswith("OK")


def test_one_motion_at_a_time_across_both_axes(client: Client) -> None:
    jog = client.send("JOG YAW 4000 200 1000")
    assert client.request("JOG TILT 10 100 100") == "ERR BUSY"
    assert client.request("JOG TILT 10 0 100") == "ERR ARG"  # arguments are checked first
    assert client.request("HOME YAW 800 4000 8 60") == "ERR ARG"
    assert client.request("LIMITS TILT 10 0") == "ERR ARG"
    assert client.request("LIMITS TILT 0 10") == "ERR BUSY"
    assert client.data("STATUS")["moving"] == "yaw"
    assert client.request("HALL").startswith("OK hall=")
    assert client.request("STOP") == "OK"
    assert client.reply(jog).startswith("ERR STOPPED pos=")


# -- motion -----------------------------------------------------------------------------------


def test_jog_works_before_homing_and_turns_the_output(module: SimModule, client: Client) -> None:
    yaw, tilt = module.yaw_deg, module.tilt_deg
    assert client.request("JOG YAW 1132 1000 4000") == "OK pos=1132"
    # The gearbox starts out with its backlash on the other side, so the output lags it.
    assert module.yaw_deg == pytest.approx(yaw + 100 - 0.3, abs=0.05)
    assert client.request("JOG TILT 113 1000 4000") == "OK pos=113"  # positive: tilt goes down
    assert module.tilt_deg == pytest.approx(tilt - 10, abs=0.05)
    assert module.motions == {"yaw": 1, "tilt": 1}
    assert any(e.startswith("! POS axis=yaw pos=") for e in client.events)


def test_move_needs_homing(client: Client) -> None:
    assert client.request("MOVE YAW 100 500 1000") == "ERR NOT_HOMED"
    assert client.request("MOVE TILT 100 500 1000") == "ERR NOT_HOMED"


def test_stop_decelerates_and_reports(client: Client) -> None:
    jog = client.send("JOG YAW 20000 1000 1000")
    time.sleep(0.05)
    client.request("STOP")
    reply = client.reply(jog)
    assert reply.startswith("ERR STOPPED pos=")
    assert 0 < int(reply.split("=")[1]) < 20000


def test_coils_switch_off_after_idle() -> None:
    module = SimModule(speedup=1.0)  # real time, to see the 300 ms
    client = Client(module)
    assert not module.coils_on
    jog = client.send("JOG TILT 150 1000 4000")
    wait_until(lambda: module.coils_on)
    client.reply(jog)
    assert module.coils_on  # still on just after the move
    wait_until(lambda: not module.coils_on, timeout=1.0)


def test_stop_right_away_and_never_past_the_target(client: Client) -> None:
    jog = client.send("JOG YAW 5000 1000 1000")
    client.request("STOP")  # before the first step: stops where it is
    assert client.reply(jog) == "ERR STOPPED pos=0"
    for _ in range(3):
        jog = client.send("JOG YAW 300 1000 1000")
        wait_until(lambda: client.data("STATUS")["yaw"] not in ("0", "300"))
        client.request("STOP")
        assert int(client.reply(jog).split("pos=")[1]) <= 300
        assert client.request("JOG YAW -300 1000 4000").startswith("OK")


def test_watchdog_stops_motion_when_the_host_goes_quiet() -> None:
    module = SimModule(speedup=1.0)  # the watchdog runs on the wall clock
    client = Client(module)
    jog = client.send("JOG YAW 20000 200 1000")
    reply = client.reply(jog, timeout=5)
    assert reply.startswith("ERR LINK pos=")


# -- tilt -------------------------------------------------------------------------------------


def test_tilt_homing_zeroes_at_the_switch(module: SimModule, client: Client) -> None:
    reply = client.request(HOME_TILT)
    assert reply.startswith("OK pos=0 release=")
    # The release is the lever's hysteresis plus the gearbox backlash taken up on the way back.
    release = int(reply.split("release=")[1])
    assert release == pytest.approx((0.6 + 0.3) * STEPS_PER_REV / 360, abs=2)
    assert module.tilt_deg == pytest.approx(97.0, abs=0.01)
    status = client.data("STATUS")
    assert (status["thomed"], status["tilt"], status["switch"]) == ("1", "0", "1")
    assert "! SWITCH pressed=1" in client.events


def test_tilt_homing_repeats_from_anywhere() -> None:
    angles = []
    for start in (-30.0, 50.0, 97.2):  # 97.2: starts on the pressed switch
        module = SimModule(speedup=SPEEDUP, tilt_start_deg=start)
        assert Client(module).request(HOME_TILT).startswith("OK pos=0")
        angles.append(module.tilt_deg)
    assert max(angles) - min(angles) < 0.01


def test_tilt_homing_ignores_noise_on_the_probe(module: SimModule, client: Client) -> None:
    home = client.send("HOME TILT 800 20 30 3000 200 4000")
    wait_until(lambda: module.pending.motion.name == "HOME_PROBE")
    module.blip_switch()  # too short for the filter: the probe goes on to the switch
    assert client.reply(home).startswith("OK pos=0")
    assert module.tilt_deg == pytest.approx(97.0, abs=0.01)


def test_tilt_homing_refuses_an_early_probe_contact(module: SimModule, client: Client) -> None:
    home = client.send("HOME TILT 800 10 30 3000 200 4000")
    wait_until(lambda: module.pending.motion.name == "HOME_PROBE")
    module.hold_switch(True)  # well before where the seek tripped it (clearance/2 = 15)
    try:
        assert client.reply(home).startswith("ERR SWITCH_EARLY pos=")
    finally:
        module.hold_switch(False)
    assert client.data("STATUS")["thomed"] == "0"


def test_tilt_homing_without_a_switch_in_reach(client: Client) -> None:
    assert client.request("HOME TILT 800 100 30 300 200 4000").startswith("ERR NO_SWITCH")
    assert client.data("STATUS")["thomed"] == "0"


def test_tilt_limits(module: SimModule, client: Client) -> None:
    homed_tilt(client)
    assert client.request("MOVE TILT 1401 500 1000") == "ERR LIMIT"
    assert client.request("MOVE TILT -1 500 1000") == "ERR LIMIT"
    assert client.request("JOG TILT 1500 500 1000") == "ERR LIMIT"
    assert client.request("MOVE TILT 1132 1000 4000") == "OK pos=1132"
    assert module.tilt_deg == pytest.approx(97.0 - 100 + 0.3, abs=0.05)  # backlash on reversal


def test_switch_stops_a_tilt_move_and_clears_homed(module: SimModule, client: Client) -> None:
    homed_tilt(client)
    assert client.request("MOVE TILT 500 1000 4000") == "OK pos=500"
    module.hold_switch(True)
    try:
        reply = client.request("JOG TILT 300 500 1000")
    finally:
        module.hold_switch(False)
    # Starting on the pressed switch and moving away ignores it until it releases.
    assert reply == "OK pos=800"
    jog = client.send("JOG TILT -400 200 1000")
    time.sleep(0.01)
    module.hold_switch(True)
    try:
        assert client.reply(jog).startswith("ERR ENDSTOP pos=")
    finally:
        module.hold_switch(False)
    assert client.data("STATUS")["thomed"] == "0"


def test_a_switch_hit_while_stopping_still_reports_endstop() -> None:
    module = SimModule(speedup=1.0)  # real time, to press the switch while it decelerates
    client = Client(module)
    homed_tilt(client)
    assert client.request("MOVE TILT 600 1000 4000", timeout=10) == "OK pos=600"
    move = client.send("MOVE TILT 100 200 100")
    wait_until(lambda: int(client.data("STATUS")["tilt"]) < 590, timeout=3.0)
    assert client.request("STOP") == "OK"
    module.hold_switch(True)
    try:
        assert client.reply(move).startswith("ERR ENDSTOP pos=")  # not STOPPED: homed is lost
    finally:
        module.hold_switch(False)
    assert client.data("STATUS")["thomed"] == "0"


def test_a_tilt_move_toward_the_pressed_switch_is_refused() -> None:
    module = SimModule(speedup=SPEEDUP, tilt_start_deg=97.2)  # resting on the switch
    client = Client(module)
    assert client.request("JOG TILT -10 500 1000") == "ERR PRESSED pos=0"
    assert module.tilt_deg == 97.2
    assert client.request("JOG YAW -10 500 1000") == "OK pos=-10"  # yaw doesn't care
    assert client.request("JOG TILT 10 500 1000") == "OK pos=10"  # away from it is fine


def test_a_refused_move_keeps_tilt_homed(client: Client) -> None:
    homed_tilt(client)  # homing ends on the pressed switch, at 0
    assert client.request("LIMITS TILT -100 1400") == "OK"
    assert client.request("MOVE TILT -10 500 1000") == "ERR PRESSED pos=0"
    status = client.data("STATUS")
    assert (status["thomed"], status["switch"]) == ("1", "1")


def test_unhomed_tilt_jogs_are_short(client: Client) -> None:
    assert client.request("JOG TILT 171 500 1000") == "ERR LIMIT"
    assert client.request("JOG TILT -171 500 1000") == "ERR LIMIT"
    assert client.request("JOG TILT 170 500 1000") == "OK pos=170"
    homed_tilt(client)
    assert client.request("JOG TILT 400 500 1000") == "OK pos=400"  # homed: the limits apply


def test_a_noise_blip_does_not_stop_a_move(module: SimModule, client: Client) -> None:
    jog = client.send("JOG TILT 170 100 1000")
    time.sleep(0.01)
    module.blip_switch()
    assert client.reply(jog) == "OK pos=170"


def test_jogging_into_the_switch() -> None:
    module = SimModule(speedup=SPEEDUP, tilt_start_deg=90.0)  # 7° from it: within a short jog
    client = Client(module)
    assert client.request("JOG TILT -170 1000 4000").startswith("ERR ENDSTOP pos=")
    assert module.tilt_deg == pytest.approx(97.0, abs=0.01)


# -- yaw --------------------------------------------------------------------------------------


def home_yaw(module: SimModule) -> tuple[dict[str, str], float]:
    reply = Client(module).request(HOME_YAW)
    assert reply.startswith("OK pos=0"), reply
    return dict(t.split("=") for t in reply.split()[1:]), module.yaw_deg


def angle_between(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def test_yaw_homing_finds_the_magnet_repeatably() -> None:
    half_step = 360 / STEPS_PER_REV
    angles = []
    for start in (123.0, 0.0, 3.0, 300.0, 355.0):  # on the peak, just past it, before it
        reply, angle = home_yaw(SimModule(speedup=SPEEDUP, yaw_start_deg=start))
        assert int(reply["dev"]) == pytest.approx(180, abs=8)
        assert int(reply["width"]) == pytest.approx(14 * STEPS_PER_REV / 360, abs=16)
        angles.append(angle)
    assert all(angle_between(a, angles[0]) <= 2 * half_step for a in angles)
    assert angle_between(angles[0], 0.0) <= 2 * half_step  # and it's the magnet


def test_two_yaw_homings_measure_the_steps_per_turn(module: SimModule) -> None:
    client = Client(module)
    assert client.request(HOME_YAW).startswith("OK pos=0")
    reply = client.request(HOME_YAW)  # starts on the peak, so the next one is a turn on
    found = int(reply.split("from=")[1].split()[0])
    assert found == pytest.approx(STEPS_PER_REV, abs=3)


def test_yaw_homing_without_a_magnet(module: SimModule, client: Client) -> None:
    module.remove_magnet()
    assert client.request(HOME_YAW).startswith("ERR NO_MAGNET pos=")
    assert client.data("STATUS")["yhomed"] == "0"
    assert client.request("MOVE YAW 0 500 1000") == "ERR NOT_HOMED"


def test_yaw_move_after_homing(module: SimModule, client: Client) -> None:
    assert client.request(HOME_YAW).startswith("OK pos=0")
    assert client.request("MOVE YAW 1019 1000 4000") == "OK pos=1019"  # a quarter turn
    assert angle_between(module.yaw_deg, 90.0) < 0.3


def test_find_peak_skips_a_peak_cut_off_by_the_sweep() -> None:
    flat = [128] * 700
    flat[:5] = [175, 170, 160, 140, 130]  # a truncated peak at the start
    for i, v in enumerate([140, 160, 172, 160, 140]):
        flat[500 + i] = v
    peak = find_peak(flat, 0, 5600)
    assert peak is not None
    assert peak.position == pytest.approx(8 * 502 + 3.5, abs=0.5)
    # Under a turn, or with no other peak, the cut-off one is used.
    under_turn = find_peak(flat, 0, 4000)
    assert under_turn is not None
    assert under_turn.position < 24
    only = find_peak(flat[:400], 0, 5600)
    assert only is not None
    assert only.position < 24
    assert find_peak([128] * 700, 0, 5600) is None
    assert find_peak([200], 0, 16) is None  # too few bins


def test_find_peak_tries_every_lower_peak() -> None:
    samples = [128] * 700
    samples[:3] = [175, 160, 140]  # the highest, cut off by the start
    samples[100:103] = [150, 168, 150]  # fully inside, but lower than the one at 400
    samples[400:403] = [150, 171, 150]
    samples[-3:] = [140, 160, 172]  # the second highest, cut off by the end
    peak = find_peak(samples, 0, 5600)
    assert peak is not None
    assert peak.position == pytest.approx(8 * 401 + 3.5, abs=0.5)
