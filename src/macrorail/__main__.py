"""Command line entry point: `macrorail [--sim] [--config PATH]`."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from . import __version__
from .api import create_app
from .config import load_config
from .machine import build_machine


def main() -> None:
    parser = argparse.ArgumentParser(prog="macrorail", description=__doc__)
    parser.add_argument(
        "--config", type=Path, help="config file (default: ~/.config/macrorail/config.toml)"
    )
    parser.add_argument("--sim", action="store_true", help="run against the built-in simulator")
    parser.add_argument("--host", help="override the configured listen address")
    parser.add_argument("--port", type=int, help="override the configured port")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    if args.sim:  # keep simulator settings apart from the real rail's
        config = config.model_copy(update={"data_dir": config.data_dir / "sim"})
    machine = build_machine(config, sim=args.sim)
    uvicorn.run(
        create_app(machine),
        host=args.host or config.server.host,
        port=args.port or config.server.port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
