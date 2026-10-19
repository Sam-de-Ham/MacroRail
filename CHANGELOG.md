# Changelog

## Unreleased

- Tabbed interface: a fixed live view with Shoot, Camera, Review and System tabs, and a
  status strip showing whatever is running.
- Auto range: a scan through focus finds where the subject starts and ends.
- Step-size helper from the lens's magnification and numerical aperture.
- Backlash measurement from live view, with a suggested take-up.
- Camera settings in the browser (ISO, shutter, aperture, exposure compensation, white
  balance, quality, size, focus mode) and a test shot.
- Stack names; small JPEG copies of each shot kept on the Pi; a review gallery with a quick
  all-in-focus preview stack.
- Installable as an app; a chime, vibration, tab title and (over HTTPS) a notification when a
  stack ends or needs attention.
- Diagnostics: motor driver status, link round trip, camera, and the Pi's temperature, power,
  load, memory and disk.
- Firmware protocol 3: `DRIVER` reports the TMC2209's status. Reflash the Nano.
- CI on current actions, a CI badge, and steadier switch tests.

## 1.0.0: 2026-10-19

First release: a complete rewrite of the MacroScanner experiments.

- Arduino Nano + TMC2209 rail firmware with a documented line protocol:
  - StealthChop.
  - An interrupt-driven, always-armed home switch.
  - Soft limits, link watchdog and driver fault detection.
- Raspberry Pi web app: home, jog in steps down to 2.5 µm, start/end points with
  backlash-aware approach, range preview sweep, focus stacks with pause/resume/stop.
- Sony camera control over USB through gphoto2:
  - Each shot is confirmed before the stack moves on.
  - Live view in the browser, with tap-to-zoom and a pause toggle.
- Mobile-first dark UI, one controlling device at a time with one-tap handover.
- Simulator for the rail and camera (`--sim`), full test suite, CI.
- Install script and systemd service for the Pi.
