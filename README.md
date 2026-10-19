# MacroRail

[![CI](https://github.com/Sam-de-Ham/MacroRail/actions/workflows/ci.yml/badge.svg)](https://github.com/Sam-de-Ham/MacroRail/actions/workflows/ci.yml)

Focus stacking for macro and microscope-objective photography: a 3D-printed rail moves the
subject in micrometre steps while the camera takes a photo at each step. You run it all
from a phone or laptop.

A Raspberry Pi serves the web app, drives the rail through an Arduino Nano + TMC2209
stepper driver, and controls the camera over USB with gphoto2, including live view.

- **Precise and repeatable**
  - 2.5 µm steps (1/16 microstepping on an 8 mm-lead screw).
  - Silent StealthChop drive.
  - Every frame is approached from the same direction, so backlash never shifts a slice.
  - The home switch is interrupt-driven and always armed: its first contact stops the motor before its next step.
- **Nothing is assumed**
  - Each move is confirmed by the controller, and each shot by the camera, before the next step.
  - A camera hiccup pauses the stack instead of skipping a frame.
- **Simple to use**
  - Home, find focus on the live view, set start and end, preview the range, press Start.
  - Or let it find the range: a scan through focus finds where the subject starts and ends.
  - A step-size helper works out the step from the lens's magnification and aperture.
  - The range is always fully covered, and the rail returns to the start when the stack ends.
- **Check the result straight away**
  - Small copies of each shot are saved on the Pi and combined into a quick preview stack.
  - Camera settings (ISO, shutter, aperture, quality…) are set from the browser.
- **Calibrated and observable**
  - Measures the lead screw's backlash optically and suggests the take-up to use.
  - A diagnostics panel shows the motor driver, the serial link, the camera and the Pi's health.
- **Works from a phone**
  - Dark, mobile-first UI that can be installed as an app, and alerts you when a stack ends.
  - One device is in control at a time, and handing control over is one tap.
  - Stop works from any device.

## Hardware

| Part | Notes |
|---|---|
| Rail | 3D-printed, two 8 mm rods, four SC8UU blocks, Tr8×8 lead screw, NEMA 17 (parts from an Anet A8). STLs and assembly notes: [`hardware/rail`](hardware/rail). |
| Controller | Arduino Nano + TMC2209 module at 12 V, roller microswitch for homing. Step-by-step breadboard build: the [setup guide (PDF)](docs/setup-guide/MacroRail-setup-guide.pdf). Wiring reference: [`docs/wiring.md`](docs/wiring.md). |
| Computer | Raspberry Pi (tested on a 3B+, Raspberry Pi OS 64-bit, Debian 13). |
| Camera | Sony A6400 over USB in *PC Remote* mode. Other gphoto2-supported bodies with remote capture should work. |

## Try it without hardware

Any machine with [uv](https://docs.astral.sh/uv/):

```bash
uv run macrorail --sim
```

Open <http://localhost:8000>. The simulator models the controller (it speaks the same serial
protocol as the firmware), the carriage and a camera. Its live view gets sharper and
blurrier as the rail moves through focus.

## Install on the Raspberry Pi

1. **Flash the firmware** onto the Nano with [PlatformIO](https://platformio.org/), from any computer:

   ```bash
   pio run -d firmware -e nano -t upload
   ```

   Use `-e nano_new` for Nanos with the new bootloader.
2. **Install the app** on the Pi:

   ```bash
   git clone https://github.com/Sam-de-Ham/MacroRail.git ~/macrorail
   ~/macrorail/deploy/install.sh
   ```

   This installs uv and the dependencies, creates `~/.config/macrorail/config.toml`, and
   starts the `macrorail` service at `http://<pi-hostname>.local:8000`.
3. **Turn autostart on or off** at any time:

   ```bash
   sudo systemctl disable --now macrorail
   ```

   Use `enable --now` to turn it back on. To install without autostart, run
   `deploy/install.sh --no-autostart`. Logs: `journalctl -u macrorail -f`.

Check the Nano's serial port path in the config (`ls /dev/serial/by-id/`).

**Camera (Sony):** set *USB Connection* to *PC Remote*. For the review previews, also set
*PC Remote Settings → Still Img. Save Dest.* to *PC+Camera* and *PC Save Img* to *JPEG Only*:
full-resolution files (RAW too, if chosen) stay on the card and a JPEG comes over USB.

**As an app:** the page can be added to a phone's home screen. Browsers allow installing it,
and system notifications, only over HTTPS or on the Pi itself; over plain HTTP the stack alerts
still chime, vibrate and mark the tab title.

## Shooting a stack

1. **Home** the rail. It finds the switch, backs off until it opens, touches it again slowly, and
   parks just clear of it.
2. **Set the range.** Either jog to the front of the subject on the live view and press
   **Set here** for Start, then the same for End; or bring any part of it roughly into focus
   and press **Find range automatically**. Tap the live view to zoom in; the button in its
   corner pauses or resumes it.
3. **Choose a step size**, or open **Which step?**: from the magnification and numerical
   aperture it suggests half the depth of field (≈ λ/NA² + e/(M·NA)). The summary and the
   Start button show how many shots it will take, plus the estimated time.
4. **Preview range** sweeps between the two points so you can check the framing.
5. **Start stack**, optionally named. You can pause and resume. Stop returns the rail to the start.
6. **Review** shows each stack's shots and a quick all-in-focus preview built from them.

Once per setup, **System → Measure backlash** (with a sharp detail in focus) measures the
lead screw's play and offers the matching take-up distance.

## Development

```bash
uv sync                         # Python 3.13 environment with dev tools
uv run pytest                   # tests (run against the simulator)
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src                 # strict type checking
pio run -d firmware             # build the Nano firmware
scripts/deploy-dev.sh pi        # copy HEAD to the Pi over SSH and reinstall
```

- [`docs/architecture.md`](docs/architecture.md) explains how the parts fit together and why.
- [`docs/protocol.md`](docs/protocol.md) is the serial protocol between the Pi and the Nano.
- [`docs/wiring.md`](docs/wiring.md) covers wiring and first power-up checks.
- [`docs/setup-guide/`](docs/setup-guide/) has the illustrated setup guide and its generator.

## License

- **Code:** [PolyForm Noncommercial 1.0.0](LICENSE). Free to use, study, modify and share for any
  noncommercial purpose.
- **Hardware designs:** [CC BY-NC 4.0](hardware/LICENSE).
