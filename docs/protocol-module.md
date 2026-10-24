# Scan module controller protocol (v1)

The line protocol between the Raspberry Pi (host) and the scan module's Arduino Nano. It is the
contract between `firmware-module/`, `src/macrorail/motion/module.py` and the simulator in
`src/macrorail/sim/module.py`. It follows the rail's protocol ([protocol.md](protocol.md)) in
everything not stated here; the rail's protocol is unchanged.

The module has its own Nano so the rail firmware never changes (see
[3d-software-plan.md](3d-software-plan.md)).

## Transport

- USB serial, 115200 baud, 8N1. Opening the port resets the Nano; the host waits for `READY`.
- ASCII lines ending in `\n` (a trailing `\r` is ignored), at most 63 characters host → firmware.
- `READY` carries `role=module`. That is how the host tells the two Nanos apart: both are CH340
  clones without serial numbers, so their `/dev/serial/by-id` names collide. The rail's `READY`
  has no `role`.

## Units and directions

- Positions, distances, speeds and accelerations are in the motor's **half-steps** (`/s`,
  `/s²`). The host converts to degrees. A 28BYJ-48 makes about 4076 half-steps per output turn;
  the exact number is measured (see `HOME YAW`), because the gearbox ratio isn't an integer.
- **TILT:** positive moves go **away from the switch**, which turns the insect's belly towards the
  lens (the tilt *angle* decreases). The switch is at the dorsal end, past +90°.
- **YAW:** positive turns the head **counter-clockwise seen from above**, and it is the
  direction `HOME YAW` turns. Yaw is unlimited. At yaw 0 the magnet is over the hall sensor,
  centring screw X points at the camera and screw Y at the bearing side (+Y).
- Each axis has a direction constant in `firmware-module/src/config.h` (`TILT_INVERT`,
  `YAW_INVERT`) for the motor wiring.

## Messages

As in the rail protocol: requests `<id> <COMMAND> [arg ...]`, replies `<id> OK [key=value ...]`
or `<id> ERR <CODE> [key=value ...]`, events `! <EVENT> [key=value ...]`, `0 ERR SYNTAX` for a
line that can't be parsed. The axis is a word argument: `YAW` or `TILT`.

- **Immediate** commands reply straight away.
- **Motion** commands (`HOME`, `MOVE`, `JOG`) reply when the motion has finished: `OK`, or
  `ERR` with the reason it ended early.
- **One motion at a time, across both axes.** While one runs, only `INFO`, `STATUS`, `HALL` and
  `STOP` are accepted; everything else gets `ERR BUSY`.
- **Order of checks:** the line (`SYNTAX`, `TOOLONG`), the command (`UNKNOWN`), the axis word,
  the number of arguments and every argument's range (`ARG`), then `BUSY`, then the state
  checks (`NOT_HOMED`, `LIMIT`, `PRESSED`). So a malformed request gets `ARG` even while busy.
- Numbers are decimal integers that fit the firmware's 32-bit `long`; anything else is `ERR ARG`.
- The module has no driver UART, so there is no half-duplex rule; the host still uses the same
  `Link` discipline.

## Commands

| Command | Kind | Reply data | Notes |
|---|---|---|---|
| `INFO` | immediate | `fw=<semver> proto=1 role=module` | |
| `STATUS` | immediate | `yaw= tilt= yhomed= thomed= moving=<none\|yaw\|tilt> switch= hall=` | Positions in half-steps, flags `0`/`1`, `hall` the raw ADC reading (0–1023). Polled every 0.5 s; it also keeps the link watchdog alive. |
| `HALL` | immediate | `hall=` | One raw ADC reading of the hall sensor. |
| `LIMITS TILT <min> <max>` | immediate | | Soft limits for tilt, enforced once tilt is homed. Yaw has none. |
| `HOME TILT <fast> <slow> <clearance> <max> <release_max> <accel>` | motion | `pos=0 release=` | The rail's homing sequence: seek the switch (negative direction) at `fast` for up to `max`; back off until the switch has released, then `clearance` further; touch it again at `slow` (the probe). That contact is `0`. `release` is the switch's hysteresis. If the switch is pressed at the start, it backs off first and then seeks as usual, so the probe always has the seek's trip point to compare with (below). |
| `HOME YAW <speed> <accel> <max> <takeup>` | motion | `pos=0 from= dev= width=` | Turn in the positive direction for up to `max` half-steps, sampling the hall sensor. Find the magnet's field peak (below). Turn back to `takeup` before the peak and approach it in the positive direction; that point is `0`. `from` is the peak's position in the frame before this command (two homings one turn apart measure the half-steps per turn). `dev` is the peak's deviation from the baseline in ADC counts, `width` the width of the peak at half height in half-steps. |
| `MOVE <axis> <target> <speed> <accel>` | motion | `pos=` | Absolute. The axis must be homed; a tilt target must be within the limits. |
| `JOG <axis> <delta> <speed> <accel>` | motion | `pos=` | Relative. Allowed before homing, but an unhomed tilt jog may be at most 170 half-steps (about 15°) either way, else `ERR LIMIT` (the host caps it at 10°). Once tilt is homed, the target must be within its limits. |
| `STOP` | immediate | | Decelerate whatever is moving, never past the motion's own target (so never past the tilt limits); a motion that hasn't stepped yet stops where it is. Its pending motion replies `ERR STOPPED pos=`. |

Argument ranges (anything else is `ERR ARG`):

- `speed`, `fast`, `slow`: 1–1000 half-steps/s; `accel`: 1–4000 half-steps/s².
- Absolute positions (`MOVE` target, `LIMITS` min and max): −1,000,000 to 1,000,000, and
  `min` ≤ `max`.
- Distances: `JOG` delta at most 20,000 either way (about 5 turns); `HOME TILT` `clearance`,
  `max` and `release_max` 1–20,000 with `release_max` > `clearance`; `HOME YAW` `takeup`
  1–20,000.
- `HOME YAW` `max`: 16–5376 (below).

**Tilt homing, the probe's contact:** like other motions (and unlike the seek, which takes the
very first blip), the probe counts only a contact that is still closed a few µs later. It must
also lie where the seek tripped the switch: at most `clearance`/2 half-steps before that point
(the probe comes from the positive side). An earlier contact is noise or a switch that moved;
homing there would put 0 in the wrong place, so homing ends with `ERR SWITCH_EARLY pos=` and
tilt stays unhomed.

### Finding the magnet (HOME YAW)

The KY-024's linear hall sensor reads about 512 with no field and moves up or down (by pole)
as the magnet passes. While turning, the firmware reads the sensor at every position of the
sweep, from its start (before the first step) to its end at `max`, and stores the rounded mean
of every 8 positions (one byte each, ADC/4): sample i covers offsets 8i … 8i+7. A last, partial
sample is dropped. Then:

1. **Baseline:** the most common stored value (a 64-bucket histogram), i.e. the reading away
   from the magnet.
2. **Deviation** of each sample from the baseline; the largest is the peak.
3. If the largest deviation is below 40 ADC counts, or there are fewer than 2 samples:
   `ERR NO_MAGNET`.
4. The **peak region** is the contiguous run of samples around the largest deviation whose
   deviation is at least half of it. If the sweep covered more than a turn and that run touches
   either end of the sweep, the next-highest peak whose run lies fully inside is used instead:
   the peaks are tried highest first, skipping every one whose run touches an end.
5. The **peak position** is the deviation-weighted centroid of that run. This repeats far better
   than the moment the board's comparator would switch.

Details, as the firmware implements them:

- `max` must be 16–5376 half-steps (at least 2, at most 672 one-byte bins of 8) and `takeup`
  1–20,000; otherwise `ERR ARG`. The host sends about 1.25 turns.
- Deviations are absolute, so either pole of the magnet works.
- Every `ERR` that ends a motion carries `pos=` (the axis's position where it stopped).
- The baseline is the 64-bucket mode, then the rounded mean of the bins in that bucket ×4
  (integer ADC counts). `dev` is in ADC counts at a resolution of 4; `width` is the run's
  bins × 8.
- One reading per position, whatever the speed, so the ramps don't skew the bins. The
  centroid uses each bin's centre, 8i + 3.5, and is rounded to the nearest half-step.
- The rule for a run touching an end applies only when `max` is over one nominal turn (4076);
  the other peak must also reach 40 counts and lie fully inside. Otherwise the run found is
  used.

**Positions:** the firmware never resets its step counters, because in half-step mode the coil
pattern follows the counter. Each axis keeps an origin instead, and homing moves the origin;
what the host sees is identical (0 after homing). With the coils off a rotor may settle by up
to half a motor step (about 0.09° at the output). Before a motor whose coils were off takes
its first step, the firmware energises the coil pattern of its held position and waits 10 ms,
which pulls the rotor back, so the count stays right and the first step is a normal one.

## Events

| Event | When |
|---|---|
| `! READY fw=<semver> proto=1 role=module` | After boot (and after every port open). |
| `! POS axis=<yaw\|tilt> pos=<n>` | About every 100 ms while that axis moves. |
| `! SWITCH pressed=<0\|1>` | The tilt switch's debounced level changed. |

## Error codes

| Code | Meaning |
|---|---|
| `SYNTAX`, `TOOLONG`, `UNKNOWN`, `ARG` | As in the rail protocol (`ARG` also for an unknown axis). |
| `BUSY` | A motion command is in flight. |
| `NOT_HOMED` | Absolute move of an axis that isn't homed. |
| `LIMIT` | A tilt target outside the soft limits, or an unhomed tilt jog over 170 half-steps. |
| `STOPPED` | The motion ended early on `STOP`. |
| `ENDSTOP` | The tilt switch closed during a tilt move or jog: stopped at once, tilt homed cleared. Also when that happens while the move is already stopping on `STOP` or the watchdog, so a lost homing is never hidden. Carries `pos=`. |
| `PRESSED` | A tilt move or jog toward the switch while it is pressed: refused without moving, homed kept. Carries `pos=`. |
| `NO_SWITCH` | Tilt homing travelled `max` without finding the switch. |
| `SWITCH_STUCK` | The switch was still pressed after backing off `release_max`. |
| `SWITCH_EARLY` | Tilt homing's probe met the switch more than `clearance`/2 before where the seek tripped it (noise on the switch line, or the switch moved). Tilt stays unhomed. Carries `pos=`. |
| `NO_MAGNET` | Yaw homing found no field peak. |
| `LINK` | The watchdog stopped motion: no line from the host for 2 s. |

## Safety rules enforced by the firmware

- **The tilt switch is always armed**, in every motion of either axis, through a pin-change
  interrupt: its first contact stops a tilt motion before the next step. As on the rail, a tilt
  move that starts on the pressed switch and moves away ignores it only until it has released
  (its release bounce included); outside the homing seek, a contact counts only if it is still
  closed a few µs later.
- While tilt moves toward the switch, the switch's level stops it too, not only a closing edge:
  a contact made just before the motion started still counts. Whether the switch is pressed
  when a motion starts is read from the debounced level or the raw input, whichever says
  pressed.
- An endstop hit clears tilt's homed flag. Tilt soft limits apply once homed; before that,
  tilt jogs are limited to 170 half-steps (about 15°).
- **Coils off when idle:** 300 ms after a motion ends, both motors' coils are switched off. The
  gearboxes hold the load, and no heat reaches the insect. A motion energises its motor again.
- While a motion is in flight, the firmware stops it (with deceleration) if no line arrives for
  2 s.
- Homed flags are only lost on reset, `ENDSTOP` (tilt) or a `HOME` of that axis (cleared when
  it starts, set when it succeeds).

## Pins (module Nano)

| Signal | Pin |
|---|---|
| Yaw ULN2003 IN1, IN2, IN3, IN4 | D4, D5, D6, D7 |
| Tilt ULN2003 IN1, IN2, IN3, IN4 | D8, D9, D11, D12 |
| Tilt switch (C → GND, NO → pin, internal pull-up, active low) | D10 |
| KY-024 analog output | A0 |

AccelStepper's half-step mode takes a 28BYJ-48's pins in the order IN1, IN3, IN2, IN4.
