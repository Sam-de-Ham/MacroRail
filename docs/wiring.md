# Wiring

```
                 USB                          12 V supply
 Raspberry Pi ─────────── Arduino Nano          │   │
      │                   │                    (+) (−)
      │ USB               D3 ─────── STEP        │   │
      │                   D4 ─────── DIR         │   │   100 µF across VM–GND,
   Camera                 D5 ──┬──── EN          │   │   close to the module
                               └ 10 kΩ ─ 5V      │   │
                          D7 ────────┬ PDN_UART  │   │
                          D8 ── 1 kΩ ┘           │   │
                          5V ─────── VIO    VM ──┘   │
                          GND ────── GND    GND ─────┘
                                     MS1 ─ GND
                          D6 ──┐     MS2 ─ GND
                          GND ─┤     OA1/OA2 ── motor coil A
                       switch NC/C   OB1/OB2 ── motor coil B
                                    TMC2209
```

## Connections

| Nano | TMC2209 module / other | Notes |
|---|---|---|
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
| D6 | Home switch NC | Switch C (common) → GND. |
| D9 | Relay (reserved for v1.1) | |

## Home switch

Wire the roller microswitch **normally-closed** (C and NC terminals). The input then reads
"triggered" when the switch is pressed **or** when a wire breaks, so a loose connector stops
the rail instead of letting it crash into the motor block. The firmware expects this; if
the switch only has two terminals (normally-open), change `ENDSTOP_ACTIVE_LEVEL` in
`firmware/src/config.h` to `LOW`.

## First power-up checks

1. **Without the motor connected:** plug the Nano into the Pi and power the 12 V supply.
   In the web UI, the rail pill should show **Not homed** (not *No driver power*). If the
   driver isn't detected, check 12 V, the UART wiring and the 1 kΩ resistor. The TMC2209
   only answers on UART when VM is powered.
2. **Endstop:** press the switch by hand. The Position card should show *Home switch pressed*.
3. **Direction:** with the motor connected, jog **Away** by 1 mm. The carriage must move
   away from the switch. If it moves toward it, swap the two wires of one coil (with power
   off), or set `INVERT_DIRECTION` in `firmware/src/config.h` and reflash.
4. **Home**, then check that the rail stops on the switch and parks at 0.5 mm.

Never connect or disconnect the motor while the driver is powered.

## Driver notes

- `DRIVER_RSENSE_OHM` in `firmware/src/config.h` is 0.11 Ω, which is right for common BTT and FYSETC
  TMC2209 modules. Check yours: the set current scales with it.
- Motor current is set over UART from the web UI (Settings → Motor current). The module's
  VREF potentiometer is ignored.
