# MacroRail

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
  - The range is always fully covered, and the rail returns to the start when the stack ends.
- **Works from a phone**
  - Dark, mobile-first UI.
  - One device is in control at a time, and handing control over is one tap.
  - Stop works from any device.

## Hardware

| Part | Notes |
|---|---|
| Rail | 3D-printed, two 8 mm rods, four SC8UU blocks, Tr8×8 lead screw, NEMA 17 (parts from an Anet A8). STLs and assembly notes: [`hardware/rail`](hardware/rail). |
| Controller | Arduino Nano + TMC2209 module at 12 V, roller microswitch for homing. Wiring: [`docs/wiring.md`](docs/wiring.md). |
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

Set the camera's USB connection to *PC Remote*. Check the Nano's serial port path in the
config (`ls /dev/serial/by-id/`).

## Shooting a stack

1. **Home** the rail. It finds the switch, then parks just in front of it.
2. **Find the front of the subject** on the live view with the jog buttons, and press **Set here** for Start.
   Tap the live view to zoom in; the button in its corner pauses or resumes it.
3. **Find the back of the subject** and press **Set here** for End.
4. **Choose a step size.** The summary and the Start button show how many shots it will take, plus the estimated time.
5. **Preview range** sweeps between the two points so you can check the framing.
6. **Start stack.** You can pause and resume. Stop returns the rail to the start.

**Step size.** Depth of field ≈ λ/NA² + e/(M·NA) (λ ≈ 0.55 µm, e = pixel pitch,
3.9 µm on the A6400). A step of about half the depth of field gives a safe overlap:

| Optics | Depth of field | Suggested step |
|---|---|---|
| 4× objective, NA 0.10 | ≈ 65 µm | 25–30 µm |
| 10× objective, NA 0.25 | ≈ 10 µm | 4–5 µm |
| 10× objective, NA 0.28 | ≈ 8 µm | 3.5–4 µm |

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

## License

- **Code:** [PolyForm Noncommercial 1.0.0](LICENSE). Free to use, study, modify and share for any
  noncommercial purpose.
- **Hardware designs:** [CC BY-NC 4.0](hardware/LICENSE).
