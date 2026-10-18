"""Installation config: hardware constants that only change when the hardware does.

Loaded from a TOML file (see deploy/config.example.toml). User-tunable values that change
from session to session live in `settings.py` instead.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "macrorail" / "config.toml"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "macrorail"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RailConfig(_Section):
    port: str = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
    steps_per_mm: int = Field(400, gt=0, description="Microsteps per mm of carriage travel.")
    min_mm: float = Field(
        0.5, ge=0, description="Soft limit nearest the switch; parked here after homing."
    )
    travel_mm: float = Field(140.0, gt=0, description="Soft limit furthest from the switch.")
    homing_speed_mm_s: float = Field(2.0, gt=0)
    homing_probe_speed_mm_s: float = Field(0.2, gt=0)
    homing_backoff_mm: float = Field(1.0, gt=0)
    homing_accel_mm_s2: float = Field(10.0, gt=0)


class CameraConfig(_Section):
    capture_timeout_s: float = Field(10.0, gt=0)
    liveview_max_fps: float = Field(10.0, gt=0)


class ServerConfig(_Section):
    host: str = "0.0.0.0"
    port: int = 8000


class Config(_Section):
    rail: RailConfig = RailConfig()
    camera: CameraConfig = CameraConfig()
    server: ServerConfig = ServerConfig()
    data_dir: Path = DEFAULT_DATA_DIR


def load_config(path: Path | None = None) -> Config:
    """Load config from `path`, or the default location if it exists, else built-in defaults."""
    if path is None:
        if not DEFAULT_CONFIG_PATH.exists():
            return Config()
        path = DEFAULT_CONFIG_PATH
    with path.open("rb") as f:
        return Config.model_validate(tomllib.load(f))
