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
- **YAW:** positive is the direction `HOME YAW` turns. Yaw is unlimited.
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
- The module has no driver UART, so there is no half-duplex rule; the host still uses the same
  `Link` discipline.

## Commands

| Command | Kind | Reply data | Notes |
|---|---|---|---|
| `INFO` | immediate | `fw=<semver> proto=1 role=module` | |
| `STATUS` | immediate | `yaw= tilt= yhomed= thomed= moving=<none\|yaw\|tilt> switch= hall=` | Positions in half-steps, flags `0`/`1`, `hall` the raw ADC reading (0–1023). Polled every 0.5 s; it also keeps the link watchdog alive. |
| `HALL` | immediate | `hall=` | One raw ADC reading of the hall sensor. |
| `LIMITS TILT <min> <max>` | immediate | | Soft limits for tilt, enforced once tilt is homed. Yaw has none. |
| `HOME TILT <fast> <slow> <clearance> <max> <release_max> <accel>` | motion | `pos=0 release=` | The rail's homing sequence: seek the switch (negative direction) at `fast` for up to `max`; back off until the switch has released, then `clearance` further; touch it again at `slow`. That contact is `0`. `release` is the switch's hysteresis. |
| `HOME YAW <speed> <accel> <max> <takeup>` | motion | `pos=0 from= dev= width=` | Turn in the positive direction for up to `max` half-steps, sampling the hall sensor. Find the magnet's field peak (below). Turn back to `takeup` before the peak and approach it in the positive direction; that point is `0`. `from` is the peak's position in the frame before this command (two homings one turn apart measure the half-steps per turn). `dev` is the peak's deviation from the baseline in ADC counts, `width` the width of the peak at half height in half-steps. |
| `MOVE <axis> <target> <speed> <accel>` | motion | `pos=` | Absolute. The axis must be homed; a tilt target must be within the limits. |
| `JOG <axis> <delta> <speed> <accel>` | motion | `pos=` | Relative. Allowed before homing; once tilt is homed, the target must be within its limits. |
| `STOP` | immediate | | Decelerate whatever is moving. Its pending motion replies `ERR STOPPED pos=`. |

`speed` is 1–1000 half-steps/s and `accel` 1–4000 half-steps/s²; anything else is `ERR ARG`.

### Finding the magnet (HOME YAW)

The KY-024's linear hall sensor reads about 512 with no field and moves up or down (by pole)
as the magnet passes. While turning at constant speed the firmware stores the mean reading of
every 8 half-steps (one byte each, ADC/4), up to `max` half-steps. Then:

1. **Baseline:** the most common stored value (a 64-bucket histogram), i.e. the reading away
   from the magnet.
2. **Deviation** of each sample from the baseline; the largest is the peak.
3. If the largest deviation is below 40 ADC counts: `ERR NO_MAGNET`.
4. The **peak region** is the contiguous run of samples around the largest deviation whose
   deviation is at least half of it. If the sweep covered more than a turn and that run touches
   either end of the sweep, the next-highest peak whose run lies fully inside is used instead.
5. The **peak position** is the deviation-weighted centroid of that run. This repeats far better
   than the moment the board's comparator would switch.

The host sends `max` of about 1.3 turns.

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
| `LIMIT` | A tilt target outside the soft limits. |
| `STOPPED` | The motion ended early on `STOP`. |
| `ENDSTOP` | The tilt switch closed during a tilt move or jog: stopped at once, tilt homed cleared. A tilt move toward the pressed switch is refused with this code without moving. |
| `NO_SWITCH` | Tilt homing travelled `max` without finding the switch. |
| `SWITCH_STUCK` | The switch was still pressed after backing off `release_max`. |
| `NO_MAGNET` | Yaw homing found no field peak. |
| `LINK` | The watchdog stopped motion: no line from the host for 2 s. |

## Safety rules enforced by the firmware

- **The tilt switch is always armed**, in every motion of either axis, through a pin-change
  interrupt: its first contact stops a tilt motion before the next step. As on the rail, a tilt
  move that starts on the pressed switch and moves away ignores it only until it has released;
  outside homing, a contact counts only if it is still closed a few µs later.
- An endstop hit clears tilt's homed flag. Tilt soft limits apply once homed.
- **Coils off when idle:** 300 ms after a motion ends, both motors' coils are switched off. The
  gearboxes hold the load, and no heat reaches the insect. A motion energises its motor again.
- While a motion is in flight, the firmware stops it (with deceleration) if no line arrives for
  2 s.
- Homed flags are only lost on reset, `ENDSTOP` (tilt) or a failed `HOME`.

## Pins (module Nano)

| Signal | Pin |
|---|---|
| Yaw ULN2003 IN1, IN2, IN3, IN4 | D2, D3, D4, D5 |
| Tilt ULN2003 IN1, IN2, IN3, IN4 | D6, D7, D8, D9 |
| Tilt switch (C → GND, NO → pin, internal pull-up, active low) | D10 |
| KY-024 analog output | A0 |

AccelStepper's half-step mode takes a 28BYJ-48's pins in the order IN1, IN3, IN2, IN4.
