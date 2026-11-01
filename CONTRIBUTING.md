# Contributing

Bug reports, ideas and pull requests are welcome. For anything larger than a small fix, open an
issue first so we can agree on the approach.

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.13 and the dependencies:

```bash
uv sync
```

## Running the simulator

```bash
uv run macrorail --sim
```

Then open http://localhost:8000. The simulator speaks the real serial protocols, so everything
above the transport is the production code. It keeps its data in a `sim/` folder next to the
normal data paths.

## Checks

All of these must pass; CI runs the same ones.

```bash
uv run pytest --cov            # tests against the simulator, with a coverage summary
uv run ruff check
uv run ruff format --check
uv run mypy                    # src, tests and scripts
npx @biomejs/biome@2.5.15 ci   # lints the web UI's JavaScript
```

The tests run the simulators about 25 times faster than real time. A full run takes a few
minutes, most of it in the 3D scan tests.

Optionally, install the git hooks (ruff, mypy, whitespace) with `uvx pre-commit install`.

## Firmware

Both firmware projects build with [PlatformIO](https://platformio.org/)
(`uv tool install platformio`):

```bash
pio run -d firmware            # the rail's Nano
pio run -d firmware-module     # the scan module's Nano
pio check -d firmware -e nano  # cppcheck, as in CI (same for firmware-module)
```

Flashing is described in the README (rail) and `docs/wiring.md` (scan module). A change to
either serial protocol needs the matching change in the simulator (`src/macrorail/sim/`) and in
`docs/protocol.md` or `docs/protocol-module.md`.

## Style

- Behaviour in 2D mode must not change unless that is the point of the change.
- Keep it simple: fix causes, not symptoms, and add only what is needed.
- Comments explain why, briefly.

## Licence

By contributing you agree that your contributions are licensed under the project's licences:
the [PolyForm Noncommercial License 1.0.0](LICENSE) for code, and
[CC BY-NC 4.0](hardware/LICENSE) for the hardware designs.
