# Wiring

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
| D9 | Relay (reserved for v1.1) | |

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
2. **Endstop:** press the switch by hand. The Position card should show *Home switch pressed*.
3. **Direction:** with the motor connected, jog **Away** by 1 mm. The carriage must move
   away from the switch. If it moves toward it, swap the two wires of one coil (with power
   off), or set `INVERT_DIRECTION` in `firmware/src/config.h` and reflash.
4. **Home**, then check that the rail stops on the switch, backs off until the switch opens and
   parks just clear of it. The activity log reports the switch's release distance.

Never connect or disconnect the motor while the driver is powered.

## Driver notes

- `DRIVER_RSENSE_OHM` in `firmware/src/config.h` is 0.11 Ω, which is right for common BTT and FYSETC
  TMC2209 modules. Check yours: the set current scales with it.
- Motor current is set over UART from the web UI (Settings → Motor current). The module's
  VREF potentiometer is ignored.
