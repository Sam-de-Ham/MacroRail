# 3D scanning software: plan

**Agreed with the user on 2026-10-24.** This is the spec the implementation follows; the hardware facts it relies on are in [`3d-scanning.md`](3d-scanning.md).

## What we're building

A 3D scan is many ordinary focus stacks, one per **pose** (a tilt and a yaw angle of the
insect). The 3D workspace adds three things on top of today's app: moving the two new axes,
centring the insect on them, and running and reviewing a whole series of poses.

```
Mount pin ─▶ Centre (wizard) ─▶ Plan (rings × yaw) ─▶ Scan (per pose: rotate → focus → stack)
          ─▶ Review (pose map, previews) ─▶ Export (pose table + files for Zerene/COLMAP)
```

## Ground rules

- **2D stays exactly as it is.** The only change in 2D is a 2D/3D switch in the top bar.
  The rail firmware isn't touched at all (see the next section).
- **Same app, same feel.** The 3D workspace reuses the layout (live view left, tabs right),
  the cards, buttons, toasts and alerts. Same architecture: one owner per device, push state,
  never act on assumptions, one operation at a time, Stop from any device.
- **A 3D stack is a 2D stack.** The scan runner calls the same stack code the Shoot tab uses,
  so focus, backlash take-up, settle, camera retries and previews behave identically.
- **Simulator first.** Every feature works and is tested in `--sim` before it touches the rig.
- **Every milestone** ends with the usual checks green, a commit, `agents.md` updated, and a
  test on the rig by you.

## 1. Electronics: a second Nano for the module (recommended)

One Nano *could* run all three motors (the pins fit exactly), but a second Nano is the
cleaner design:

- **2D can't break:** the rail firmware stays byte-for-byte what you tested. No protocol bump,
  no reflash of the rail.
- **Timing:** the rail's driver UART (SoftwareSerial) blocks interrupts, which would stall the
  28BYJ-48 stepping. Separate controllers can't disturb each other.
- **Pins:** one Nano would be full with nothing spare. A module Nano has room for v2 (the
  centring motors would then need a Mega for the module only, not a rewrite of the rail).
- **Unplug the module:** the rail is exactly today's rig.
- **Cost:** one more USB port on the Pi (camera, rail, module: 3 of 4) and one more cable.

**Finding the right port:** both Nanos are CH340 clones with no serial number, so their
`/dev/serial/by-id` names collide. The module firmware announces itself (`! READY …
role=module`); the host finds it by probing at start-up, and the rail keeps its port. A
fixed `/dev/serial/by-path` (USB socket) can be set in `config.toml` instead.

**Wiring (module Nano):**

| What | Nano pin | Notes |
|---|---|---|
| Yaw ULN2003 IN1–IN4 | D2, D3, D4, D5 | |
| Tilt ULN2003 IN1–IN4 | D6, D7, D8, D9 | |
| Tilt switch (C → GND, NO → pin) | D10 | `INPUT_PULLUP`, active low, like the rail's |
| KY-024 analog out | A0 | its digital out and pot unused |
| ULN2003 power | separate 5 V supply | ground shared with the Nano; not from USB (2 × ~240 mA) |

Written up in `docs/wiring.md` with a picture, as for the rail.

## 2. Module firmware (`firmware-module/`, new PlatformIO project)

- **Same protocol style** as the rail: `<id> COMMAND args`, `OK`/`ERR`, `!` events, 2 s link
  watchdog, one motion at a time, `STOP` from anywhere. Documented in
  `docs/protocol-module.md`. Commands name the axis: `MOVE TILT …`, `HOME YAW …`.
- **Stepping:** AccelStepper in half-step mode (already a dependency, proven on the rail),
  with a speed ramp. With the coils off a rotor may settle by half a motor step (0.09° at
  the output); the next move's energised coils pull it back, so the count stays right.
- **Coils off when idle**, after a short settle. The gearbox holds the cradle (60–120 mN·m
  friction vs ~40 needed); no heat near the insect, no 480 mA idle draw.
- **Tilt homing:** the rail's proven sequence: seek slowly *away from the lens*, back off until
  released, re-approach slowly; that contact is the home angle. The switch is always armed.
  Soft limits once homed.
- **Yaw homing:** turn one way while sampling A0, find the magnet's field peak (the centre of
  the samples above half height, which is far more repeatable than one threshold), then turn
  on round and approach it from the same side.
- **Calibration helpers:** `HALL` (raw reading, for diagnostics), and a routine that measures
  steps per yaw turn from two peaks. The 28BYJ-48's gearbox (~63.68:1) gives a non-integer
  ~4076 half-steps per turn, so we measure it instead of trusting the datasheet.

## 3. Host

| Module | Job |
|---|---|
| `motion/module.py` | The module controller: connection supervision, status, homing, moves. Reuses `Link` unchanged. Exposes `tilt` and `yaw` as rotary axes in **degrees**. Tilt limits −33° to +90° enforced here *and* in firmware. |
| `scan/plan.py` (pure) | Poses from rings (tilts) × yaw step, in a fixed order: tilt rings top to bottom, yaw only ever increasing (no unwinding; nothing electrical turns with the head). Every arrival from the same side (backlash). Shot, time and storage estimates. |
| `scan/centring.py` (pure) | The centring fit: positions at N yaw angles → offset (x, y) and where the axis is in the image; then screw turns. Height error from two tilts. |
| `scan/runner.py` | Per pose: rotate → settle → focus range → **the existing `StackRun`** → pose preview. Pause, resume, Stop like a stack. A camera error pauses it; resume retakes that pose's slice. |
| `machine.py` | New operations (home module, move pose, calibrate, centre, scan) with the same preconditions style. Stop stops both controllers. One operation at a time across everything. |
| `review/` | A scan folder: one record (plan, calibration, every pose with its camera file names), one preview and depth map per pose, and the export. |

**Resume after a restart.** A full scan is 6–8 hours. The scan record is written after every
pose, so after a power cut or restart you re-home and press Resume: finished poses are
skipped. (Centring is mechanical, so it survives a restart.)

**Pre-flight check before a scan starts:** module and rail homed, camera connected and
battery (warn without a dummy battery), Pi disk space for the previews, the camera card's free
space if the camera reports it (JPEG fine ≈ 10 MB × ~9,400 shots ≈ 94 GB), and the tilt
range inside the limits. It shows what's wrong instead of failing after an hour.

**Pi storage:** today each stack keeps every frame as a 1600 px JPEG. For ~9,400 frames that
is ~2.3 GB, so a scan keeps each pose's preview and depth map plus every 10th frame
(the interval is a setting). Full-size files stay on the camera card, as now.

## 4. Calibration (once per machine; System tab, 3D workspace)

Both are built (`scan/calibrate.py`, `Machine.calibrate_yaw/tilt`). The results live in their
own file, `module.json` next to `settings.json`, so the 2D settings file stays readable by a
2D-only version of the app (its settings model forbids unknown sections). Only the
calibrations write it; there is no settings edit for it.

- **Yaw steps per turn:** home yaw, turn three turns (by the current value), home again. The
  second homing reports where it found the magnet in the old frame (`from=`), which is three
  true turns. Refused if it is more than 2 % from nominal (the head slipping on its shaft).
- **Tilt level:** a straight pin stands upright in the holder, in focus at the current rail
  position. At +10° and −10° the app focus-sweeps it (2 mm, one DOF per frame) and reads the
  rail position where its top and bottom tile rows are sharpest. The rise (top − bottom) is
  k·sin(true tilt), so with true = commanded + e:
  tan e = tan 10° · (rise₊ + rise₋) / (rise₊ − rise₋), whatever k (pin length, rail
  direction) is. A pin leaning in the head frame adds equal and opposite rises at yaws 180°
  apart, so each tilt is measured at yaw 0° and 180° and averaged. `tilt_switch_deg` += e,
  and tilt opens to its full range (−33°). The result includes the constant gearbox
  backlash offset between homing and pose arrivals, which is what poses need.
- **Image scale:** from the optics settings the app already has (magnification and pixel
  size). The rail gives the depth direction in exact mm, as a cross-check.

## 5. Centring wizard

1. **Mount** (the button turns the head so the clamp screw faces you, cradle level).
2. **Measure:** the app turns yaw to 0°, 90°, 180°, 270°. At each angle it runs a short focus
   scan (depth, in exact mm from the rail) and finds the insect in the sharpest live-view
   frame (sharpness-weighted centroid: sideways, in pixels → mm).
3. **Fit:** sideways and depth both follow one circle; the fit gives the insect's offset
   from the yaw axis, and the axis's own position in the image.
4. **Adjust:** "Turn screw X ¾ turn in." The head turns so that screw faces you; a dial shows
   how far to turn. 0.5 mm per turn.
5. **Check:** measure again; repeat until the offset is under ~0.1 mm (usually 2 rounds).
6. **Height:** measure at two tilts; if the insect is above or below the tilt axis, it says
   how far to move the pin with the gauge.

## 6. UI

**Top bar:** a 2D | 3D switch, remembered per browser. In 3D without the module connected,
the 3D-only controls are disabled with a plain message; the rail and camera still work.
If a 3D scan is running, opening the app goes to 3D.

**3D workspace tabs** (live view stays on the left):

| Tab | Contents |
|---|---|
| **Rig** | Rail position card (same as Shoot). Tilt and yaw: home, jog (±1°, ±10°), go to angle. Quick poses: **Level**, **Top view**, **Mount**, **Face screw X / Y**. |
| **Centre** | The wizard above, with its plot and screw dial. |
| **Scan** | Plan (tilt rings, yaw step, focus mode, settle), summary (poses, shots, time, Pi disk, card), pre-flight check, **Test one pose**, Start / Pause / Resume / Stop, progress. |
| **Camera** | The same tab as 2D. |
| **Review** | Scans: pose map with thumbnails, each pose's preview and depth map (today's viewer), export. Plain stacks stay in the 2D Review. |
| **System** | The same as 2D, plus a **Scan module** card: connection, diagnostics (hall signal, switch), calibration. |

**As built (2026-10-24), where it differs from the table:** jog steps are 1°, 5°, 15° and
45° (tilt capped at 10° before homing); quick poses are Level, Top view, Belly view (the
lowest allowed tilt), Screw X / Y to you and Yaw zero (no separate Mount pose: the screws'
poses and Level cover it); the live-view corner shows the angles as text beside the rail
position; Review shows a scan's poses as a thumbnail grid (each opens the stack viewer)
rather than a hover map; the top bar's Stop stops a scan, as it does a stack; during a scan
the alerts are the scan's (complete, stopped, failed, paused for the user) plus any camera
problem, not each pose's stack. On phones the six 3D tabs sit in two rows.

**Visualisations:**

- **Pose gauges** (Rig tab, and small in the live-view corner like the rail position): a
  side view of the cradle with the tilt angle and the shaded no-go zone below −33°, and a top
  view dial for yaw with screws X and Y marked.
- **Pose map** (Scan and Review): yaw across, tilt down; each pose a dot: planned, done (its
  thumbnail on hover), current, failed. Click a done pose to view it, or a planned one to go
  there.
- **Centring plot** (Centre tab): the measured points, the fitted circle and the axis, and the
  offset shrinking round by round.
- **Live-view overlay** (3D only): a crosshair where the yaw axis appears in the image, so you
  can see at a glance whether the insect sits on it.

## 7. Scan flow and numbers

- **Default plan:** tilt rings −30°, 0°, +30°, +60°, yaw every 36° → 40 poses. Rings and the
  yaw step are settings; a top view at +90° is one more ring.
- **Per pose:** rotate (seconds), focus range (~15 s from live view), stack (~78 shots ×
  2.4 s ≈ 3 min at 4×). About 2.5 h for the default 40 poses; the summary shows the real estimate before you
  start.
- **Focus per pose:** auto range at every pose (what `focus/` was built for), clamped to a
  maximum span with a margin, with a fixed range as the alternative (decision below).

## 8. Export

- **For full quality:** a pose table (CSV + JSON: pose, tilt, yaw, focus range, and the camera
  file names of every shot), so the full-size files from the card can be batch-stacked in
  Zerene per pose, then fed to COLMAP or Meshroom with known angles.
- **Quick check:** the per-pose previews (1600 px, already stacked on the Pi) as a ready
  folder for a draft photogrammetry run.

## 9. Testing

- Pure unit tests: scan plan, centring fit (synthetic offsets, noise), pose table.
- Firmware: built in CI next to the rail firmware; the protocol mirrored by a simulated
  module.
- **Simulator:** a simulated module (switch at +97°, hall field, gearbox backlash,
  non-integer steps per turn) and a simulated camera whose subject moves with yaw, tilt and a
  hidden centring offset, so the wizard and whole scans run end to end in tests.
- The 2D tests stay unchanged and must keep passing.

## 10. Milestones (each tested by you on the rig)

All five are built and tested in the simulator (2026-10-24); none on the rig yet.

1. **Wiring + module firmware + host driver + Rig tab:** home and move both axes from the app,
   pose gauges, quick poses. *You check: homing repeats, torque at +90°, switch angle.*
2. **Calibration:** yaw steps per turn, tilt level, live-view axis crosshair.
3. **Centring wizard.** As built: each round sweeps focus at yaw 0/90/180/270 (tilt 0), takes
   the sharpest frame's detail centre sideways, fits the offset, and advises screw turns in
   1/8 turns with a dial each and a "screw to you" button. It learns the rail's direction
   (needed for the height) and where the yaw axis appears (the dashed live-view line).
   Height: focus at tilt ±20° (inside the uncalibrated range), then "push/pull the pin".
4. **Scans.** As built: tilt rings top down, yaw always forwards; yaw is homed at each scan's
   start (so its count never runs out); the step, stack settle and focus span are fixed in
   the scan's record, and those settings can't change mid-scan; per pose: turn → settle → auto range (falls back to
   the last range; with none, the scan stops so the user can focus, then Continue) → stack with the 2D step → preview
   and depth map → keep one frame in n. `scan.json` after every pose; Continue skips the
   poses done. "Test this pose" runs one pose at the module's current angle.
5. **Review and export.** As built: scans list in the 3D Review tab, pose thumbnails open
   the usual viewer (preview, depth, 3D relief, frames). "Download for 3D": `images/` with
   one all-in-focus JPEG per pose named `pose-NNN_tilt+SSS_yawYYY.jpg`, `depth/`,
   `poses.csv` (angles, stack, camera file names), `scan.json`, `about.json`.

## Decisions (user, 2026-10-24)

1. **A second Nano** runs the module.
2. **Auto range at every pose.** Auto range hasn't been tested much on real subjects yet, so
   the scan checks each result and falls back to the last good range rather than failing.
3. **Pi storage:** each pose keeps its preview, its depth map and every 10th frame.
4. **Default plan:** rings −30°, 0°, +30°, +60°; yaw every 36°. All configurable.
5. **Electronics guide:** an illustrated PDF for wiring the module, like the rail's setup guide.
6. **Verification:** simulator tests, screenshots of every screen, and independent adversarial
   reviews of each milestone before it is committed.

## Later (not in this plan)

- A live-view "draft scan" (sweep without the shutter) to check coverage in minutes.
- Tiling for insects bigger than the frame; motorised centring (v2); a 3D sphere view of the
  pose map; lighting control.
