# Scan module: measurements

The measured dimensions the scan module was designed around, in mm, taken with calipers unless
marked otherwise. If your parts differ, change the matching parameter in
`fusion/stage_01_params.py` (see [README.md](README.md)) rather than the features.

| Diagram | Shows |
|---|---|
| [`diagrams/01-objective.svg`](diagrams/01-objective.svg) | Objective front, working distance, field of view |
| [`diagrams/02-carriage-holes.svg`](diagrams/02-carriage-holes.svg) | Carriage top: free mounting holes and screw heads |
| [`diagrams/03-28byj48.svg`](diagrams/03-28byj48.svg) | 28BYJ-48 motor |

## Objective (AmScope Plan 4/0.10, 160/0.17, sleeve on)

| Label | Meaning | Value |
|---|---|---|
| A1 | Working distance, sleeve front to subject when sharp | 12.0 at 4× |
| D1 | Sleeve (front part) diameter | 21.9 |
| L1 | Sleeve front to the knurled ring | 18.2 |
| D2 | Knurled ring diameter | 23.4 |
| L2 | Sleeve front to the adapter tube's end | 30.5 |
| D3 | Adapter tube diameter at that end | 29.8 |
| F1 | Field of view, long side | 5.5 at 4× |

A 2× setup has more working distance and a wider field. The 4× numbers are the worst case for
clearance.

## Carriage (sample platform not fitted)

| Label | Meaning | Value |
|---|---|---|
| C1 | Free M4 holes, centre to centre along the rail | 59.5 (CAD: 60.0) |
| C2 | Free M4 holes, centre to centre across | 20.5 (CAD: 20.0) |
| C3 | Bearing-block screw head height above the carriage top | 1.3 |

C1 and C2 are within caliper error of the CAD values (measured over hole edges), so the module
uses 60 × 20.

## 28BYJ-48 and ULN2003

| Label | Meaning | Value |
|---|---|---|
| D3 | Body diameter | 28 |
| H3 | Body height, under the tabs to the back | 19 |
| S2 | Tab holes, centre to centre | 35 |
| d1 | Tab hole diameter | 4.2 |
| T1 | Tab thickness | 0.7 |
| O1 | Shaft centre to body centre | 8 |
| D4 | Shaft diameter / across the flats | 5 / 3 |
| L4 | Shaft length above the boss / length of the flats | 9.7 / 7.8 |
| D5 / H4 | Boss diameter / height | 9 / 1.5 |
| W2 | Wire box width | 14.4 (17.2 at its widest) |
| P2 | Wire box protrusion past the body | 3 |
| ULN2003 | Board W × L / hole spacing / hole diameter | 34.6 × 31.7 / 29.6 × 27.0 / 2.6 |

The ULN2003 board runs on 5–12 V and has IN1–IN4 headers and a 5-pin motor socket.

## KY-024 hall board

34.5 × 15.2, 13 thick including the potentiometer; mounting hole centre 8.3 from the pin end.
A 49E-type linear sensor on leads, a comparator with potentiometer, D0 and A0 outputs. Only A0
is used.

## Pins

| Label | Meaning | Value |
|---|---|---|
| d5, d6 | Insect pins, glued-tip and pinned-through | Sizes 00, 0 and 1 (nominal 0.30, 0.35, 0.40) |
| L8 | Pin length | 39.4 |

## Hardware used

| Part | Value |
|---|---|
| Bearing | 608: 21.8 / 7.9 / 7 measured |
| Magnet | Ø5.7 × 1.8 (one, for yaw home) |
| Spring | Pen spring: OD 4.6, free length 19, wire 0.5 |
| M3 bolts | Button head, head Ø5.2 × 1.9; lengths 11.8, 17.5 and 27.7 |
| M3 nuts | 5.2 across flats (standard is 5.5) × 2.2. A 5.7 AF × 2.6 deep pocket fits both sizes. |

M3 is used throughout, including through the carriage's Ø4.5 holes with printed washers.

## Tilt home microswitch

Roller-lever microswitch, seen from the hole side, pivot end on the left, pins down.

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
| — | Wood screws to hold it | Ø1.8–1.9, 11.5 overall, head Ø3.2 × 1 |

It is held by the two wood screws and glue.

## Derived values

Computed from the measurements. Where the design moved on, the final value is the Fusion
parameter named in brackets.

- **Magnification** at 4×: 23.5 / 5.5 = **4.27×**. Field 5.5 × 3.65 mm; 0.92 µm per
  full-resolution pixel (A6400).
- **Depth of field** (the app's step helper, NA 0.10): 0.55/NA² + 3.92/(M·NA) = **64 µm**;
  suggested step **32.5 µm** (on the 2.5 µm grid).
- **Lens keep-out zone** (insect at the origin, x towards the camera along the lens axis):
  - x 12.0 to 30.2: radius 11.0 (sleeve), then 11.7 from x 30.2 (knurled ring);
  - from x 42.5: radius 14.9 (adapter tube);
  - plus at least 2 of clearance. Anything nearer the lens axis than that must stay at
    x < 10 when the module tilts or turns.
- **Footprint:** the base is wider than ±24 across the rail, so it has pockets for the
  bearing-block screw heads. M3 bolts in Ø3.4 holes on 60 × 20, with printed washers under the
  nuts in the carriage's Ø4.5 holes.
- **Shaft coupling:** double-D 5 / 3 shaft. Yaw head bore 5.1 / 3.1 (`fit_D` 0.1, printed
  vertical, plus a set screw); tilt hub bore 5.05 / 3.05 (`fit_Dt` 0.05, printed on its side).
- **Tilt bearing:** seat 21.8 + 0.35 (`fit_press`). The yaw head sits on its motor shaft with
  no bearing.

Not measured: the 2× setup's working distance and field width.
