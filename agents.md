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

- **Homing (user asked for a slower seek):**
  - Seek at 1 mm/s, stopping on the first contact.
  - Back off until the switch has released (at most `homing_release_max_mm`, 5 mm), plus 0.5 mm clearance.
    A roller lever releases well past its trip point, so a fixed back-off failed with SWITCH_STUCK.
  - Re-approach at 0.2 mm/s. Position 0 is the second contact.
  - The release distance is reported and logged.
  - Park at whichever is further: `min_mm` (0.5 mm) or the release point plus the clearance,
    so the switch rests open and armed. Work happens near the front.
- **Home switch (user decision):** interrupt-driven and always armed.
  - The first contact stops any motion, in either direction, before its next step. It stops
    abruptly, with no ramp, within tens of µs (worst case one 2.5 µm step).
  - The only exception: a move that starts on the pressed switch and backs away from it. It
    ignores the switch only until it releases; after that the switch is armed again.
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
  - **Half-duplex around the driver UART:** the Nano's SoftwareSerial drops host bytes.
    - The firmware uses the driver UART only while answering a request (idle STATUS, ENABLE, CURRENT).
    - The host sends nothing while a request is unanswered; motion requests free the line once sent.
- **Camera:**
  - A shot is gphoto2 `trigger_capture`, then wait for FILE_ADDED. On failure: re-init and retry once.
    This can cost a duplicate frame, never a missing one.
  - Images stay on the card. Never use a blocking `capture()`; it dropped USB on Sony in MacroScanner3.
- **Stacks:**
  - Two modes: start + end + step (default), or start + step + count.
  - If the covering last shot would run past the travel limit, it is placed on the limit.
  - The range is always covered: count = ceil(range/step) + 1.
  - Steps snap to the microstep grid.
  - The shot count is shown before starting: in the plan summary and on the Start button.
- **Stack runner:**
  - Each shot is move → settle (0.8 s) → shoot → confirm.
  - Pause holds position.
  - A camera error pauses the stack, and resume retakes that slice.
  - Stop or completion returns to start.
  - Each stack writes a JSON record to `~/.local/share/macrorail/stacks/`.
- **Live view** is paused during stacks. Each browser can also pause it with a toggle, which closes
  the stream so the camera stops sending frames; the choice is saved per browser. Tap-to-zoom is a 3× zoom around the tap point. The A6400
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

- **Software (2026-10-19):** v1 is feature-complete.
  - 84 tests against the simulator; ruff, mypy (strict) and the firmware build are green.
  - An independent review was done and its findings fixed.
  - The UI was checked at phone and desktop sizes, from localhost and over the LAN.
- **Pi:**
  - The code is deployed to `~/macrorail` and run by hand, because the systemd install needs the user's sudo.
  - Power is fine on the new PSU. Startup takes about 5 s.
  - **Run by hand:** `cd ~/macrorail && setsid nohup .venv/bin/macrorail > ~/macrorail.log 2>&1 < /dev/null &`
  - **Stop:** `pkill -f "^/home/pi/macrorail/[.]venv/bin/python"` (anchored, so it can't kill your own SSH shell).
  - **Deploy:** `git archive HEAD | ssh pi 'tar -x …'`. Never redirect SSH's stdin to `/dev/null` in that pipe.
  - **Flash:** `~/.local/bin/pio run -d firmware -e nano -t upload --upload-port /dev/ttyUSB0`.
    The app must be stopped first, because it owns the port.
- **Hardware bring-up so far:** breadboard per the setup guide `MacroRail-quick-start.pdf` (untracked; built from HTML in the session scratchpad).
  - **Driver:** detected over UART.
  - **Switch:** wired NO on D2, so `ENDSTOP_ACTIVE_LEVEL = LOW`.
  - **Motor direction:** `INVERT_DIRECTION = true`.
  - **Measured:** READY 1.6 s after the port opens; a STATUS round trip is about 10 ms. The link survived a 3,353-request stress test with 0 errors.
  - **Camera:** "Sony ILCE-6400 (PC Control)". Live view is 1024×680 at about 30 fps (the app caps it at 10). A capture is confirmed in 1.33–1.43 s. The battery drains while connected, so use a dummy battery for long stacks.
- **Lessons from bring-up:**
  - Test the UI over the LAN: `crypto.randomUUID` only exists on HTTPS or localhost.
  - An unclean session end leaves the A6400 stuck until it is power-cycled, so the app closes the session on shutdown.
  - Supervisors must never die. A link error once killed every background task; they now log and recover.
- **Firmware on the Nano:** protocol 2, with release-based homing and the re-armed switch. Flashed 2026-10-19. The Pi's config was refreshed from the new example; it had been unmodified.
- **Open:** the test suite failed once (1 of 10 full runs) and the failure wasn't captured. Suspect a timing-tight test, such as the 0.3 s switch-push test. Rerun under load and fix if it recurs.
- **Fixed after bring-up:** homing failed with SWITCH_STUCK because a fixed 1 mm back-off was shorter than the roller lever's release travel. Homing now backs off until the switch releases and reports the release distance. Next step: confirm on the hardware.

## Next: hardware bring-up (with the user)

1. **Homing:** confirm the new homing on the real switch, and note its reported release distance.
2. **Calibrate:**
   - Measure the real travel and set `travel_mm` (default 140).
   - Tune the run current: smooth, cool, no lost steps at 2.5 µm moves.
   - Tune the settle time on 4× live view.
3. **Camera:** measure the JPEG-download cost to decide whether a review gallery is worth it.
4. **Full stacks:** run them at 2× and 4×, including a 100+ shot stack and a camera unplug mid-stack.
5. **Pi install:** the user runs `~/macrorail/deploy/install.sh` (it needs sudo) for autostart.
6. **Release polish:**
   - README screenshots from the real setup, and a sample stack.
   - The date in the CHANGELOG, and a local `v1.0.0` tag.
   - Push to GitHub only when the user says so.

## Reference: old projects (read-only inspiration)

- `C:\Code\Mine\MacroScanner4`: rail CAD and measurements (its `agents.md`).
- `C:\Code\Mine\MacroScanner3`: previous software; its gphoto2 findings fed the decisions above.
- `C:\Code\Mine\MacroScanner2`: early FastAPI prototype with the Sony SDK (abandoned).
