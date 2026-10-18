"""The camera abstraction. v1 implements it with gphoto2 over USB; v1.1 adds a relay trigger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CameraError(Exception):
    """A camera operation failed. The message is written for the user."""


@dataclass(frozen=True)
class Capture:
    name: str  # file name on the camera's card
    duration_s: float  # trigger to confirmation


@dataclass(frozen=True)
class CameraState:
    connected: bool = False
    model: str | None = None
    battery: str | None = None
    live_view: bool = False  # whether this camera can stream preview frames
    problem: str | None = None


class Camera(Protocol):
    @property
    def state(self) -> CameraState: ...

    async def run(self) -> None:
        """Keep looking for / checking the camera for the lifetime of the app."""

    async def capture(self) -> Capture:
        """Take one picture and return once the camera confirms it was written."""

    async def preview(self) -> bytes:
        """One live-view frame as JPEG."""
