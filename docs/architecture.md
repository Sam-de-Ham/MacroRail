# Architecture

```
Browser ──REST (commands)──▶ FastAPI ──▶ Machine (orchestrator, asyncio)
        ◀─WebSocket (state)──          ├─ Axis   ◀─ RailAxis ─ Link ─ USB serial ─ Nano ─ TMC2209
        ◀─MJPEG (live view)──          ├─ Camera ◀─ GPhotoCamera (one worker thread)
                                       └─ StackRun (plan + runner)
```

## Principles

- **One owner per device.** A single process owns the serial port and the camera, and the
  browser never talks to hardware. `Machine` runs one operation at a time. Stop is the only
  command that can cut in, and it is accepted from any device.
- **Never act on assumptions.** A move is done when the controller says so. A shot is done when
  the camera reports the new file. Positions come from the controller.
- **Push, don't poll.** Every change produces a state snapshot that is pushed over the
  WebSocket (at most 20 per second per client). Defaults live only in the backend.
- **Same code for the simulator and the hardware.** `--sim` swaps in a simulated controller
  that speaks the real serial protocol, and a simulated camera. Everything above the
  transport is the production code, which is what the tests exercise.

## Layers

| Module | Responsibility |
|---|---|
| `motion/protocol.py`, `motion/link.py` | Line protocol ([protocol.md](protocol.md)). Requests carry ids, so replies can never be mismatched. A missing reply means the link is dead, and it is rebuilt. |
| `motion/rail.py` | The rail as an `Axis`: connection supervision, status polling (which doubles as the controller's watchdog), homing, moves, errors in plain language. |
| `camera/gphoto.py` | gphoto2 session on one worker thread: trigger + wait for `FILE_ADDED`, re-init and one retry, live-view frames. |
| `stack/plan.py` | Pure planning: positions on the microstep grid. The range is always fully covered (the last shot lands on or just past the end). |
| `stack/runner.py` | Move → settle → shoot → confirm. Pause, resume, stop-and-return. A camera error pauses the stack and the slice is retaken on resume. Writes a JSON record per stack. |
| `machine.py` | Commands and their preconditions, the backlash-aware approach, range preview, motor current policy, settings persistence. |
| `api.py`, `web/` | REST + WebSocket + MJPEG. A plain ES-module UI with no build step. |
| `firmware/` | Nano firmware: step generation (AccelStepper), TMC2209 setup over UART, homing state machine, soft limits, link watchdog, driver fault checks. |

## Motion decisions

- **Backlash.** Every arrival at a start/end point ends with a move in the stack direction
  (overshooting first if needed), and a stack only ever moves forward. The lead-screw nut is
  therefore always loaded the same way when a frame is taken.
- **Current.** The driver runs at full current from the first move of an operation until it
  has been idle for a while (30 s by default), then drops to a low hold current. The current
  never changes between frames of a stack, because lowering it while the rotor sits between full
  steps can shift it slightly.
- **StealthChop at 1/16 with 256× interpolation**: quiet, smooth, 2.5 µm per microstep with
  the Tr8×8 screw. CoolStep and StallGuard are off, and homing uses the microswitch.
- **Motors off means position unknown.** Disabling clears the homed flag, so nothing absolute
  moves until the rail is homed again.
