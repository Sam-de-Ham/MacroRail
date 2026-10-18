# Rail: print and assembly

The six STL files in `stl/` make up the rail:

1. `01_motor_end_block.stl`
2. `02_far_end_block.stl`
3. `03_carriage.stl`
4. `04_floating_nut_carrier.stl`
5. `05_sample_platform.stl`
6. `06_endstop_trigger.stl`

The STLs retain their Fusion assembly coordinates. In the slicer, use **drop to build plate** and **center/arrange** on every part before slicing.

## Prototype Settings

- Material: PLA
- Nozzle: 0.4 mm
- Layer height: 0.2 mm
- Structural walls: at least 4
- Top/bottom layers: at least 5
- End blocks: 40–60% infill
- Carriage and nut carrier: 40–60% infill
- Platform and trigger: 30–50% infill
- Slicer-generated supports: normally **off** for all six parts when using the orientations below

## Recommended Print Orientation

- Motor-end block: broad mounting foot on the bed.
- Far-end block: broad mounting foot on the bed.
- Carriage: largest flat face on the bed.
- Sample platform: largest flat face on the bed.
- Endstop trigger: broad attachment pad on the bed or rotate for the cleanest horizontal M4 pilot hole.
- Floating nut carrier: rotate it upside down so the broad 30 × 40 mm flange face is on the bed and the vertical nut plate rises from it.

Both end blocks include narrow 0.8 mm sacrificial support fins under the two horizontal rod bosses. Print these fins as part of the model, then snap or trim them away after printing. They prevent the round bosses and their short ledges from beginning in mid-air without requiring slicer-generated support. The wall-relief openings use short, printable bridges; do not enable support inside them unless a test print shows that the specific printer cannot bridge them cleanly.

Print small fit coupons or the smallest relevant part first before committing to both end blocks.

## Provisional Hardware

- NEMA 17 motor: 4 × M3 screws, approximately M3×14–16 depending on washer and safe motor engagement.
- Four SC8UU bearing blocks: up to 16 × M4 screws, approximately M4×10–12.
- T8 brass nut: reuse its four existing M3 screws where practical.
- Nut carrier to carriage: 4 × M4 bolts, washers, and nuts, approximately M4×16.
- Sample platform to carriage: 4 × M4 bolts, washers, and nuts, approximately M4×16.
- Trigger to carriage: 2 × M3 bolts, washers, and nuts, approximately M3×16.
- Rod retention: 4 × M4 screws; tap/form threads in the 3.3 mm printed pilot holes.
- Endstop: 2 × M3-class screws into the integrated motor-end mounting tab.
- End blocks to base: M5 bolts/screws with large washers.

Verify actual screw lengths against the printed parts before tightening. NEMA motor screws must not bottom out against the windings.

## Assembly Order

1. Deburr holes and remove support material.
2. Test each guide rod in both end blocks without forcing it.
3. Tap or thread-form the four M4 rod-retention pilot holes.
4. Bolt all four SC8UU blocks under the carriage, but do not overtighten initially.
5. Slide the carriage and bearing blocks onto the two rods.
6. Install the motor-end block and loosely position the far-end block.
7. Align the rods until the carriage slides freely by hand.
8. Mount the motor and confirm Allen-key access to both coupler set screws.
9. Insert the TR8×8 lead screw into the coupler.
10. Attach the T8 nut to the floating nut carrier.
11. Attach the carrier loosely under the carriage using its adjustment slots.
12. Run the carriage through its travel by hand and let the nut carrier find its natural position.
13. Tighten the nut carrier without pulling the carriage sideways.
14. Mount the sample platform.
15. Screw the endstop directly to the integrated motor-end tab, then mount the trigger.
16. Adjust the trigger so the roller operates before any carriage component reaches the motor-end block.
17. Bolt both end blocks to a heavy, flat base; tighten the far end last.

## Acceptance Checks

- Carriage slides end-to-end smoothly with the screw disconnected.
- No bearing block feels rough or binds on either rod.
- Lead screw rotates without visibly pushing the carriage sideways.
- Coupler set screws remain accessible.
- Endstop triggers reliably and has mechanical overtravel margin.
- At least 15 mm clearance remains at the configured far software limit.
- Sample platform is rigid and does not rock.

A fuller illustrated guide is in `assembly-guide.pdf`. Its electronics section predates the switch from the Anet A8 board to the Arduino Nano + TMC2209.
