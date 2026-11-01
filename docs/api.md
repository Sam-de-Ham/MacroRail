# HTTP API

The web UI uses nothing but this API, so anything it does can be scripted. The server also
serves its own OpenAPI description: an interactive page at `/docs` and the schema at
`/openapi.json`.

## Conventions

- **Control.** Commands marked **C** need the header `X-Client-Id: <id>` of the client holding
  control (see `POST /api/control/take`), or they return `403`. Reads, `stop` and the camera
  settings refresh need no control.
- **Asynchronous commands.** Most commands check their preconditions, start a background
  operation and return `204` at once. Progress and the result arrive over the WebSocket (state
  and the activity log). Only one operation runs at a time.
- **Errors.** A refused command returns `409` with `{"detail": "<reason, written for the
  user>"}` (busy, not homed, no camera, ...). A missing stack, scan or image returns `404`.
  Invalid bodies return `422`.
- **Units.** Rail positions, jogs and steps are in microsteps (400 per mm with the standard
  rail; `state.rail.steps_per_mm`). Module angles are in degrees: tilt 0 is level and positive
  turns the specimen's back towards the camera; yaw is counter-clockwise seen from above.

## State

| Endpoint | Description |
|---|---|
| `GET /api/state?client=<id>` | The current state snapshot, once. |
| `WS /api/ws?client=<id>` | The state stream. Connecting registers the client (the first one gets control). |
| `GET /api/liveview` | Live view as MJPEG (`multipart/x-mixed-replace`), capped at `liveview_max_fps`. Paused while a stack shoots. |

The WebSocket sends JSON messages of two types. The first message is the activity log so far;
after that, a state message whenever anything changes (at most 20 per second), and new log
lines as they happen:

```json
{"type": "log", "entries": [{"time": 1761300000.0, "level": "info", "message": "Homed. ..."}]}
{"type": "state", "state": {"activity": "idle", "rail": {...}, "camera": {...}, ...}}
```

Top-level keys of `state`:

| Key | Holds |
|---|---|
| `version`, `activity` | App version; `idle`, `homing`, `moving`, `previewing`, `stacking`, `capturing`, `scanning` (focus scans and 3D measurements), `rotating` (module moves) or `scanning_3d`. |
| `rail` | `connected`, `driver_ok`, `enabled`, `homed`, `moving`, `endstop`, `position`, `firmware`, `problem`; `steps_per_mm`, `min`, `max`. |
| `module` | Scan module connection, angles (`tilt_deg`, `yaw_deg`), homed flags, switch, hall reading, tilt limits, `calibration`, `centring` (rounds, screw turns, height), `link`. |
| `scan3d` | The 3D scan plan, its poses, estimate, pre-flight checks, the running scan and unfinished scans. |
| `camera`, `live_view` | Camera connection, model, battery, settings; whether live view is available or paused. |
| `settings`, `optics`, `plan` | User settings; depth of field and suggested step; the current stack plan (shot count, estimate). |
| `scan`, `stack` | The last focus scan (range or backlash result); the running or last stack. |
| `review`, `diagnostics`, `control` | Review revision; Pi, link, driver and camera health; whether this client holds control. |

## Control and stop

| Endpoint | Description |
|---|---|
| `POST /api/control/take` | Take control for the client in `X-Client-Id`. |
| `POST /api/stop` | Stop whatever is running: a stack stops and returns to its start (also a scan pose's stack, which ends the scan), anything else decelerates and stops in place. Any client. |

## Rail

| Endpoint | | Description |
|---|---|---|
| `POST /api/rail/home` | C | Home the rail. |
| `POST /api/rail/jog` | C | `{"delta": <microsteps>}`, at most 5 mm. Allowed before homing. |
| `POST /api/rail/motors` | C | `{"enabled": true\|false}`. Turning the motor off clears homed. |
| `POST /api/points/{start\|end}` | C | Set the stack's start or end: `{"position": <microsteps>}`, or `{}` for the current position. |
| `POST /api/points/{start\|end}/go` | C | Go to that point, arriving in the stack direction. |
| `POST /api/preview` | C | Sweep between start and end until Stop. |

## Stacks

| Endpoint | | Description |
|---|---|---|
| `POST /api/stack/start` | C | Start a stack with the current settings. |
| `POST /api/stack/pause` | C | Pause after the current shot. |
| `POST /api/stack/resume` | C | Resume (retakes the slice after a camera error). |
| `PATCH /api/settings` | C | `{"motion": {...}, "stack": {...}, "optics": {...}, "scan": {...}, "camera": {...}}`, any subset. Validated as a whole. |

## Focus scans

| Endpoint | | Description |
|---|---|---|
| `POST /api/scan/range` | C | Auto range: scan around the current position for the subject's front and back. |
| `POST /api/scan/range/apply` | C | Use the found range as the stack's start and end. |
| `POST /api/scan/backlash` | C | Measure the lead-screw backlash from live view. |
| `POST /api/scan/backlash/apply` | C | Set the take-up to the suggested value. |

## Camera

| Endpoint | | Description |
|---|---|---|
| `POST /api/camera/test` | C | Take one shot. |
| `POST /api/camera/settings` | C | `{"key": "iso", "value": "400"}`. Keys and choices come from `state.camera`. |
| `POST /api/camera/settings/refresh` | | Read the camera's settings again. |

## Review

| Endpoint | | Description |
|---|---|---|
| `GET /api/stacks` | | Every 2D stack's summary, newest first (scan poses are left out). |
| `GET /api/stacks/{id}/frames/{n}` | | Frame `n` (1-based), 1600 px JPEG. |
| `GET /api/stacks/{id}/preview` | | The preview stack, JPEG. |
| `GET /api/stacks/{id}/depth?colour=<bool>` | | The depth map: 16-bit grey PNG, or the false-colour JPEG. |
| `GET /api/stacks/{id}/zip` | | Record, preview, depth maps and frames, streamed uncompressed. |
| `POST /api/stacks/{id}/preview` | C | Build the preview stack and depth map again. |
| `DELETE /api/stacks/{id}` | C | Delete the Pi's copy (the camera's card is untouched). |

## Scan module

All need the module connected. Tilt commands are refused while manual tilt is on.

| Endpoint | | Description |
|---|---|---|
| `POST /api/module/home` | C | `{"axes": ["tilt", "yaw"]}` (default both; tilt first). |
| `POST /api/module/jog` | C | `{"axis": "tilt"\|"yaw", "delta_deg": <deg>}`, at most 45° (10° for tilt before homing). |
| `POST /api/module/pose` | C | `{"tilt": <deg>, "yaw": <deg>}`, either may be omitted. Arrives from the take-up side. |
| `POST /api/module/calibrate/yaw` | C | Measure the half-steps per yaw turn (home, three turns, home). |
| `POST /api/module/calibrate/tilt` | C | Level tilt from a straight needle in focus (rail and module homed). |
| `POST /api/module/centring` | C | One centring round: four yaws, fit, screw advice. |
| `POST /api/module/height` | C | The specimen's height above the tilt axis, from focus at ±20° tilt. |
| `POST /api/module/spin` | C | Turn yaw continuously (up to 100 turns) until Stop. |
| `POST /api/module/specimen` | C | Forget the current specimen's centring rounds and height. |

## 3D scans

| Endpoint | | Description |
|---|---|---|
| `PATCH /api/scan3d/plan` | C | Any of `tilts`, `yaw_step_deg`, `keep_every`, `settle_s`, `name`, `manual_tilt`, `screw_access_deg`. Refused while a scan runs. |
| `POST /api/scan3d/start` | C | `{"test": false}` scans the plan; `{"test": true}` runs one pose at the module's current angles. Refused if a blocking pre-flight check fails. |
| `POST /api/scan3d/pause` | C | Pause (inside the current pose's stack, or before the next pose). |
| `POST /api/scan3d/resume` | C | Resume. With manual tilt, also confirms the tilt was set by hand. |
| `GET /api/scans` | | Every scan's summary, newest first. |
| `GET /api/scans/{id}` | | The scan's record (`scan.json`): plan, poses, results. |
| `GET /api/scans/{id}/stacks` | | Summaries of the scan's pose stacks; each is then read through the stack endpoints. |
| `GET /api/scans/{id}/zip` | | The export for photogrammetry (see [3d-scanning.md](3d-scanning.md#review-and-export)). |
| `POST /api/scans/{id}/continue` | C | Continue an unfinished scan; finished poses are skipped. |
| `DELETE /api/scans/{id}` | C | Delete the scan and its pose stacks. |
