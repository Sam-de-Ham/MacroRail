"""User-tunable settings, edited from the UI and persisted between runs.

Positions and step sizes are stored in axis steps, so they round-trip exactly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

log = logging.getLogger(__name__)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MotionSettings(_Model):
    travel_speed_mm_s: float = Field(2.0, ge=0.1, le=5.0)
    stack_speed_mm_s: float = Field(1.0, ge=0.05, le=5.0)
    accel_mm_s2: float = Field(10.0, ge=1.0, le=50.0)
    run_current_ma: int = Field(600, ge=100, le=1200)
    hold_current_ma: int = Field(200, ge=0, le=1200)
    idle_hold_after_s: float = Field(30.0, ge=5.0, le=600.0)
    backlash_mm: float = Field(0.3, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def _hold_not_above_run(self) -> Self:
        if self.hold_current_ma > self.run_current_ma:
            raise ValueError("hold current cannot exceed run current")
        return self


class StackSettings(_Model):
    mode: Literal["range", "count"] = "range"
    start: int | None = None
    end: int | None = None
    step: int = Field(4, ge=1)  # 10 µm at 400 steps/mm
    count: int = Field(50, ge=2, le=5000)
    direction: Literal[1, -1] = 1  # count mode only; range mode goes from start toward end
    settle_s: float = Field(0.8, ge=0.0, le=10.0)
    name: str = Field("", max_length=60)  # labels the stack's record and review entry


class OpticsSettings(_Model):
    """The lens in use, for the depth-of-field maths behind step sizes and focus scans."""

    magnification: float = Field(4.0, ge=0.1, le=100.0)
    na: float = Field(0.10, ge=0.01, le=1.0)  # numerical aperture
    pixel_um: float = Field(3.9, ge=0.5, le=20.0)  # sensor pixel pitch (A6400: 3.9 µm)


class ScanSettings(_Model):
    """Focus scans: sweeps that read sharpness from live view (auto range, backlash)."""

    span_mm: float = Field(4.0, ge=0.2, le=50.0)  # how far around the current position to look
    settle_s: float = Field(0.3, ge=0.0, le=5.0)  # pause after each move before reading a frame


class CameraSettings(_Model):
    download_previews: bool = True  # fetch each shot's JPEG (if the camera sends one) for review


class Settings(_Model):
    motion: MotionSettings = MotionSettings()
    stack: StackSettings = StackSettings()
    optics: OpticsSettings = OpticsSettings()
    scan: ScanSettings = ScanSettings()
    camera: CameraSettings = CameraSettings()

    def merged(self, patch: dict[str, dict[str, object]]) -> Settings:
        """A copy with `patch` ({"motion": {...}, "stack": {...}}) applied and re-validated."""
        data = self.model_dump()
        for section, values in patch.items():
            if section not in data:
                raise ValueError(f"unknown settings section: {section}")
            data[section].update(values)
        return Settings.model_validate(data)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            return Settings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (ValidationError, OSError) as exc:
            log.warning("ignoring unreadable settings file %s: %s", self.path, exc)
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
