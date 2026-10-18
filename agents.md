# MacroRail — source of truth

Handoff document. Anyone (person or agent) should be able to continue from here.
Keep it compact: update after every chunk of work, prune instead of appending.

## Goal

A polished, release-quality focus-stacking controller and portfolio project:
a Raspberry Pi hosts a web app (laptop + phone, same LAN) that drives a 3D-printed
macro rail and a camera, so a full stack runs start → end with no fiddling.
Not a prototype: no placeholders, no band-aids. Clean, modular and nothing more than needed.

## Scope

- **v1:** custom macro rail (Arduino Nano + TMC2209) + Sony A6400 over USB (gphoto2).
  All effort goes here. It ends with the complete pipeline working really well.
- **v1.1:** 3D printer as the motion source (Marlin G-code over USB, jog X/Y/Z),
  relay shutter-cable trigger on the Nano. v1 is designed so these plug in behind
  the existing motion/camera interfaces.
- **Later ideas:** in-browser review of the captured stack, low-res live stack
  preview, auto-detecting start/end focus from live view.

## Principles

- Stability and repeatability come first; then intuitive UX; then features.
- Simple and minimal. No over-engineering, no hot fixes. Fix root causes.
- One owner per piece of hardware; the browser never talks to hardware directly.
- Every state change is pushed to clients. No polling, no duplicated defaults.
- Never move or shoot on assumptions: wait for confirmations (move done, file added).

## Hardware (verified facts)

- **Rail** (CAD/STLs in `hardware/rail/`): 2 × 8×380 mm rods,
  4 × SC8UU blocks, T8 brass nut on a floating carrier, horizontal. The carriage
  carries the **sample**; the camera is fixed. CAD travel ≈ 150 mm (real limit not yet measured).
- **Lead screw:** Tr8×8 (P2, 4-start), **8 mm/rev**, not self-locking.
- **Motor:** NEMA 17 42SHDC3025-24B (ex Anet A8), 1.8°. Rated current unverified
  (an unofficial listing says 1.5 A). Read it off the label.
- **Resolution:** full step 40 µm; 1/16 microstep = **2.5 µm** (400 steps/mm).
- **Homing:** roller microswitch at the motor end (X-min).
- **Driver:** TMC2209 at **12 V**, STEP/DIR for motion, UART for configuration.
- **MCU:** Arduino Nano, USB to Pi.
- **Camera:** Sony A6400, USB to Pi, gphoto2 (libgphoto2 2.5.31 on the Pi).
- **Pi:** 3B+, Debian 13 (trixie) 64-bit, Python 3.13.5, `ssh pi`.
  `get_throttled=0x50005`: **under-voltage**. Fix the PSU before trusting USB stability.

## Decisions

- Homing uses the microswitch at the motor end (front). Position 0 is the front, and work
  happens near the front; we never need the far end. StallGuard is deferred.
- 1/16 microstepping with the driver's 256× interpolation; StealthChop. No CoolStep
  (dynamic current): the current stays constant during motion and stacks, for repeatability.
- Motor current: rating unknown (generic Anet A8 NEMA 17). Use a conservative,
  configurable default (~0.6 A RMS run) with a low idle hold.
- Precision instrument: every move is slow, with gentle acceleration and deceleration,
  including travel between start and end. Speed is never traded for stability.
- Motors off → position unknown → re-home before any absolute move.
- 4× objective (shot at 2×–4×) is the v1 target. 10× and a Tr8×2 screw are a later upgrade
  (steps/mm comes from config).
- The Nano runs a minimal custom line protocol (not G-code). Commands carry IDs,
  replies are matched by ID, events are async (move done, homed, stall, endstop).
  Stop takes effect immediately.
- Camera control is gphoto2 via trigger + wait for FILE_ADDED. Never use a direct
  `capture()` (caused `-7` errors and USB drops in MacroScanner3).
- Images stay on the SD card. JPEG download to the Pi is optional, only if it
  doesn't slow the stack (measure first).
- Live view through the gphoto2 preview, shown in the web UI.
- Stack definition: **start + end + step** (default) or **start + step + count**.
  Coverage is guaranteed: shots = ceil(range/step) + 1, and the last shot lands at or beyond the end.
- Cycle: move → settle → trigger → wait for the camera's confirmation → next.
  Never move before the camera confirms.
- Pause holds position and Resume continues. Stop returns to start.
  A completed stack returns to start.
- Backlash: always approach positions from the same direction as the stack runs.
- Run current is moderate, below rating. The current does not change during a stack;
  low hold only when idle.
- No saved presets/setups for now.
- Multi-client: one controller at a time. Other devices are view-only with a
  "Take control" button that takes control immediately.
- Backend is Python, FastAPI + WebSocket, managed with **uv**.
- Frontend is plain JS (ES modules) with handwritten CSS and no build step. Dark mode,
  minimal, mobile-first.
- License: PolyForm Noncommercial 1.0.0 for code; CC BY-NC 4.0 for CAD/docs.
  Use, adapt and share with attribution; no selling.
- The Pi gets a proper PSU for real runs. The current under-voltage is just a
  bench-access setup.
- Deploy: install script + systemd service, with autostart easy to enable/disable.
- The repo includes the Arduino firmware, the rail CAD/STLs, a hardware simulator
  (for tests, CI and screenshots) and tests.
- Git: local only unless explicitly agreed. Author is Sam-de-Ham
  <weisz.sam321@gmail.com>, with no co-author or AI attribution.

## Open questions

- None blocking. Measure on hardware: real travel, a good run current, settle time,
  JPEG download cost, and live-view frame rate.

## Status

- 2026-10-19: Reviewed MacroScanner2/3/4 and the Pi. Decisions agreed. Local git
  initialised; rail STLs and assembly guide imported into `hardware/rail/`.
  Next: v1 implementation plan.

## Reference: old projects (read-only inspiration)

- `C:\Code\Mine\MacroScanner4`: rail mechanics/CAD, Marlin config for the Anet board,
  measured hardware (its `agents.md`).
- `C:\Code\Mine\MacroScanner3`: newest software. Flask, gphoto2 trigger + FILE_ADDED
  (works, ~1.3–1.5 s/shot), probe scripts. Also on the Pi in `~/MacroScanner3`.
- `C:\Code\Mine\MacroScanner2`: FastAPI + WS push, Sony SDK helper (abandoned), mock mode.
