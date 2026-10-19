# Rail controller protocol (v2)

This is the line protocol between the Raspberry Pi (host) and the Arduino Nano (firmware).
It is the contract between `firmware/` and `src/macrorail/motion/`. The simulator in
`src/macrorail/sim/firmware.py` implements the same contract.

## Transport

- USB serial, 115200 baud, 8N1.
- Opening the port resets the Nano (DTR), and the host waits for the `READY` event.
- ASCII lines terminated by `\n`; a trailing `\r` is ignored. Lines are at most 63 characters.
- All positions, distances, speeds and accelerations are in **microsteps**
  (`/s`, `/s²` for speed and acceleration). The host converts to millimetres.

## Messages

| Direction | Form | Example |
|---|---|---|
| Host → firmware request | `<id> <COMMAND> [arg ...]` | `17 MOVE 4000 400 4000` |
| Firmware → host reply | `<id> OK [key=value ...]` | `17 OK pos=4000` |
| | `<id> ERR <CODE> [key=value ...]` | `17 ERR NOT_HOMED` |
| Firmware → host event | `! <EVENT> [key=value ...]` | `! POS pos=1234` |

- `id` is a decimal integer from 1 to 65535 chosen by the host, and is unique among requests still in flight.
- Each request gets exactly one reply with the same `id`.
- **Immediate** commands reply straight away.
- **Motion** commands (`HOME`, `MOVE`, `JOG`) reply only when the motion has finished.
  - The reply is `OK` if the motion completed, or `ERR` with the reason it ended early.
  - Only one motion command may be in flight. While one is running, only `INFO`, `STATUS` and
    `STOP` are accepted; everything else gets `ERR BUSY`.
- A line that cannot be parsed gets the reply `0 ERR SYNTAX` (or `0 ERR TOOLONG`).
- **Flow control:** the Nano talks to the driver over a software UART that blocks its interrupts,
  which would drop bytes arriving from the host. So the firmware uses the driver UART only while
  answering a request: `STATUS` when idle (a driver check at most once a second), `ENABLE` and
  `CURRENT`. The host sends nothing while a request is unanswered. The only exception is a motion
  command: once it has been sent, `STATUS` and `STOP` may follow, because the firmware never
  touches the driver while moving.

## Commands

| Command | Kind | Reply data | Notes |
|---|---|---|---|
| `INFO` | immediate | `fw=<semver> proto=<n> driver=<ok\|missing>` | |
| `STATUS` | immediate | `pos= homed= enabled= moving= endstop= driver=` | Flags are `0`/`1`. `driver` is `ok`/`missing`. The host polls it every 0.5 s, which also keeps the link watchdog alive. |
| `ENABLE` | immediate | | Energises the motor. Calibrates StealthChop at run current. |
| `DISABLE` | immediate | | De-energises the motor and **clears homed**. |
| `CURRENT <run_mA> <hold_mA>` | immediate | | RMS currents. `100 ≤ run ≤ 1500` and `0 ≤ hold ≤ run`. |
| `LIMITS <min> <max>` | immediate | | Soft limits, enforced once homed. |
| `HOME <fast> <slow> <clearance> <max> <release_max> <accel>` | motion | `pos=0 release=` | Seek the switch at `fast` for up to `max` steps. Back off until the switch has released, then `clearance` further. Touch it again at `slow`; that point becomes `0`. `release` is how far past its trip point the switch released (its hysteresis). Fails with `SWITCH_STUCK` if the switch is still pressed after `release_max`. |
| `MOVE <target> <speed> <accel>` | motion | `pos=` | Absolute move. Requires homed, and the target must be within limits. |
| `JOG <delta> <speed> <accel>` | motion | `pos=` | Relative move. Allowed when not homed; once homed, the target must be within limits. |
| `STOP` | immediate | | Decelerate. The pending motion then replies `ERR STOPPED pos=`. |

## Events

| Event | When |
|---|---|
| `! READY fw=<semver> proto=<n> driver=<ok\|missing>` | After boot (and so after every port open). |
| `! POS pos=<n>` | About every 100 ms while moving. |
| `! SWITCH pressed=<0\|1>` | The home switch's debounced level changed. |
| `! FAULT code=<code>` | When the idle driver check finds a problem. The motor is disabled and homed is cleared. |

Fault codes:

- `driver_lost`: the driver doesn't answer over UART. Check the 12 V supply and the UART wiring.
- `driver_reset`: the driver lost power and its registers were reset. The firmware has already restored the configuration.
- `overtemp`: the driver is too hot.
- `short`: short to ground or to supply.

## Error codes

| Code | Meaning |
|---|---|
| `SYNTAX`, `TOOLONG` | Malformed line. |
| `UNKNOWN` | Unknown command. |
| `ARG` | Wrong number or range of arguments. |
| `BUSY` | A motion command is in flight. |
| `DISABLED` | Motion requested while the motor is disabled. |
| `NOT_HOMED` | Absolute move before homing. |
| `LIMIT` | The target is outside the soft limits. |
| `DRIVER` | The driver isn't responding, so the motor can't be enabled. |
| `STOPPED` | The motion ended early on `STOP`. |
| `ENDSTOP` | The switch closed during a move or jog, which stopped at once and cleared homed. A move toward the switch while it is already pressed is refused with this code without moving (homed unchanged). |
| `NO_SWITCH` | Homing travelled `max` steps without finding the switch. |
| `SWITCH_STUCK` | The switch was still pressed after backing off `release_max`. |
| `LINK` | The watchdog stopped motion: no line from the host for 2 s. |

## Safety rules enforced by the firmware

- The switch is always armed. Its first contact (a hardware interrupt) stops any motion, in either
  direction, before the next step. The only exception is a move that starts with the switch
  pressed and backs away from it (positive direction): it ignores the switch only until the switch
  has released, bounce included, and is armed again from then on. While the switch is pressed,
  moves toward it are refused.
- During homing, the first contact ends the seek. The back-off ignores the switch until it has
  released. The slow re-approach ends on the next contact, which becomes position `0`.
- `DISABLE`, an endstop hit, and any driver fault clear the homed flag. The host must home again
  before absolute moves.
- While motion is in flight, the firmware stops the motor (with deceleration) if no line arrives
  for 2 s.
