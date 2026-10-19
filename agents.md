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
- **v1.1 (built, untested on hardware; user's picks from the ideas list):** auto start/end,
  step-size helper (popup), tabbed UI, camera settings, stack names, small JPEG copies + review
  gallery + quick preview stack, stack-done alerts + installable app, diagnostics, backlash
  measurement, upkeep. README screenshots/photos come later from the user.
- **Next major:** a rotation stage (3D scanning): focus scans are built to be rerun per angle.
- **Deferred:** 3D printer as motion source (Marlin, new `Axis`), relay shutter trigger (D9
  reserved, new `Camera`), one-click flashing, PCB.
- **Not wanted for now (user):** focus peaking, sharpness meter, lens profiles, grid overlay,
  auto settle, multi-shot, export, bad-frame detection, hold-to-jog, keyboard shortcuts,
  first-run wizard, repeatability test, Tr8×2 screw, docs site.

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
  - **Noise filter (user decision):** outside homing, a contact must still be closed a few µs
    later, which rejects motor-noise spikes. Homing (seek and probe) takes the very first blip,
    because the switch stopped 2–3 mm after its click (release distance 3.79 mm), possibly from
    contact chatter.
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
- **Focus scans** (`focus/`): sharpness = Laplacian energy per tile (8×6) of live-view frames.
  - Auto range: tiles whose peak is ≥ 2× their median are subject; the range is where any of
    them is above halfway to its peak, plus half a step. Warns if clipped by the scan span.
  - Backlash: coarse sweep picks the most contrasty tile; then 2 rounds of forward + backward
    fine sweeps (DOF/4 steps) over a window sized for up to 0.25 mm. Backlash = the shift that
    best matches the backward curve onto the forward one (not peak fitting: a broad or noisy
    top threw peaks off by 35 µm). Take-up suggested = 2× backlash + one DOF.
  - Every scan returns the rail to where it began (also when nothing was found; not after Stop).
- **Previews/review:** the runner downloads each shot's JPEG in the background (needs the camera
  set to PC+Camera, PC Save Img: JPEG Only), shrinks it to 1600 px into
  `stacks/<id>/frames/`, and builds `preview.jpg` (per-pixel sharpest frame) after the stack.
- **App/alerts:** manifest + a service worker without caching (a stale UI could mismatch the
  server). Notifications and install need HTTPS or localhost; chime/vibration/title work on
  HTTP after the page was touched once.
- **Diagnostics** refresh every 5 s; the driver (`DRIVER`, protocol 3) is read only while idle.
- **License:** PolyForm Noncommercial 1.0.0 (code), CC BY-NC 4.0 (hardware).

## Repository map

`firmware/` Nano (PlatformIO) · `src/macrorail/` app (`motion/`, `camera/`, `stack/`, `sim/`,
`machine.py`, `api.py`, `web/`) · `tests/` · `deploy/` install + service · `scripts/deploy-dev.sh` ·
`docs/` protocol, wiring, architecture · `hardware/rail/` STLs + assembly guide.

## Status

- **Released:** v1.0.0 on 2026-10-19, public at https://github.com/Sam-de-Ham/MacroRail (tag, GitHub release, CI green).
  - `gh` here defaults to the work account (TT-SaWe), so push with the Sam-de-Ham token per command.
  - `CLAUDE.md` is kept local (gitignored).
- **Software (2026-10-19):** v1.1 features built and committed locally (not pushed).
  - 109 tests against the simulator; ruff, mypy (strict) and the firmware build are green.
  - Every tab was checked in the simulator at desktop and phone sizes; auto range and backlash
    give the simulated values (backlash exact for 0.04–0.15 mm at 2×, 4× and 10×).
- **Pi:**
  - The code is deployed to `~/macrorail` and run by hand, because the systemd install needs the user's sudo.
  - Power is fine on the new PSU. Startup takes about 5 s.
  - **Run by hand:** `cd ~/macrorail && setsid nohup .venv/bin/macrorail > ~/macrorail.log 2>&1 < /dev/null &`
  - **Stop:** `pkill -f "^/home/pi/macrorail/[.]venv/bin/python"` (anchored, so it can't kill your own SSH shell).
  - **Deploy:** `git archive HEAD | ssh pi 'tar -x …'`. Never redirect SSH's stdin to `/dev/null` in that pipe.
  - **Flash:** `~/.local/bin/pio run -d firmware -e nano -t upload --upload-port /dev/ttyUSB0`.
    The app must be stopped first, because it owns the port.
- **Hardware bring-up so far:** breadboard per the setup guide `docs/setup-guide/MacroRail-setup-guide.pdf`. Rebuild it with `docs/setup-guide/build_html.py`, then print to PDF.
  - **Driver:** detected over UART.
  - **Switch:** wired NO on D2, so `ENDSTOP_ACTIVE_LEVEL = LOW`.
  - **Motor direction:** `INVERT_DIRECTION = true`.
  - **Measured:** READY 1.6 s after the port opens; a STATUS round trip is about 10 ms. The link survived a 3,353-request stress test with 0 errors.
  - **Camera:** "Sony ILCE-6400 (PC Control)". Live view is 1024×680 at about 30 fps (the app caps it at 10). A capture is confirmed in 1.33–1.43 s. The battery drains while connected, so use a dummy battery for long stacks.
- **Lessons from bring-up:**
  - Test the UI over the LAN: `crypto.randomUUID` only exists on HTTPS or localhost.
  - An unclean session end leaves the A6400 stuck until it is power-cycled, so the app closes the session on shutdown.
  - Supervisors must never die. A link error once killed every background task; they now log and recover.
- **Firmware on the Nano:** protocol 2 (release-based homing, unfiltered homing contact). Protocol 3 (`DRIVER`) must be flashed with the v1.1 app.
- **Homing on hardware:** works. The measured release distance is 3.79 mm, but a microswitch should be well under 1 mm, and the user hears the click 2–3 mm before the stop.
  - Wiring is C + NO (open at rest, closed when pressed).
  - Suspects: contact chatter rejected by the noise filter (now unfiltered while homing), or a worn switch.
  - Next: flash, re-home, and compare the release distance. If it is still about 3–4 mm, the user checks the switch with a meter (does C–NO beep exactly at the click?) or replaces it.
  - Flash is pending until the Pi is reachable (SSH was timing out).

## Next

- The user tests v1.1 on hardware (12 V + camera) from the checklist given on 2026-10-19:
  homing release distance, auto range, backlash, camera settings, previews/review, alerts,
  diagnostics. Fix what they find, then release v1.1.0 (CHANGELOG date, tag, push when agreed).
- Hardware items still open are below.

## Hardware bring-up (with the user)

1. **Homing:** re-home on the current firmware and compare the release distance with 3.79 mm.
2. **Calibrate:**
   - Measure the real travel and set `travel_mm` (default 140).
   - Tune the run current: smooth, cool, no lost steps at 2.5 µm moves.
   - Tune the settle time on 4× live view.
3. **Camera:** check that JPEG downloads don't slow a stack, and which settings the A6400 exposes.
4. **Full stacks:** run them at 2× and 4×, including a 100+ shot stack and a camera unplug mid-stack.
5. **Pi install:** the user runs `~/macrorail/deploy/install.sh` (it needs sudo) for autostart.
6. **Release polish:**
   - README screenshots and photos from the real setup (the user supplies them), and a sample stack.
   - Push to GitHub only when the user says so.

## Reference: old projects (read-only inspiration)

- `C:\Code\Mine\MacroScanner4`: rail CAD and measurements (its `agents.md`).
- `C:\Code\Mine\MacroScanner3`: previous software; its gphoto2 findings fed the decisions above.
- `C:\Code\Mine\MacroScanner2`: early FastAPI prototype with the Sony SDK (abandoned).
