# Wiring

For a step-by-step breadboard build with pictures and a wire checklist, see the
[build guide](guides/MacroRail-build-guide.pdf). This page is the compact reference.

```
                 USB                          12 V supply
 Raspberry Pi ─────────── Arduino Nano          │   │
      │                   │                    (+) (−)
      │ USB               D2 ──┐ home switch NO   │   │
      │                   GND ─┘ home switch C    │   │
      │                   D3 ─────── STEP        │   │
      │                   D4 ─────── DIR         │   │   100 µF across VM–GND,
   Camera                 D5 ──┬──── EN          │   │   close to the module
                               └ 10 kΩ ─ 5V      │   │
                          D7 ────────┬ PDN_UART  │   │
                          D8 ── 1 kΩ ┘           │   │
                          5V ─────── VIO    VM ──┘   │
                          GND ────── GND    GND ─────┘
                                     MS1 ─ GND
                                     MS2 ─ GND
                                     OA1/OA2 ── motor coil A
                                     OB1/OB2 ── motor coil B
                                    TMC2209
```

## Connections

| Nano | TMC2209 module / other | Notes |
|---|---|---|
| D2 | Home switch NO | Switch C (common) → GND. D2 is the Nano's hardware-interrupt pin (INT0). |
| D3 | STEP | |
| D4 | DIR | |
| D5 | EN | Active low. A 10 kΩ pull-up to 5 V keeps the motor off while the Nano boots. |
| D7 | PDN_UART | Direct. UART receive. |
| D8 | PDN_UART through 1 kΩ | UART transmit. Single-wire UART needs the resistor. |
| 5V | VIO (VDD) | Logic supply. |
| GND | GND | Shared with the 12 V supply's ground. |
| — | MS1, MS2 → GND | UART address 0. |
| — | VM ← 12 V | Add a 100 µF electrolytic across VM–GND at the module. |
| — | OA1/OA2, OB1/OB2 | One motor coil each. Find coil pairs with a multimeter (a few Ω between the two wires of a pair). |
| D9 | (reserved) | Kept free for a shutter-cable relay; not used. |

## Home switch

The roller microswitch is wired **normally-open**: C to GND, NO to D2, NC empty. It closes
when the carriage presses it.

The switch is always armed. Its first contact fires a hardware interrupt, and any motion
stops before its next step, in either direction. The only exception is a move that starts with
the switch already pressed and backs away from it; that move ignores the switch's release
bounce. While the switch is pressed, moves toward it are refused.

To wire it normally-closed instead (C + NC), set `ENDSTOP_ACTIVE_LEVEL` to `HIGH` in
`firmware/src/config.h` and reflash. A broken wire then also reads as "pressed", so it fails
safe, at the cost of a stop whenever a connector works loose. Motor direction is set by
`INVERT_DIRECTION` in the same file.

## First power-up checks

1. **Without the motor connected:** plug the Nano into the Pi and power the 12 V supply.
   In the web UI, the rail pill should show **Not homed** (not *No driver power*). If the
   driver isn't detected, check 12 V, the UART wiring and the 1 kΩ resistor. The TMC2209
   only answers on UART when VM is powered.
2. **Endstop:** press the switch by hand. The Position card on the Shoot tab should show *Home switch pressed*.
3. **Direction:** with the motor connected, jog **Away** by 1 mm. The carriage must move
   away from the switch. If it moves toward it, swap the two wires of one coil (with power
   off), or set `INVERT_DIRECTION` in `firmware/src/config.h` and reflash.
4. **Home**, then check that the rail stops on the switch, backs off until the switch opens and
   parks just clear of it. The activity log reports the switch's release distance.

Never connect or disconnect the motor while the driver is powered.

## Driver notes

- `DRIVER_RSENSE_OHM` in `firmware/src/config.h` is 0.11 Ω, which is right for common BTT and FYSETC
  TMC2209 modules. Check yours: the set current scales with it.
- Motor current is set over UART from the web UI (System tab, Motion → Motor current). The driver module's
  VREF potentiometer is ignored.

## Scan module

The 3D scan module has its own Arduino Nano on its own USB cable, so nothing above changes.
The illustrated, wire-by-wire build is in the
[scan module guide](guides/MacroRail-scan-module-guide.pdf). Pins are constants
in `firmware-module/src/config.h`.

| Module Nano | Connects to | Notes |
|---|---|---|
| D2, D3, D4, D5 | Yaw ULN2003 IN1, IN2, IN3, IN4 | |
| D7, D6, D9, D11 | Tilt ULN2003 IN1, IN2, IN3, IN4 | Note the order: IN1 on D7, IN2 on D6. D8 is free. |
| D10 | Tilt switch NO | Switch C → GND, NC empty. Internal pull-up, active low, pin-change interrupt. |
| A0 | KY-024 AO | The analogue output; the board's DO and potentiometer are unused. |
| 5V | KY-024 + | The sensor only. |
| GND | KY-024 G, both ULN2003 −, 5 V supply − | One common ground. |
| — | Both ULN2003 + ← separate 5 V supply | Not from the Nano: each 28BYJ-48 draws about 240 mA while moving. |

Each 28BYJ-48 plugs into its ULN2003 board's 5-pin socket. If a motor turns the wrong way,
set `TILT_INVERT` or `YAW_INVERT` in `config.h` and reflash: tilt's positive direction is away
from the switch (the belly turns towards the lens), yaw's is counter-clockwise seen from
above. The tilt switch can be wired normally closed by setting `SWITCH_ACTIVE_LEVEL` to `HIGH`,
as for the rail.

Flash with `pio run -d firmware-module -e nano -t upload` (`-e nano_new` for a Nano with the
new bootloader). **System → Module test** in the app's 3D workspace shows the switch, the hall
reading (about 512 with no magnet near) and the step counts, with a forward and back button
per motor, for checking the wiring before the first homing.

**Before plugging the module's Nano into the Pi**, make sure `port` under `[rail]` in
`~/.config/macrorail/config.toml` is `"auto"` (the default) or a `/dev/serial/by-path/...`
socket path, then restart the app. The two CH340 clones share one `/dev/serial/by-id` name, so
an old by-id path may then point at the module, and the rail would refuse it. `install.sh`
never overwrites an existing config.
