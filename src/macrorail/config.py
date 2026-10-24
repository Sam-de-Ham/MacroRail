"""Installation config: hardware constants that only change when the hardware does.

Loaded from a TOML file (see deploy/config.example.toml). User-tunable values that change
from session to session live in `settings.py` instead.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "macrorail" / "config.toml"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "macrorail"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


PORT_DESCRIPTION = (
    "Serial port, or 'auto' to find the controller by what it reports. Both Nanos are CH340 "
    "clones whose /dev/serial/by-id names collide, so with the scan module plugged in use "
    "'auto' or a /dev/serial/by-path/... (USB socket) path."
)


class RailConfig(_Section):
    port: str = Field("auto", description=PORT_DESCRIPTION)
    steps_per_mm: int = Field(400, gt=0, description="Microsteps per mm of carriage travel.")
    min_mm: float = Field(
        0.5,
        ge=0,
        description="Soft limit nearest the switch. After homing the rail parks here, or just "
        "past the switch's release point if that is further.",
    )
    travel_mm: float = Field(140.0, gt=0, description="Soft limit furthest from the switch.")
    homing_speed_mm_s: float = Field(1.0, gt=0)
    homing_probe_speed_mm_s: float = Field(0.2, gt=0)
    homing_clearance_mm: float = Field(
        0.5, gt=0, description="How far past the switch's release point to back off."
    )
    homing_release_max_mm: float = Field(
        5.0, gt=0, description="Homing fails if the switch is still pressed after this."
    )
    homing_accel_mm_s2: float = Field(10.0, gt=0)


class ModuleConfig(_Section):
    """The 3D scan module (its own Nano, docs/protocol-module.md). Angles in degrees: tilt 0 is
    level and + turns the insect's back towards the camera; yaw is unlimited."""

    port: str = Field("auto", description=PORT_DESCRIPTION)
    # Safe tilt range from the CAD lens-clearance sweep (hardware/scan-module/README.md).
    tilt_min_deg: float = Field(-33.0, ge=-90.0, le=0.0)
    tilt_max_deg: float = Field(90.0, ge=0.0, le=95.0)
    # Until the tilt switch's angle has been calibrated, stay this far from the lens side.
    tilt_min_uncalibrated_deg: float = Field(-20.0, ge=-90.0, le=0.0)
    tilt_speed_deg_s: float = Field(15.0, gt=0, le=60.0)
    yaw_speed_deg_s: float = Field(30.0, gt=0, le=60.0)
    accel_deg_s2: float = Field(60.0, gt=0, le=300.0)
    # Tilt homing: the rail's sequence (seek the switch, back off until released, touch slowly).
    tilt_homing_speed_deg_s: float = Field(5.0, gt=0, le=30.0)
    tilt_homing_probe_speed_deg_s: float = Field(1.0, gt=0, le=10.0)
    tilt_homing_clearance_deg: float = Field(1.0, gt=0, le=10.0)
    tilt_homing_release_max_deg: float = Field(10.0, gt=0, le=30.0)
    tilt_homing_max_deg: float = Field(150.0, gt=0, le=200.0)
    # Yaw homing: sweep past the magnet, then approach its field peak from one side.
    yaw_homing_speed_deg_s: float = Field(20.0, gt=0, le=60.0)
    yaw_homing_turns: float = Field(1.25, ge=1.1, le=1.29)  # capped at the controller's 5376
    # Every arrival at a pose ends moving the same way, so gearbox backlash is taken up.
    takeup_deg: float = Field(3.0, gt=0.0, le=20.0)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.tilt_min_uncalibrated_deg < self.tilt_min_deg:
            raise ValueError("tilt_min_uncalibrated_deg must not be below tilt_min_deg")
        if self.tilt_homing_clearance_deg >= self.tilt_homing_release_max_deg:
            raise ValueError("tilt_homing_clearance_deg must be below tilt_homing_release_max_deg")
        return self


class CameraConfig(_Section):
    capture_timeout_s: float = Field(10.0, gt=0)
    liveview_max_fps: float = Field(10.0, gt=0)


class ServerConfig(_Section):
    host: str = "0.0.0.0"
    port: int = 8000


class Config(_Section):
    rail: RailConfig = RailConfig()
    module: ModuleConfig = ModuleConfig()
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
