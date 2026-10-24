"""A simulated camera for `--sim` mode and tests.

Live view renders a synthetic subject (a compound-eye-like dome) whose sharpness depends on
the rail position, so jogging, ranges and stacks behave visibly like the real thing.
"""

from __future__ import annotations

import asyncio
import io
import math
from collections.abc import Callable
from dataclasses import replace
from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..camera.base import CameraError, CameraSetting, CameraState, Capture

if TYPE_CHECKING:
    from .specimen import SimSpecimen

# What the 3D workspace shows, when it does: the specimen and the module's (tilt, yaw) in degrees.
SpecimenView = Callable[[], "tuple[SimSpecimen, float, float] | None"]

WIDTH, HEIGHT = 960, 640
SETTINGS = (
    CameraSetting("iso", "ISO", "100", ("100", "200", "400", "800", "1600"), False),
    CameraSetting("shutterspeed", "Shutter", "1/125", ("1/60", "1/125", "1/250", "1/500"), False),
    CameraSetting("f-number", "Aperture", "f/5.6", ("f/4", "f/5.6", "f/8"), False),
    CameraSetting("imagequality", "Image quality", "RAW+JPEG", ("JPEG", "RAW", "RAW+JPEG"), False),
)
# Blur radius for each step out of focus: fine steps give smooth sharpness peaks, like real optics.
BLUR_LEVELS = tuple(0.8 * level for level in range(16))
BAND = 6  # depth units (of 255 across the subject) per blur level


class SimCamera:
    def __init__(
        self,
        focus_mm: Callable[[], float],
        *,
        subject_near_mm: float = 10.0,
        subject_depth_mm: float = 1.5,
        capture_s: float = 1.2,
        speedup: float = 1.0,
        specimen: SpecimenView | None = None,
    ) -> None:
        self._focus_mm = focus_mm
        self._specimen = specimen  # when it returns a view, frames show it instead of the dome
        self._near = subject_near_mm
        self._depth = subject_depth_mm
        self._capture_s = capture_s / speedup
        self._shots = 0
        self.fail_next_captures = 0  # tests: make the next N captures fail
        self._state = CameraState(connected=True, model="Simulated camera", battery="100%",
                                  live_view=True, settings=SETTINGS)  # fmt: skip
        self._files: dict[str, bytes] = {}  # what each capture "wrote", for download()

    @property
    def state(self) -> CameraState:
        return self._state

    async def run(self) -> None:
        await asyncio.Event().wait()  # always connected

    def disconnect(self, problem: str) -> None:
        self._state = replace(self._state, connected=False, problem=problem)

    def reconnect(self) -> None:
        self._state = replace(self._state, connected=True, problem=None)

    async def capture(self) -> Capture:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")
        await asyncio.sleep(self._capture_s)
        if self.fail_next_captures:
            self.fail_next_captures -= 1
            raise CameraError("The camera did not confirm the shot within 10 s.")
        self._shots += 1
        name = f"DSC{self._shots:05d}.JPG"
        self._files[name] = await self._frame()
        return Capture(folder="/", name=name, duration_s=self._capture_s)

    async def download(self, capture: Capture) -> bytes:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")
        return self._files.pop(capture.name)

    async def refresh_settings(self) -> None:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")

    async def set_setting(self, key: str, value: str) -> None:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")
        settings = list(self._state.settings)
        for i, setting in enumerate(settings):
            if setting.key == key:
                if setting.choices and value not in setting.choices:
                    raise CameraError(f"The camera refused {key} = {value}.")
                settings[i] = replace(setting, value=value)
                self._state = replace(self._state, settings=tuple(settings))
                return
        raise CameraError(f"The camera has no setting called {key}.")

    async def preview(self) -> bytes:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")
        return await self._frame()

    # -- rendering ----------------------------------------------------------------------------

    async def _frame(self) -> bytes:
        focus = self._focus_mm()
        view = self._specimen() if self._specimen else None
        if view is None:
            return await asyncio.to_thread(self._render, focus)
        specimen, tilt_deg, yaw_deg = view
        return await asyncio.to_thread(specimen.render, tilt_deg, yaw_deg, focus)

    @cached_property
    def _layers(self) -> tuple[list[Image.Image], Image.Image]:
        """Pre-rendered blur levels of the subject, plus its depth map (0 = nearest)."""
        sharp = Image.new("RGB", (WIDTH, HEIGHT), (14, 16, 20))
        draw = ImageDraw.Draw(sharp)
        cx, cy, radius = WIDTH / 2, HEIGHT / 2, HEIGHT * 0.44
        pitch = 22.0
        for row in range(-20, 21):
            for col in range(-25, 26):
                x = cx + (col + (row % 2) / 2) * pitch
                y = cy + row * pitch * math.sqrt(3) / 2
                r = math.hypot(x - cx, y - cy) / radius
                if r >= 1:
                    continue
                height = math.sqrt(1 - r * r)  # dome: 1 at the centre, 0 at the rim
                shade = int(90 + 120 * height)
                size = pitch * 0.42 * (0.6 + 0.4 * height)
                box = (x - size, y - size, x + size, y + size)
                draw.ellipse(box, fill=(shade, int(shade * 0.72), int(shade * 0.35)))
                draw.ellipse(
                    (x - size * 0.35, y - size * 0.55, x + size * 0.1, y - size * 0.15),
                    fill=(min(255, shade + 60),) * 3,
                )
        # Depth of the dome's surface everywhere on it: 0 at its top, 255 at its rim and beyond.
        yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH]
        r = np.hypot(xx - cx, yy - cy) / radius
        height = np.sqrt(np.clip(1 - r * r, 0, 1))
        depth = Image.fromarray((255 * (1 - height)).astype(np.uint8))
        layers = [sharp.filter(ImageFilter.GaussianBlur(b)) if b else sharp for b in BLUR_LEVELS]
        return layers, depth

    def _render(self, focus_mm: float) -> bytes:
        layers, depth = self._layers
        focus = (focus_mm - self._near) / self._depth * 255  # focus plane on the depth scale
        frame = layers[-1]
        for level in reversed(range(len(BLUR_LEVELS) - 1)):
            band = BAND * (level + 1)
            lut = [255 if abs(d - focus) < band else 0 for d in range(256)]
            frame = Image.composite(layers[level], frame, depth.point(lut))
        buffer = io.BytesIO()
        frame.save(buffer, "JPEG", quality=80)
        return buffer.getvalue()
