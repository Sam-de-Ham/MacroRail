"""The camera abstraction. v1 implements it with gphoto2 over USB; v1.1 adds a relay trigger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CameraError(Exception):
    """A camera operation failed. The message is written for the user."""


@dataclass(frozen=True)
class Capture:
    folder: str  # where the camera reported the new file
    name: str
    duration_s: float  # trigger to confirmation

    @property
    def is_jpeg(self) -> bool:
        return self.name.lower().endswith((".jpg", ".jpeg"))


@dataclass(frozen=True)
class CameraSetting:
    key: str  # the camera's own name for it, e.g. "iso"
    label: str
    value: str
    choices: tuple[str, ...]  # empty when the camera offers no list
    readonly: bool


@dataclass(frozen=True)
class CameraState:
    connected: bool = False
    model: str | None = None
    battery: str | None = None
    live_view: bool = False  # whether this camera can stream preview frames
    settings: tuple[CameraSetting, ...] = ()
    problem: str | None = None


class Camera(Protocol):
    @property
    def state(self) -> CameraState: ...

    async def run(self) -> None:
        """Keep looking for / checking the camera for the lifetime of the app."""

    async def capture(self) -> Capture:
        """Take one picture and return once the camera confirms it was written."""

    async def download(self, capture: Capture) -> bytes:
        """Fetch a captured file from the camera."""

    async def preview(self) -> bytes:
        """One live-view frame as JPEG."""

    async def refresh_settings(self) -> None:
        """Re-read the camera's settings (they can change on the camera itself)."""

    async def set_setting(self, key: str, value: str) -> None: ...
