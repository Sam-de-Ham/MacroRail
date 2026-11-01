# Rail: print and assembly

The rail is six printed parts on two 8 mm rods, four SC8UU bearing blocks and a Tr8×8 lead
screw driven by a NEMA 17. The STLs are in `stl/`:

1. `01_motor_end_block.stl`
2. `02_far_end_block.stl`
3. `03_carriage.stl`
4. `04_floating_nut_carrier.stl`
5. `05_sample_platform.stl`
6. `06_endstop_trigger.stl`

The sample platform is optional: with the [3D scan module](../scan-module/README.md) fitted,
the module bolts to the same four carriage holes instead.

The STLs keep their Fusion assembly coordinates. In the slicer, use *drop to build plate* and
*center/arrange* on every part before slicing.

## Print settings

| Setting | Value |
|---|---|
| Material | PLA |
| Nozzle / layer height | 0.4 mm / 0.2 mm |
| Walls | at least 4 |
| Top and bottom layers | at least 5 |
| Infill | End blocks, carriage and nut carrier 40–60 %; platform and trigger 30–50 % |
| Supports | Off for all six parts in the orientations below |

## Orientation

| Part | On the bed |
|---|---|
| Motor-end block, far-end block | The broad mounting foot |
| Carriage, sample platform | The largest flat face |
| Endstop trigger | The broad attachment pad, or rotated for the cleanest horizontal M4 pilot hole |
| Floating nut carrier | Upside down: the 30 × 40 mm flange face on the bed, the nut plate rising from it |

Both end blocks have thin (0.8 mm) sacrificial fins under the two horizontal rod bosses, so
the round bosses don't start in mid-air. Print them as part of the model and snap or trim them
off afterwards. The openings in the walls use short bridges; don't add support inside them
unless a test print shows your printer can't bridge them.

Print a small part, or a slice of an end block, first to check the fits before committing to
both end blocks.

## Hardware

| Item | Fasteners |
|---|---|
| NEMA 17 motor | 4 × M3, about 14–16 mm depending on washers; they must not bottom out against the windings |
| 4 × SC8UU bearing blocks | Up to 16 × M4 × 10–12 |
| T8 brass nut | Its four M3 screws, reused where practical |
| Nut carrier to carriage | 4 × M4 × 16, washers and nuts |
| Sample platform to carriage | 4 × M4 × 16, washers and nuts |
| Trigger to carriage | 2 × M3 × 16, washers and nuts |
| Rod retention | 4 × M4, tapped or thread-formed into the 3.3 mm printed pilot holes |
| Endstop (roller microswitch) | 2 × M3-class screws into the tab on the motor-end block |
| End blocks to the base | M5 bolts or screws with large washers |

Check screw lengths against the printed parts before tightening.

## Assembly

1. Deburr the holes and remove any support material.
2. Try each guide rod in both end blocks; it should go in without force.
3. Tap or thread-form the four M4 rod-retention pilot holes.
4. Bolt the four SC8UU blocks under the carriage, not fully tight yet.
5. Slide the carriage and bearing blocks onto the two rods.
6. Fit the motor-end block and loosely position the far-end block.
7. Align the rods until the carriage slides freely by hand.
8. Mount the motor and check that both coupler set screws can be reached with a hex key.
9. Insert the Tr8×8 lead screw into the coupler.
10. Attach the T8 nut to the floating nut carrier.
11. Attach the carrier loosely under the carriage using its adjustment slots.
12. Run the carriage through its travel by hand and let the nut carrier find its position.
13. Tighten the nut carrier without pulling the carriage sideways.
14. Mount the sample platform (or the scan module).
15. Screw the endstop to the tab on the motor-end block, then mount the trigger.
16. Adjust the trigger so the roller operates before any part of the carriage reaches the
    motor-end block.
17. Bolt both end blocks to a heavy, flat base; tighten the far end last.

## Checks

- The carriage slides end to end smoothly with the screw disconnected.
- No bearing block feels rough or binds on either rod.
- The lead screw turns without visibly pushing the carriage sideways.
- The coupler set screws stay accessible.
- The endstop triggers reliably and has mechanical overtravel beyond its click.
- At least 15 mm of clearance remains at the far soft limit (`travel_mm`, 140 mm by default;
  the CAD travel is about 150 mm).
- The sample platform is rigid and doesn't rock.

The illustrated [build guide](../../docs/guides/MacroRail-build-guide.pdf) covers the same
steps with pictures, and the electronics (Arduino Nano and TMC2209) wire by wire; the compact
pin reference is [`docs/wiring.md`](../../docs/wiring.md).
