# MacroRail — source of truth

Handoff document. Anyone (person or agent) should be able to continue from here.
Keep it compact: update after every chunk of work, prune instead of appending.

## Goal

A polished, release-quality focus-stacking controller and portfolio project:
a Raspberry Pi hosts a web app (laptop + phone, same LAN) that drives a 3D-printed
macro rail and a camera, so a full stack runs start → end with no fiddling.
Not a prototype: no placeholders, no band-aids. Clean, modular and nothing more than needed.

## Scope

- **v1 (now):** custom macro rail (Arduino Nano + TMC2209) + Sony A6400 over USB (gphoto2).
- **v1.1:** 3D printer as the motion source (Marlin G-code over USB, jog X/Y/Z), and a relay
  shutter-cable trigger on the Nano (D9 reserved). Add these as new `Axis` / `Camera`
  implementations; nothing else should need to change.
- **Later ideas:** review captured JPEGs in the browser, a low-res live stack preview,
  auto-detecting start/end from live view, StallGuard crash detection, a Tr8×2 screw for 10×.

## Principles and how we work

- Stability and repeatability first, then intuitive UX, then features.
- Simple and minimal. No over-engineering, no hot fixes; fix root causes. Don't copy old-project
  approaches without checking them; research when unsure.
- One owner per device; the browser never talks to hardware. Push state, never poll.
- Never act on assumptions: wait for the controller's move reply and the camera's FILE_ADDED.
- Develop and test against the simulator. Real hardware is tested once everything is ready,
  just before calling v1 done.
- Every milestone ends with: `uv run pytest`, `ruff check`, `ruff format --check`,
  `mypy src` and `pio run -d firmware` all green, a local commit, and this file updated.
- Git: **local only** unless explicitly agreed. Author Sam-de-Ham <weisz.sam321@gmail.com>,
  with no co-author or AI attribution in commits.

## Hardware (verified facts)

- **Rail** (`hardware/rail/`): 2 × 8×380 mm rods, 4 × SC8UU blocks, T8 nut on a floating carrier,
  horizontal. The carriage carries the **sample**; the camera is fixed. CAD travel ≈ 150 mm.
- **Lead screw:** Tr8×8, 8 mm/rev, not self-locking.
- **Motor:** generic Anet A8 NEMA 17 (42SHDC3025-24B), rating unknown.
- **Resolution:** full step 40 µm; 1/16 microstep = **2.5 µm** (400 steps/mm).
- **Driver:** TMC2209 at 12 V: STEP/DIR for motion, UART (SoftwareSerial D7 RX / D8 TX via 1 kΩ) for setup.
- **Nano:** the pin map is in `firmware/src/config.h` and `docs/wiring.md`. The home switch should be
  on **D2** (INT0). This rail's switch is wired **normally-open** (C → GND, NO → D2), so
  `ENDSTOP_ACTIVE_LEVEL = LOW`. The motor needed `INVERT_DIRECTION = true`.
- **Pi:** 3B+, Debian 13 64-bit, Python 3.13.5, `ssh pi`. `sudo` needs a password, so the user
  runs `deploy/install.sh` themselves. It showed under-voltage on the bench supply; use a
  proper PSU for real runs.
- **Camera:** Sony A6400, USB *PC Remote* mode, gphoto2.

## Decisions

- **Homing:** microswitch at the motor end; position 0 = switch, park at `min_mm` (0.5 mm).
  Work happens near the front.
- **Home switch (user decision):** interrupt-driven and always armed.
  - The first contact stops any motion, in either direction, before its next step.
  - The only exception: a move that starts on the pressed switch and backs away from it.
  - While pressed, moves toward the switch are refused.
  - Every level change is pushed to the host as a `! SWITCH` event, with no polling.
- **Driver modes:** StealthChop, 1/16 + 256× interpolation. CoolStep and StallGuard are off.
- **Current policy:** full run current (default 600 mA) from the first move until idle for
  30 s, then low hold (200 mA). No current change during a stack.
- **Motors off** clears homed; re-home before absolute moves.
- **Motion speeds:** slow and gentle. Travel 2 mm/s, stack 1 mm/s, 10 mm/s².
  All of these are user settings.
- **Backlash:** every arrival at start/end ends moving in the stack direction (overshoot of
  0.3 mm when needed), and stacks only move forward.
- **Protocol** (`docs/protocol.md`): ASCII lines with ids.
  - Motion commands reply when the motion finishes.
  - `STATUS` is polled every 0.5 s and doubles as the firmware's 2 s watchdog.
  - A missing reply means the link is dead, and the host reconnects.
- **Camera:**
  - A shot is gphoto2 `trigger_capture`, then wait for FILE_ADDED. On failure: re-init and retry once.
    This can cost a duplicate frame, never a missing one.
  - Images stay on the card. Never use a blocking `capture()`; it dropped USB on Sony in MacroScanner3.
- **Stacks:**
  - Two modes: start + end + step (default), or start + step + count.
  - If the covering last shot would run past the travel limit, it is placed on the limit.
  - The range is always covered: count = ceil(range/step) + 1.
  - Steps snap to the microstep grid.
- **Stack runner:**
  - Each shot is move → settle (0.8 s) → shoot → confirm.
  - Pause holds position.
  - A camera error pauses the stack, and resume retakes that slice.
  - Stop or completion returns to start.
  - Each stack writes a JSON record to `~/.local/share/macrorail/stacks/`.
- **Live view** is paused during stacks. Tap-to-zoom is a 3× zoom around the tap point. The A6400
  preview frames are 1024×680, close to their on-screen size, so a 1:1 crop would add nothing.
- **Camera reconnect** is automatic: retried every 3 s, and right away after a loss. There is no
  Reconnect button. The capture timeout lives in `config.toml`, not the UI.
- **Stop:**
  - Always sent to the controller. There is no HALT command; motion is slow enough that a
    decelerating stop is immediate in practice.
  - During a stack's approach, Stop stops in place. While shooting, it stops and returns to
    the start. During the return, it stops the return.
- **Control:** one controlling client id at a time; the first to connect gets it, and
  "Take control" hands it over. Stop is allowed from any device.
- **Stack:** FastAPI + WebSocket + MJPEG; plain ES-module UI, no build step; uv; PlatformIO.
- **Config vs settings:** hardware constants live in `~/.config/macrorail/config.toml`. User
  settings, start/end and the step live in `~/.local/share/macrorail/settings.json`. `--sim` uses a `sim/` subfolder.
- **No presets/profiles for now.**
- **License:** PolyForm Noncommercial 1.0.0 (code), CC BY-NC 4.0 (hardware).

## Repository map

`firmware/` Nano (PlatformIO) · `src/macrorail/` app (`motion/`, `camera/`, `stack/`, `sim/`,
`machine.py`, `api.py`, `web/`) · `tests/` · `deploy/` install + service · `scripts/deploy-dev.sh` ·
`docs/` protocol, wiring, architecture · `hardware/rail/` STLs + assembly guide.

## Status

- **2026-10-19:**
  - v1 software is complete and tested against the simulator: 78 tests; ruff, mypy (strict) and the firmware build are green.
  - An independent code review was done and its findings were fixed: a double-tap Start could orphan a stack, Stop could be missed in several places, and live view was never enabled for gphoto. Link, watchdog and gphoto tests were added.
  - The driver UART moved to D7/D8, so all signals use one row (D3–D8).
  - The UI was checked in the browser at phone and desktop sizes: home, set range, stack, pause/resume, stop-and-return, take control.
  - On the Pi, the app was deployed to `~/macrorail` and ran in sim mode: it starts in about 5 s and live view streams.
  - The service is not installed yet because `sudo` needs a password.

- **2026-10-19, on the real Pi with nothing wired (Nano and A6400 on USB):**
  - **Power:** a new PSU fixed the under-voltage (`get_throttled` is `0x0`).
    The soft temperature limit tripped during a firmware compile on the Pi.
  - **Firmware:** flashed from the Pi over SSH with `pio run -d firmware -e nano -t upload`
    (PlatformIO in `uv tool`). The `nano` (old bootloader) environment is the right one.
    - READY arrives 1.6 s after the port opens. A STATUS round trip takes about 10 ms.
    - With nothing wired it reports `driver=missing` and `endstop=1` (the fail-safe reading), and refuses ENABLE/MOVE/JOG.
  - **Camera:** gphoto2 reports "Sony ILCE-6400 (PC Control)", and the battery widget works.
    - Live view: 1024×680 at about 30 fps from the camera; the app caps it at 10 fps.
    - A capture is confirmed in 1.33–1.43 s. The battery drains slightly while connected: the Pi does not charge it, so use a dummy battery for long stacks.
  - **Full app** (`.venv/bin/macrorail` run by hand): the rail is connected but reports no driver, the camera is connected, and live view streams. The systemd service is still not installed (the install needs the user's sudo).
  - **Setup guide:** a 9-page PDF with breadboard layout and wire checklist, at `MacroRail-quick-start.pdf` (not tracked). It is built from HTML in the session scratchpad.

## Next: hardware bring-up (with the user)

1. **Pi setup:** the user runs `~/macrorail/deploy/install.sh` on the Pi (it needs sudo).
2. **Wiring:** done on a breadboard. The switch moves to D2 (from D6).
3. **Firmware and port:** already flashed (1.0.0), and the default port path matches this Nano.
4. **First power-up checks:** detect the driver, check the switch reading, direction and homing.
5. **Calibrate:**
   - Measure the real travel and set `travel_mm`.
   - Tune the run current: smooth, cool, no lost steps at 2.5 µm moves.
   - Tune the settle time on 4× live view.
6. **Camera:** measure the JPEG-download cost to decide whether a review gallery is worth it.
7. **Full stacks:** run them at 2× and 4×, including a 100+ shot stack and a camera unplug mid-stack.
8. **Release polish:** README screenshots from the real setup, a sample stack, the date in the CHANGELOG,
   and a local `v1.0.0` tag. Push to GitHub only when the user says so.

## Reference: old projects (read-only inspiration)

- `C:\Code\Mine\MacroScanner4`: rail CAD and measurements (its `agents.md`).
- `C:\Code\Mine\MacroScanner3`: previous software; its gphoto2 findings fed the decisions above.
- `C:\Code\Mine\MacroScanner2`: early FastAPI prototype with the Sony SDK (abandoned).
