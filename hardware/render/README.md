# Product renders

The renders in `docs/images/` (rail, module, exploded views, social preview) and the step
views in `docs/guides/img/rail/` and `docs/guides/img/module/` come from these scripts.

| File | Does |
|---|---|
| `render.py` | Builds the scene in Blender and renders every shot with Cycles (transparent background, the floor shadow in alpha). |
| `shots.py` | The shot list: which parts show, how far each part moves in an exploded view, view direction, size. |
| `finish.py` | Puts each raw render on the light-grey studio background, saves palette PNGs into the repository, and builds `social-preview.png` (1280 × 640, with title). |

## What the scene is made of

- **Rail printed parts:** `hardware/rail/stl/*.stl`, already in assembly coordinates (X along
  the rail from the motor end, Y across, Z up from the base; rods and screw at Z 30).
- **Rail bought parts:** primitives in `render.py` (`build_rail`), sized from the CAD record:
  2 × Ø8 × 380 rods at Y ±40, Tr8×8 lead screw (345 long, from 24.4 mm in front of the motor
  face), NEMA 17 (42 × 42 × 37) on the motor-end wall, a 25 mm coupler, four SC8UU
  (30 × 34 × 22) at X 130 / 210, the T8 nut on the floating carrier, the roller microswitch on
  the motor-end tab, the M4 trigger screw and the visible screw heads.
- **Scan module:** every body of the Fusion model built by `hardware/scan-module/fusion/` (except the test
  pieces, the height gauge, the lens keep-out, the objective and `REF Carriage`) as STL in
  model coordinates, one folder per pose. These meshes are not in the repository. Export them
  from Fusion with a short script like `hardware/scan-module/fusion/export_stl.py`, looping
  over `root.bRepBodies` and writing `<body name with _ for spaces>.stl`:

  | Folder | Parameters |
  |---|---|
  | `rest/` | `explode` 0, `pose_tilt` 0, `pose_yaw` 0 |
  | `exploded/` | `explode` 1 |
  | `tilted/` | `pose_tilt` 50 deg, `pose_yaw` 35 deg |
  | `home/` | `pose_tilt` 90 deg (the flag bolt at the endstop roller) |

  Set the parameters back to 0 afterwards and don't save the document.
  `render.py` places the module on the rail carriage: module X (towards the camera) is rail
  −X, because the camera looks along the rail from the motor end; the base bolts to the
  carriage's platform holes, so module (0, 0, 0) is rail (170, 0, 142).

## Rerun

```bash
blender -b -P hardware/render/render.py -- <module_meshes> <raw_dir> [shot ...]
python hardware/render/finish.py <raw_dir>
```

- Blender 5.2 (Cycles; OptiX or CUDA if there is an NVIDIA GPU, else CPU). A full run of all
  shots takes about 30 minutes on a recent laptop GPU.
- A shot is named by its output path or file stem, e.g. `rail` or `docs/images/module.png`.
- `PREVIEW=1` renders at 40 % with few samples, for checking framing.
- `finish.py` needs Python with Pillow and numpy. It writes into the repository (or into the
  folder given as a second argument).

## Assumptions

- The rail's original CAD document isn't available, so the bought parts are placed from the
  printed parts' holes: the motor face on the motor-end wall at X 0, the switch on the inner
  face of the motor-end tab (holes at X 30 and 39.4), its roller towards the carriage, and
  the trigger screw in the trigger's horizontal pilot.
- No base board is shown; the end blocks stand on the floor.
