# Changelog

## Unreleased

### Focus stacking

- Tabbed interface: a fixed live view with Shoot, Camera, Review and System tabs, and a
  status strip showing whatever is running.
- Auto range: a scan through focus finds where the subject starts and ends.
- Step-size helper from the lens's magnification and numerical aperture.
- Backlash measurement from live view, with a suggested take-up.
- Camera settings in the browser (ISO, shutter, aperture, exposure compensation, white
  balance, quality, size, focus mode) and a test shot.
- Stack names; small JPEG copies of each shot kept on the Pi; a review gallery with a quick
  all-in-focus preview stack, and a zip download of a stack's previews.
- A rough depth map with each preview stack: false colour, a 3D relief with the stack laid
  over it (drag to turn, pinch to zoom), and a 16-bit grey PNG for Blender.
- While a stack runs, the live-view panel shows each shot as it arrives; pause holds one.
- Installable as an app; a chime, vibration, tab title and (over HTTPS) a notification when a
  stack ends or needs attention.
- Diagnostics: motor driver status, link round trip, camera, and the Pi's temperature, power,
  load, memory and disk.
- Firmware protocol 3: `DRIVER` reports the TMC2209's status. Reflash the Nano.
- CI on current actions, a CI badge, and steadier switch tests.
- Faster homing: the seek and the second touch both run at 2 mm/s, backing off 1 mm past the
  switch's release. Config files that still name the old probe speed keep loading.
- The rail's serial port defaults to `auto`: the app finds the Nano by what it reports.
- A log warning when the Pi goes under-voltage (USB devices may then drop out).

### 3D scan module

- An optional bolt-on module for multi-angle scans: a printed fork on the carriage with a
  motorised tilt cradle (−33° to +90°) and yaw head (two 28BYJ-48s), a roller switch for tilt
  home, a hall sensor for yaw home, and a hand-adjusted centring plate with a pin clamp.
  CAD scripts, STLs, test pieces and an assembly guide in `hardware/scan-module/`.
- Its own Arduino Nano and firmware (`firmware-module/`, protocol v1), with a wiring guide.
  The rail's firmware and protocol are unchanged.
- Port auto-discovery tells the two Nanos apart; the module keeps its homing across
  reconnects and app restarts.
- A 2D / 3D switch in the app. 2D is unchanged; 3D adds Rig, Centre and Scan tabs and a Scan
  module card in System.
- Calibration: yaw half-steps per turn from two magnet peaks, and tilt level from a straight
  needle.
- Centring: measurements at four yaws, a circle fit, screw advice in eighths of a turn with a
  dial per screw, self-correcting screw directions, Spin for rough centring, and the height
  above the tilt axis. The yaw axis is drawn in live view.
- Scans: tilt rings × yaw step, an estimate and pre-flight checks, a test pose, pause, resume,
  and continue after a stop or restart. Each pose is a focus scan and an ordinary stack.
- Manual tilt: scan with tilt set by hand; the scan pauses for each ring.
- 3D Review: each scan's poses as thumbnails opening the stack viewer, and a "Download for
  3D" zip with one all-in-focus image per pose named by angle, depth maps and a pose table.
- Simulated module and specimen for development and tests.

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
