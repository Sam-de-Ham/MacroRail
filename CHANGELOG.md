# Changelog

## 1.0.0: unreleased

First release: a complete rewrite of the MacroScanner experiments.

- Arduino Nano + TMC2209 rail firmware with a documented line protocol: StealthChop,
  microswitch homing, soft limits, link watchdog, driver fault detection.
- Raspberry Pi web app: home, jog in steps down to 2.5 µm, start/end points with
  backlash-aware approach, range preview sweep, focus stacks with pause/resume/stop.
- Sony camera control over USB through gphoto2, with each shot confirmed and live view
  in the browser.
- Mobile-first dark UI, one controlling device at a time with one-tap handover.
- Simulator for the rail and camera (`--sim`), full test suite, CI.
- Install script and systemd service for the Pi.
