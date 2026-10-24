# 3D scanning: first tests on the rig

Everything below is built and tested in the simulator only. Work through it in order; each
step relies on the ones before. Note anything odd (with the activity log's lines) and report
back.

## 0. Before plugging anything in

- [ ] On the Pi, set `port = "auto"` under `[rail]` in `~/.config/macrorail/config.toml`
      (it still holds a `/dev/serial/by-id/...` path, which both Nanos share), and add a
      `[module]` section with `port = "auto"` (see `deploy/config.example.toml`).
- [ ] Deploy the `3d-scanning` branch and restart the app. **2D must work exactly as before.**
- [ ] Wire the module per the [wiring guide](module-guide/MacroRail-module-wiring-guide.pdf),
      motors unplugged from their drivers at first, and flash `firmware-module/`.

## 1. Module and Rig tab (milestone 1)

- [ ] System (3D): the Scan module card says Connected; the port shown is a `/dev/ttyUSB*`.
- [ ] The rail still connects (the two Nanos are told apart by their first line).
- [ ] Hall sensor: about 512 with no magnet; turning the head by hand past the magnet moves
      it well away. The tilt switch shows Pressed / Released as you press it.
- [ ] Plug the motors in. Rig: jog yaw ±5° and tilt ±5° (before homing, tilt is limited to
      10° per click). Check each turns the way its button says.
- [ ] **Home.** Tilt goes up to the switch, backs off and touches it slowly, then parks clear
      of it; yaw turns past the magnet and comes back to it. Repeat a few times: the angles
      should return to the same place.
- [ ] Quick poses: Level, Top view, Belly view (−20° until tilt is calibrated), the screws'
      poses. Watch the lens: nothing may touch it.
- [ ] Tilt torque near +90° (the gearbox holds the cradle?), and Stop during a move.

## 2. Calibration (milestone 2)

- [ ] System → **Measure yaw turn** (nothing on the holder): about 4076 half-steps.
- [ ] **Level tilt** with a straight pin upright in the holder, rail homed, pin in focus.
      The switch angle should come out near 97°, and the cradle should look level after.

## 3. Centring (milestone 3)

- [ ] Mount an insect, home, focus on it, Centre → **Measure**. Check the advice: turning the
      named screw the shown amount should bring it closer (the dashed live-view line marks
      the axis). Two or three rounds to "Centred".
- [ ] **Measure height**, slide the pin as told, measure again.

## 4. Scans (milestone 4)

- [ ] Scan: set a small plan first (one ring, yaw step 90°), **Test this pose**, then
      **Start scan**. Try Pause / Resume and Stop, then Continue.
- [ ] Restart the app mid-scan (only when you mean to): Continue should skip the poses done.
- [ ] Then a full scan with a dummy battery.

## 5. Review and export (milestone 5)

- [ ] Review (3D): the scan's poses as thumbnails; each opens the usual viewer.
- [ ] **Download for 3D** and try the `images/` folder in Meshroom or COLMAP.
