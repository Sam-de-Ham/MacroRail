# Design notes

The main engineering decisions, why they were made, and what the hardware taught along the way.
The structure of the code is in [architecture.md](architecture.md).

## Rail

### Homing on a roller microswitch

The home switch is a roller-lever microswitch on D2, the Nano's INT0 pin. It is read by a
hardware interrupt and is armed in every motion, not only during homing: the first contact
latches a flag, and the step loop stops before its next step, with no deceleration ramp. A
polled switch could be missed during a fast move; an interrupt can't.

Three things came out of testing on the rig:

- **The switch releases far past its trip point.** The measured hysteresis was 3.79 mm, which
  is large for a microswitch but typical of a long roller lever. A fixed back-off distance
  therefore ended with the switch still pressed (`SWITCH_STUCK`). The firmware now backs off
  until the switch has stayed open for 2 ms (at most 5 mm), then 1 mm further, and reports
  the release distance so it can be checked.
- **The contact is noisy at first touch.** The electrical contact closed 2–3 mm after the
  audible click, and its first closures were short blips. Outside homing, a contact only
  counts if it is still closed a few microseconds later, which rejects motor noise. During
  homing, where the switch is expected, the very first edge counts. With that change homing
  became reliable.
- **No separate slow approach.** The original sequence re-approached at a lower speed.
  Because the interrupt stops the motor on the first edge, the re-approach now runs at the
  seek speed (2 mm/s, up from 1 mm/s). Position 0 is the second contact.

After homing, the rail parks at whichever is further from the switch: the soft limit
(0.5 mm) or the release point plus the clearance. That way the switch rests open and armed.

A move that starts on the pressed switch and backs away ignores it only until it has released;
moves towards a pressed switch are refused.

### Backlash

The lead screw is a Tr8×8 (8 mm per turn, not self-locking) with a T8 brass nut on a floating
carrier. Backlash measured optically on the rig is 14 µm ± 7 µm, close to half of a 32.5 µm
stack step at 4×, so it matters.

Rather than compensating, the motion avoids it: every arrival at a start or end point ends
with a move in the stack direction (overshooting by the take-up first if needed), and a stack
only ever moves forward. The nut is then loaded the same way for every frame. The take-up is
0.1 mm on the rig; the default is 0.3 mm until the backlash has been measured. The
simulator models 0.04 mm of backlash, so tests catch any arrival from the wrong side.

### Driver and current

The TMC2209 runs in StealthChop at 1/16 microstepping with 256× interpolation: 2.5 µm per
microstep, and quiet. CoolStep and StallGuard are off; homing uses the switch.

The motor runs at 600 mA and holds at 200 mA. Full current is applied from the first move of
an operation until the rail has been idle for 30 s. The current is never changed during a
stack: lowering it while the rotor sits between full steps can let it slip by a fraction of a
step, which would show as an uneven slice.

Turning the motor off clears the homed flag. The screw is not self-locking, so an unpowered
carriage can be pushed.

### Half-duplex serial around the driver UART

The Nano has one hardware UART, used for the Pi. The TMC2209's single-wire UART therefore runs
on SoftwareSerial (D7 receive, D8 transmit through 1 kΩ), which disables interrupts while it
transfers a byte. Bytes arriving from the Pi during that time are lost.

The fix is a protocol rule, not a buffer: the firmware talks to the driver only while
answering a request (`STATUS` when idle, `ENABLE`, `CURRENT`, `DRIVER`), and the host sends
nothing while a request is unanswered. The one exception is a motion command: once it is
sent, `STATUS` and `STOP` may follow, because the firmware never touches the driver while
moving. The link survived a stress test of 3,353 requests with no errors.

A board with a second hardware UART (an ATmega2560, for example) would remove the rule.

### Link supervision

Requests carry ids, and motion commands reply only when the motion has finished, so the host
never assumes where the rail is. `STATUS` is polled every 0.5 s and doubles as the firmware's
watchdog: if no line arrives for 2 s during a motion, the firmware decelerates to a stop. A
missing reply on the host side means the link is dead, and it is rebuilt from scratch.

The background supervisors (rail, module, camera, diagnostics) catch everything and
reconnect. An early version let one link error end every background task at once.

## Camera

The A6400 is driven over USB with libgphoto2, in PC Remote mode. A shot is `trigger_capture`
followed by waiting for the camera's `FILE_ADDED` event, so a slice is only counted once the
camera has written it. A blocking `capture()` call, used in an earlier version of this
project, dropped the USB session on Sony bodies and was abandoned.

If no `FILE_ADDED` arrives within 10 s, or gphoto2 reports an error, the session is re-opened
and the shot retried once. If the first trigger did fire, this costs a duplicate frame; it
never leaves a gap. A second failure pauses the stack, and resume retakes that slice.

All gphoto2 calls run on one worker thread. Full-size files stay on the card; with
"PC+Camera" and "JPEG only" set, the camera also sends a JPEG, which is downloaded while the
rail moves on and shrunk to 1600 px for review. A capture is confirmed in 1.33–1.43 s.

The session is closed cleanly on shutdown. An unclean exit (SIGKILL) leaves the A6400 unable
to connect until it is power-cycled.

## Focus scans

A focus scan steps the rail through a span and reads the sharpness of each live-view frame
(1024 × 680) per tile, as the Laplacian energy of an 8 × 6 grid. Live view is used instead of
shots: it is fast and costs no shutter wear.

- **Auto range.** A tile counts as subject if its peak is at least twice its median over the
  scan. The range is where any subject tile is more than halfway from its median to its peak,
  plus half a step at each end. If the subject was still sharp at an edge of the scan, the
  result says the span clipped it.
- **Backlash measurement.** A coarse sweep picks the most contrasty tile. Then two rounds of
  forward and backward fine sweeps (a quarter of the depth of field per step) run over a
  window that covers up to 0.25 mm of backlash. The backlash is the shift that best matches
  the backward sharpness curve onto the forward one. Fitting the two peaks was tried first;
  a broad or noisy peak moved the estimate by up to 35 µm, while matching the whole curve uses
  the steep flanks. The suggested take-up is twice the backlash plus one depth of field.
- Every scan returns the rail to where it started, also when nothing was found, except after
  Stop.

The step helper uses depth of field = 0.55/NA² + pixel/(M·NA) µm and suggests half of it,
rounded to the 2.5 µm grid. For the AmScope Plan 4/0.10 at 4.27× that is 64 µm and 32.5 µm.

## Preview stacks and depth maps

After each stack the Pi builds a quick preview: for every pixel, the frame that is sharpest
there. It is meant for checking a stack, not for final output; full-resolution stacking
belongs in Zerene Stacker or Helicon Focus.

The depth map comes from the same pass. Each pixel's height is the focus position of its
winning frame, averaged over 1 % of the image width weighted by sharpness, so detailed areas
decide and flat areas follow them. Areas with less than 5 % of the strongest detail fade to
the far end, which keeps featureless background from standing up as a wall. Which end is
nearer the camera depends on the rig and the stack direction, so the 3D view has a flip
control. Without the magnification in the record the height scale is relative.

Per-view depth maps are rough by nature. Proper 3D models of insects come from many views and
photogrammetry, which is what the scan module is for.

Stack and scan zips are written uncompressed and streamed chunk by chunk, so no temporary
file lands on the Pi's SD card.

## Scan module

### A second Nano

The module has its own Nano rather than sharing the rail's:

- the rail firmware and its protocol stay exactly as they are;
- the rail's SoftwareSerial transfers block interrupts, which would stall the 28BYJ-48
  stepping;
- one Nano would have no pins to spare.

The cost is one more USB port and cable. Both Nanos are CH340 clones without serial numbers,
so their `/dev/serial/by-id` names collide. With `port = "auto"`, the host probes each USB
serial port and reads the `READY` line; the module's carries `role=module`. Ports are opened
exclusively, so a search can never read the other link's traffic, and a port known to belong
to the other controller is never probed (opening it would reset that Nano).

### Keeping the module's homing across reconnects

Opening a serial port raises DTR, which resets a Nano through its auto-reset capacitor.
Linux drops DTR again when the port closes (the HUPCL flag), so every reconnect, whether a
USB hiccup or an app restart, would reset the module and lose its homing. For the module's
port HUPCL is cleared after the first open: DTR stays up, later opens find the Nano running,
and the host asks it with `INFO` when no `READY` arrives. A real power loss still resets it.
The rail keeps the reset on every connection.

### 28BYJ-48 motors

The 28BYJ-48 runs in half-step mode through a ULN2003 at 5 V from its own supply (about
240 mA per motor while moving, too much for the Nano's USB 5 V).

- **Gear ratio.** The nominal gearbox is about 63.68:1, giving 4075.77 half-steps per output
  turn, which is not an integer. The yaw motor on the rig measured 4096.33, a 64:1 gearbox.
  Yaw is calibrated for that reason; tilt keeps the nominal value because its calibration
  measures an angle offset, not a ratio.
- **Coils off when idle.** 300 ms after a motion both motors are switched off. The gearbox's
  friction (listed at 60–120 mN·m) holds the cradle, which needs about 40 mN·m at 90°, and no
  heat reaches the specimen. With the coils off a rotor can settle by half a motor step (about
  0.09° at the output), so before the first step the firmware energises the coil pattern of
  the held position and waits 10 ms, pulling the rotor back.
- **Backlash.** Every arrival ends turning the same way, with a 3° take-up: tilt arrives
  from above, yaw counter-clockwise. During a scan yaw only ever turns forwards, and it is
  homed again at the start of each scan, so its count never runs out.

### Homing the module

Tilt homes on a roller microswitch at about +97°, beyond the +90° working limit and away from
the lens, with the rail's sequence. The probe's contact must lie where the seek tripped the
switch (within half the clearance); an earlier contact is noise or a moved switch, and homing
fails rather than setting zero in the wrong place.

Yaw homes on a KY-024 linear hall board and a 5.7 mm magnet in the head. The firmware samples
the analogue output at every half-step of a 1.25-turn sweep, averages it in bins of 8, takes
the most common value as the baseline, and uses the deviation-weighted centroid of the peak
above half height. That repeats far better than the board's own comparator threshold, and
either pole of the magnet works.

### Centring

An insect on a pin never sits on the pin's axis, so when the head turns it travels a circle.
Movement along the lens axis only changes focus; movement across the image pushes it out of a
5.5 × 3.65 mm field. Published rotating-specimen rigs solve this the same way: centre the
specimen once where the rotation axes cross, then rotate freely.

The centring plate moves by two M3 screws at 90°, 0.5 mm per turn, against a spring. The app
measures the offset:

- At yaws 0°, 90°, 180° and 270° it focuses, then finds the insect across the image as the
  detail-weighted centre of the sharpest frame. At yaw θ an offset (x, y) shows sideways as
  x·sin θ + y·cos θ (plus where the yaw axis appears in the image) and in depth as
  x·cos θ − y·sin θ. A least-squares fit of the sideways channel alone gives the offset to
  a few micrometres.
- The rail positions of best focus follow the depth channel. They are fitted independently as
  a cross-check, and the fit learns which way the rail moves relative to the camera.
- The advice is in eighths of a turn, and the app turns the head so the named screw faces the
  person turning it (45° beside the objective by default). Each round compares how the plate actually
  moved with the last advice; a screw that moved it the wrong way has its direction flipped
  and stored. A mirrored camera view, a reversed motor or a different mounting can therefore
  not keep the advice wrong.
- Centred means within 0.1 mm of the axis, usually after two rounds.
- The height above the tilt axis comes from focus at +20° and −20°: a point at height h moves
  by h·sin t along the lens axis.

### Levelling tilt

The tilt switch's angle against true level is measured once, with a straight needle upright
in the holder. At +10° and −10° the app sweeps focus and finds where the needle's top and
bottom are sharp; the rise between them is k·sin(true tilt). If the true tilt is the
commanded one plus e, then tan e = tan 10° · (rise₊ + rise₋)/(rise₊ − rise₋), whatever k is.
A needle leaning in the head adds equal and opposite rises at yaws 180° apart, so each tilt is
measured at 0° and 180° and averaged. Until this has been done, tilt stops at −20° instead of
−33°.

### Lens clearance

The 4× objective has a 12 mm working distance, so the belly side of the tilt range is set by
the lens. A CAD sweep of every moving part against the objective plus 2 mm (tilt × yaw every
45°) gives −33° on the belly side with 1.1 mm to spare; the back side is free to +100°. The
software limits are −33° to +90°, enforced by both the host and the module's firmware.

### Power on the Pi

During the first module tests the Pi 3B+ reported under-voltage (`throttled=0xd0008`). The
A6400 charges its battery from USB, and that load dropped the camera and once the module's
serial link. The fix is to set the camera's USB Power Supply to Off and use a 2.5 A supply
for the Pi. The app logs a warning whenever the Pi goes under-voltage.

### Storage during scans

A full scan can run to thousands of shots. Keeping every 1600 px frame would take several
gigabytes on the Pi's card, so a scan keeps each pose's preview and depth map and every
tenth frame (configurable). Full-size files stay on the camera's card, and the scan's record
names them per pose.
