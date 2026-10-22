# 3D scanning

The plan for the next major version: a full 3D scan of a pinned insect, driven by the
existing focus rail. The v1 module design below was agreed with the user on 2026-10-21.
Nothing is built yet; the next step is CAD.

- Measurements and derived numbers: [`hardware/scan-module/MEASUREMENTS.md`](../hardware/scan-module/MEASUREMENTS.md)
- Photos: [`reference-images/`](../reference-images/)
- Concept sketches and a lens-checked 3D mock-up (private page):
  https://claude.ai/artifact/JzWYc29WNLCKHEQN3GSxCa
- Research study (private page): https://claude.ai/artifact/Rirv3GTEdBBLdavVmZ82GV

## Ground rule: 2D stays exactly as it is (user, 2026-10-21)

The rail must always work for normal focus stacking, exactly as it does today.

- **Branch:** all 3D work lives on `3d-scanning`. `main` stays the working 2D version.
  Merge only when the user agrees.
- **Mode switch:** the app gets a 2D/3D switch. 2D mode is today's app, unchanged.
  3D mode reuses the same UI patterns and components for the 3D workflow.
- **No 2D differences unless agreed.** Anything that shows in 2D mode needs the user's
  yes first: UI, behaviour, defaults, settings, stack records, rail firmware behaviour.
  If a 2D change looks worth it, propose it ("what about…?") and wait.
- **Shared code:** refactoring shared code is fine only if 2D behaviour stays identical,
  the existing tests still pass unchanged, and the refactor is mentioned to the user.
- **Firmware:** the new axes are purely additive. The firmware must run the rail
  normally with no module plugged in, and rail commands keep their current meaning.
- **Hardware:** the module bolts onto the carriage. Without it, the rail is today's rail.

## Working together

The user and the agent do the whole build together, step by step: plan, measure, model
in CAD, print, program, set up, calibrate. Measurements come from the user, never from
guesses. The rail's own geometry comes from the STLs in `hardware/rail/stl/`.

## The problem, in short

An insect on a pin never sits exactly on the pin's axis, so when the pin turns, the insect
travels a circle. Movement along the lens axis only changes focus, and a focus scan at
every pose absorbs it. Sideways and vertical movement pushes it out of a 5.5 × 3.65 mm
frame. Every published rotating-specimen rig (DISC3D, scAnt, the CSIRO prototype) solves
this the same way: centre the insect once, where the rotation axes cross, then rotate
freely. Photogrammetry doesn't need the insect centred, only whole and sharp in every view.

## v1 design (agreed 2026-10-21)

The insect's centre sits where the yaw and tilt axes cross. Both axes are motorised, and
centring is done by hand once per specimen.

```
camera ──▶ lens axis ──▶ insect (on both axes)
                          │ pin, 19 mm exposed
                          ├ specimen holder: nose + pin clamp (one M3 screw)
                          │   on the centring plate, one part; ring + X/Y screws
                          ├ yaw 28BYJ-48 (head straight on its shaft)
                          └ cradle floor
cradle arms ── tilt axis ── uprights: 608 on one side, tilt 28BYJ-48 on the other
base plate ── 4 × M3 ── rail carriage (focus axis, unchanged)
```

| Part | Design | Why |
|---|---|---|
| **Mount** | Base plate on the carriage's four free holes (60 × 20, Ø4.5), M3 bolts with washers and nuts. Pockets for the bearing-block screw heads (1.3 tall) where the plate is wider than ±24. | The sample platform isn't fitted, so these holes are free. The app measures where the axes are, so the M3-in-Ø4.5 slop doesn't matter. |
| **Fork** | One printed body: base plate, both uprights and their ribs. The bearing seat and the motor recess come out coaxial by construction; as horizontal holes, they are checked with test pieces first. | Supported on both sides: stiff, and the axis is set by two fixed points. The camera looks between the uprights, and there's room to light from the front and back. |
| **Tilt axis** | A U-cradle between the uprights. One side: a stub axle in the 608, in one upright. Other side: the **tilt 28BYJ-48, direct drive**. It's screwed to the outside of the other upright, with its Ø9 boss in a recess to centre it, and a D-hub on its shaft carries the cradle. | Simplest drive (user's choice). See "Torque" below. |
| **Tilt home** | A roller microswitch on a printed bracket on the +Y upright, pressed by a flag bolt on the cradle arm. It clicks at +97°, past the +90° working limit. | Homing moves away from the lens, never towards it. |
| **Tilt range** | −33° (belly towards the lens) to +90° (top view), confirmed by the CAD sweep. | The lens limits the belly side (see "Lens clearance"). |
| **Yaw axis** | The **yaw 28BYJ-48** screwed under the cradle floor. The head mounts **straight on its shaft** through a D-hub, with no bearing (user's choice). | The yaw only carries the head (about 25 g). Shaft play causes a small, repeatable wobble that stays well inside the frame; the centring wizard shows how big it is. A 608 turntable can be added later if it matters. |
| **Yaw home** | KY-024 linear hall board on the cradle floor, one Ø5.7 magnet in the head's underside. Homing reads the analog output and takes the field peak, the magnet's centre. | The peak repeats better than the board's on/off threshold. |
| **Yaw range** | Unlimited in v1. | Nothing electrical turns with the head. |
| **Centring (X/Y)** | One printed plate (Ø26 × 6) in a printed Ø43 ring on the yaw hub. Two M3 screws at 90° turn in captive nuts in the ring and push the plate; a pen spring at 225° pushes straight on the rim. The plate's rim has a 4 mm-wide V that holds the screw ends, so the plate can't lift. Plain button-head screws turned with a 2 mm hex key (no knobs). ±2.5 mm. | One layer and three parts. Metal screw tips on a printed plate. 0.5 mm per turn: a quarter turn is 0.125 mm. |
| **Specimen holder** | One printed part: the centring plate with the clamp column and nose on top; one M3 screw through a captive nut pinches the pin. It stays in the head; specimens change by swapping the pin. | Explained under "Why no puck". |
| **Pin clamp** | A V-groove channel running through a 45° tapered nose (Ø5 tip) and the clamp body, about 18 long. A printed pad on an M3 screw presses the pin; the screw sits at the bottom of the carrier. | Pins 00 to 1 (0.30–0.40) all sit on the same line. The tapered nose and low screw keep everything near the insect out of the lens's way. |
| **Height (Z)** | Slide the pin against the printed stepped gauge (17 to 21 mm above the nose tip), then clamp it with the clamp screw. The wizard measures any height error, and you re-set the pin with the gauge. A fine Z screw was dropped in CAD: there was no room for it inside the lens clearance cone. | Puts the insect on the tilt axis, for glued-tip and pinned-through specimens alike. Pins stay full length (39.4), no cutting needed. |
| **Accessories** | Height gauge; a calibration puck with a straight needle (for measuring where the axes appear in the image). | Calibration happens once per machine; it's stored in `config.toml`. |
| **Electronics** | 2 × ULN2003 from the user's 5 V supply, ground shared with the Nano. Pins below. | The Nano's USB 5 V shouldn't carry two motors (about 240 mA each while moving). |
| **Lighting** | Deferred. Felt background, 2–3 lights and a bounce, as the user does now. | No dome needed. |

### Why no puck (user decision, 2026-10-21)

The first design had a removable puck: three bumps in three V-grooves on the centring
plate, held by magnets, so a specimen could be lifted off and put back without
re-centring. The user dropped it for v1: the holder is rarely taken off, because changing
specimens means swapping the pin, not the holder. So the clamp is printed straight onto
the centring plate as one part, the **specimen holder**. No magnets, domes or grooves; the
centring works as before. The 0.5 mm seat gap went into the holder's neck (6.5 mm), so
every height below the insect is unchanged.

### Torque (direct-drive tilt)

- **Load:** the cradle hangs below the axis like a pendulum. With the head straight on the
  yaw shaft it pulls about 40 mN·m at 90° and about 35 at 60°.
- **Holding: fine, even unpowered.** The 28BYJ-48's gearbox friction torque is listed at
  60–120 mN·m, so the user's intuition is right. The coils switch off between moves, so
  no heat reaches the insect.
- **Lifting: borderline near 90°.** Its pull-in torque is listed at about 34 mN·m, and
  slow stepping gives a bit more.
  - So the cradle arms extend above the axis with **counterweight pockets**: room for a
    stack of coins or an 8 mm rod offcut.
  - The first test runs them empty. If the tilt skips steps near 90°, the pockets get
    weight; homing on the endstop would show any lost steps.
- **Shaft offset:** yes, both motors' shafts are 8 off the body centre (O1). The tilt
  motor's shaft is the axis, so its body sits 8 off it. Its shaft and the 608 share the
  cradle's weight, so the motor shaft only carries about half of it.
- **Alignment:** the motor shaft and the 608 must be coaxial, or the cradle binds. The
  motor boss's recess and the bolted uprights fix that. The motor's own shaft play moves
  one end of the axis a little; the insect, halfway between, moves half as much.

### Lens clearance

The 4× objective has a 12 mm working distance and a Ø21.9 sleeve, then a Ø23.4 knurled ring,
then a Ø29.8 adapter.

- **Keep-out zone:** those diameters plus 2 mm all round (in `MEASUREMENTS.md`).
- **Rule:** to tilt the belly side 45° towards the lens, a part at depth d below the
  insect and reach w from the pin needs d − w ≥ 18.
- **Hence:** 19 mm of exposed pin, the 45° tapered nose, the clamp screw low on the
  carrier, and the small centring ring.
- **The mock-up's check:** −36° on the belly side; the dorsal side is free to +90°.
- **CAD repeats this check** on the real geometry.

### Key dimensions (CAD)

- **Under the insect:** pin 19, nose 10, clamp column 8, holder neck 6.5, plate 6, ring floor
  2, bell hub 7, gap 1, floor 4, yaw motor 19. The motor's back is 82.5 below the insect.
- **Tilt axis:** 95 above the carriage top, so the swinging cradle clears the base. The
  camera's tripod sets the lens to that height.
- **Across the rail:** cradle arms at ±33 to ±39, uprights at ±40 to ±46. About 128 wide
  including the tilt motor.

### Nano pins (2D pins untouched)

- **Used today:** D2 home, D3 STEP, D4 DIR, D5 EN, D7/D8 driver UART, D9 reserved (relay).
- **Yaw:** ULN2003 IN1–IN4 on D6, D10, D11 and D12; KY-024 analog output on A0.
- **Tilt:** ULN2003 IN1–IN4 on D13, A1, A2 and A3. D13 drives the on-board LED too, which
  is harmless. The endstop goes on A4.
- **Left:** A5, plus A6 and A7 (analog only).

### One scan

1. **Mount** the pinned insect in the holder's nose, set the pin height with the gauge,
   and tighten the clamp screw (you, about 1 min).
2. **Centre** with the wizard. The app turns the insect to 4 yaw angles, finds it in the
   live view (sharp tiles) and with a focus scan, fits a circle, and says how far to turn
   each screw, then turns the head so that screw faces you. Repeat until under about 0.1 mm (you and the app, about 2 min). It also
   checks height at two tilts; you re-set the pin with the gauge if needed.
3. **Scan, automatically:** rings of poses at several tilts (for example −30°, 0°, 30°,
   60°, then a top view), yaw in 10° steps. At each pose: focus scan, then stack.
4. **Export** one stacked image per pose for COLMAP or Meshroom.

The wizard's maths: at yaw θ, an offset (x, y) shows sideways as x·cos θ − y·sin θ and
in depth as x·sin θ + y·cos θ. With equally spaced angles the least-squares fit is a
plain Fourier sum. The image gives the sideways curve precisely; the focus scan's depth
curve is a cross-check.

Backlash: every pose is approached turning the same way, the same trick as the rail's
take-up. Rings run one way; going back unwinds past the start and comes forward again.
Tilt backlash doesn't move the insect, because it sits on the tilt axis.

## CAD (built 2026-10-21)

The full model is in Fusion 360 (document *3d scanner macro v1.1*, project Everything,
folder Useful). [`hardware/scan-module/README.md`](../hardware/scan-module/README.md) covers
the model's structure, how to rebuild it from the stage scripts, what was verified, the
print guide, the hardware list and the test-piece checklist.

Changes from the agreed concept, with reasons:
- **Fork as one body:** coaxial bearing and motor seats with no assembly error.
- **Wider cradle:** arms at ±33 (planned ±30), so the centring screws clear them.
- **No knobs:** the centring and clamp screws are turned with a 2 mm hex key; yaw brings each
  screw round to the user.
- **Wider uprights:** 44.2 mm (motor tab spacing + counterbore + 3), so the tilt motor's ear
  bolts land inside the upright.
- **Thin motor-side upright (after test round 1):** 4 mm instead of 6, so the short
  28BYJ-48 shaft reaches 6.2 mm into the cradle hub. The tilt motor goes on after the cradle
  is in, its shaft pushed in from outside.
- **Simpler head (after test round 1):** no pin pad and no spring plunger. One M3 screw on a
  straight line clamps the pin; the spring pushes straight on the holder's rim.
- **Thicker plate:** 6 mm with a 4 mm rim V. A flat M3 end can't enter a narrow V, so the
  wider V captures the screws and the plate can't lift.
- **Bell hub:** the head prints hub-down with no supports. A snap-off fin carries the
  spring housing.
- **Flat hall sensor:** the hall sensor lies flat in a floor pocket, 0.8 mm under an axial
  magnet in the bell's underside.
- **Fine Z screw dropped:** a stepped height gauge replaces it.
- **Tilt axis at 95** (planned 87), and a belly limit of −33° (planned −36°).

- **Tilt home:** a printed bracket, bolted to the outside of the +Y upright with two M3
  (nuts in pockets inside), holds a roller microswitch just past the upright's +X edge. It is
  fixed with two small wood screws plus glue (the user's choice; the switch holes are too
  small for M3). An M3 × 17.5 flag bolt through the +Y arm meets the roller at +90° and
  clicks it at `home_t` = 97°, homing away from the lens.
- **Specimen holder, no puck:** the plate and the clamp are one part (see "Why no puck").

Assembly and use: [`hardware/scan-module/guide/MacroRail-scan-module-guide.pdf`](../hardware/scan-module/guide/MacroRail-scan-module-guide.pdf).
STLs: `hardware/scan-module/exports/test-pieces/` and `exports/final/`.

Next: print the test pieces (including the endstop bracket and specimen holder) and check
them; then print the final parts.

Print fits from the lens-mount project (Prusa i3 MK3, validated in PLA): M3 clearance 3.4;
M3 nut pocket 5.7 across flats × 2.6 deep; friction bore +0.6 on diameter; sliding fit 0.4
total clearance. No threads in plastic; counterbores, not countersinks.

## Later

- **v2, hands-off centring:** 28BYJ-48s on the X/Y screws (a hex-bit coupler on
  the button heads, plus a bracket). That needs 8 more pins, so it means moving to an
  **Arduino Mega 2560**: the same AVR toolchain, and hardware UARTs, which also remove the
  half-duplex SoftwareSerial workaround. Not the Pi's GPIO: motion stays in the firmware.
- A 608 turntable under the yaw head, if the shaft wobble turns out to matter.
- Tracking the insect between poses from the sharp tiles.
- Tiling, for insects bigger than the frame.
- **Cross-polarised lighting:** polariser film on each light, and an analyser behind the
  objective in the adapter tube. A diffuser goes *before* the film, never after it,
  because diffusers scramble polarisation.

## Scan time (rough)

- **Full resolution:** about 120 poses at a 32.5 µm step and about 2.5 mm visible depth
  is about 78 shots per pose. That's about 9,400 shots, roughly 6–7 h at 2.4 s per shot.
- **Live-view draft:** sweep the rail slowly while grabbing live-view frames
  (1024 × 680). It takes under an hour with no shutter wear, which is good for checking
  coverage first.

## Software (sketch, against the current layout)

- `motion/`: a rotary `Axis` for yaw and for tilt; the protocol gains an axis name. Rail
  commands keep their meaning.
- `scan/` (new): scan plan (rings × yaw, tilt limits), the centring fit, and a runner
  doing rotate → focus scan → stack per pose. `focus/` already reruns per angle.
- `review/`: a folder per pose, a pose table, export for COLMAP or Meshroom.
- Moving the sample changes magnification slightly during a stack. DISC3D corrects this
  with calibrated scaling, which matters for true-scale models.

## Setup facts (user, 2026-10-21)

- **Optics:** AmScope Plan 4/0.10 (160 mm tube, 0.17 cover glass) on a long printed
  adapter (printables 143754).
  - At 4× it gives 4.27×, a 5.5 × 3.65 mm field, 12 mm working distance with the sleeve on,
    64 µm depth of field (step 32.5 µm).
  - A 2× setup also exists, with more working distance.
- **Camera:** on a tripod on the floor; the rail on the table. The camera looks along the
  rail from the motor end. The focus point is kept near mid-travel, so the end blocks
  never matter.
- **Specimens:** aphids to grasshoppers, glued on the pin tip or pinned through. Bigger
  insects get bigger pins. At 4×, anything over about 5 mm needs tiling or the 2× setup.
- **Parts:** 4 × 28BYJ-48 and ULN2003, 1 × 608, 20 magnets, pen springs, 2 printer
  endstops, 1 × KY-024, a 5 V supply, a 30 V / 10 A bench supply, plenty of M3.

## Open items

- Torque near 90°: check on the first printed cradle; add counterweight if steps skip.
- Tilt home click angle: check on the rig that the switch clicks near +97° (`home_t`).
- Optional: screenshots of the user's old rotate-and-tilt build, for reference.
