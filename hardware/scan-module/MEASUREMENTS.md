# Scan module: measurements

Rounds 1 to 3: 2026-10-21 (round 3 is the tilt home microswitch). All values in mm and measured by the user with calipers, unless marked
otherwise. **Never guess a dimension: ask.** Photos are in `reference-images/` at the repo
root.

| Diagram | Shows |
|---|---|
| [`diagrams/01-objective.svg`](diagrams/01-objective.svg) | Objective front, working distance, field of view |
| [`diagrams/02-carriage-holes.svg`](diagrams/02-carriage-holes.svg) | Carriage top: free mounting holes and screw heads |
| [`diagrams/03-28byj48.svg`](diagrams/03-28byj48.svg) | 28BYJ-48 yaw motor |

## Objective (AmScope Plan 4/0.10, 160/0.17, sleeve on)

| Label | Meaning | Value |
|---|---|---|
| A1 | Working distance, sleeve front to subject when sharp | 12.0 at 4× (more at 2×) |
| D1 | Sleeve (front part) diameter | 21.9 |
| L1 | Sleeve front to the knurled ring | 18.2 |
| D2 | Knurled ring diameter | 23.4 |
| L2 | Sleeve front to the adapter tube's end | 30.5 |
| D3 | Adapter tube diameter at that end | 29.8 |
| F1 | Field of view, long side | 5.5 at 4× (more at 2×) |

The user also uses a 2× setup with a longer working distance. The 4× numbers are the
worst case for clearance.

## Carriage (the sample platform isn't fitted)

| Label | Meaning | Value |
|---|---|---|
| C1 | Free M4 holes, centre to centre along the rail | 59.5 (CAD: 60.0) |
| C2 | Free M4 holes, centre to centre across | 20.5 (CAD: 20.0) |
| C3 | Bearing-block screw head height above the carriage top | 1.3 |

C1 and C2 are within caliper error of the CAD values (hole edges measured), so the
design uses 60 × 20.

## 28BYJ-48 (4 on hand) and ULN2003 boards (4 on hand)

| Label | Meaning | Value |
|---|---|---|
| D3 | Body diameter | 28 |
| H3 | Body height, under the tabs to the back | 19 |
| S2 | Tab holes, centre to centre | 35 |
| d1 | Tab hole diameter | 4.2 |
| T1 | Tab thickness | 0.7 |
| O1 | Shaft centre to body centre | 8 |
| D4 | Shaft diameter / across the flats | 5 / 3 |
| L4 | Shaft length above the boss / length of the flats | 9.7 / 7.8 (swapped on the first sheet; confirmed) |
| D5 / H4 | Boss diameter / height | 9 / 1.5 |
| W2 | Blue wire box width | 14.4 (17.2 at its widest part) |
| P2 | Wire box protrusion past the body | 3 |
| ULN2003 | Board W × L / hole spacing / hole diameter | 34.6 × 31.7 / 29.6 × 27.0 / 2.6 |

The board runs on 5–12 V and has IN1–IN4 headers and a 5-pin motor socket (photo).

## Pins

| Label | Meaning | Value |
|---|---|---|
| d5, d6 | Insect pins, glued-tip and pinned-through (same pins) | Sizes 00, 0 and 1 on hand (nominal 0.30, 0.35, 0.40); the caliper read 0.1. Bigger pins for bigger insects. |
| L8 | Pin length | 39.4 |

## Parts on hand

| Part | Value |
|---|---|
| Bearings | 1 × 21.8 / 7.9 / 7 (a 608, from a fidget spinner). More can be found if needed. |
| Magnets | 20 × Ø5.7 × 1.8 |
| Compression springs | Pen springs: OD 4.6 / free 19 / wire 0.5 (standard, several). 4 × 3D-printer bed springs: OD 7.8 / free 23.8 / wire 0.8 (stiff). Small ones: OD 6.2 / 7.7 / 0.3 and OD 5.8 / 10 / 0.3. |
| Hall sensor | KY-024 linear hall board (49E-type sensor on leads, comparator with pot, D0 and A0 outputs, one mounting hole) |
| Steel balls | None |
| Polariser film | Plastic sheets that can be cut |
| Bench supply | 30 V / 10 A |
| M3 bolts | From the lens-mount project: button head, head Ø5.2 × 1.9; lengths 11.8, 17.5 (under head, confirmed there), 19.4, 27.7 (unclear whether under-head). Counts unknown. |
| M3 nuts | From the lens-mount project: plain, 5.2 across flats (standard is 5.5) × 2.2. A 5.7 AF × 2.6 deep pocket fit them. |
| M4 bolts and nuts | Not used: **M3 for everything** (user, plenty of M3 bolts and nuts). M3 with washers through the carriage's Ø4.5 holes. |

## Tilt home microswitch (round 3, 2026-10-21)

Roller-lever microswitch. Seen from the hole side, pivot end on the left, pins down.

| Label | Meaning | Value |
|---|---|---|
| — | Body length × height × thickness | 20 × 10 × 5.8 |
| S1 | Hole spacing, centre to centre | 9 |
| L1 | Pivot end to first hole centre | 4.7 |
| H1 | Pin edge to hole centres | 2.7 |
| d1 | Hole diameter | 2.5 (too small for M3) |
| L2 | Pivot end to roller centre, along the body | 16.4 |
| P1 | Lever edge to roller top, free | 10.8 (6.2 to the metal under the roller) |
| P2 | Lever edge to roller top, at the click | 7.1 |
| P3 | Pin length below the body | 3.5 |
| — | Roller type | Roller |
| — | Wood screws (to hold it) | Ø1.8–1.9, 11.5 overall, head Ø3.2 × 1 |

The user screws it on with the wood screws and also glues it (doesn't trust the screws alone).

Lighting (COB LEDs, panels, heatsinks): deferred by the user.

## Derived values (computed, not measured)

Planning-stage numbers. Where the design moved on, the final value is the Fusion parameter
named in brackets (`fusion/stage_01_params.py`).

- **Magnification** at 4×: 23.5 / 5.5 = **4.27×**. Field 5.5 × 3.65 mm; 0.92 µm per
  full-resolution pixel.
- **Depth of field** (step helper formula, NA 0.10): 0.55/NA² + 3.92/(M·NA) = **64 µm**;
  suggested step **32.5 µm** (on the 2.5 µm grid).
- **Lens keep-out zone** (the insect at the origin, x towards the camera along the lens axis):
  - x 12.0 to 30.2: radius 11.0 (sleeve), then 11.7 from x 30.2 (knurled ring);
  - from x 42.5: radius 14.9 (adapter tube).
  - Add at least 2 of clearance. Anything nearer the lens axis than that must stay at
    x < 10 when the module tilts or turns.
- **Module footprint**: the base is wider than ±24 across the rail, so it has pockets for the
  bearing-block screw heads. Final: M3 bolts (user: M3 for everything) in Ø3.4 holes on 60 × 20,
  with printed washers under the nuts in the carriage's Ø4.5 holes.
- **Shaft coupling**: double-D 5 / 3 shaft. Final, after the test prints: yaw head bore
  5.1 / 3.1 (`fit_D` 0.1, printed vertical, plus a set screw); tilt hub bore 5.05 / 3.05
  (`fit_Dt` 0.05, printed on its side).
- **Tilt bearing**: one 608 (21.8 / 7.9 / 7 measured). Final seat 21.8 + 0.35 (`fit_press`;
  0.25 was a little tight). The yaw head sits straight on its motor shaft, no bearing.
- **Specimen puck**: dropped (user, 2026-10-21). The clamp is printed onto the centring
  plate (the specimen holder); only one magnet is used, for yaw home.

## Still to measure / confirm

- [x] Second 608: not needed (the yaw head sits on its motor shaft).
- [x] Tilt home: roller microswitch, measured (round 3).
- [x] KY-024 board: 34.5 × 15.2, 13 thick with the potentiometer, hole centre 8.3 from the pin end.
- [ ] 2× setup: working distance and field width (optional).
- [x] L4 shaft (9.7) and flats (7.8); pin sizes; fasteners (M3 throughout); springs (round 2).
- [x] Objective front, field of view, carriage holes, 28BYJ-48, ULN2003, magnets, hall
      sensor type (round 1).
