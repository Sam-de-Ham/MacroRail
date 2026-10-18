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

from PIL import Image, ImageDraw, ImageFilter

from ..camera.base import CameraError, CameraState, Capture

WIDTH, HEIGHT = 960, 640
BLUR_LEVELS = (0, 1.5, 3, 5, 8, 12)


class SimCamera:
    def __init__(
        self,
        focus_mm: Callable[[], float],
        *,
        subject_near_mm: float = 10.0,
        subject_depth_mm: float = 1.5,
        capture_s: float = 1.2,
        speedup: float = 1.0,
    ) -> None:
        self._focus_mm = focus_mm
        self._near = subject_near_mm
        self._depth = subject_depth_mm
        self._capture_s = capture_s / speedup
        self._shots = 0
        self.fail_next_captures = 0  # tests: make the next N captures fail
        self._state = CameraState(connected=True, model="Simulated camera", battery="100%",
                                  live_view=True)  # fmt: skip

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
        return Capture(name=f"DSC{self._shots:05d}.ARW", duration_s=self._capture_s)

    async def preview(self) -> bytes:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")
        return await asyncio.to_thread(self._render, self._focus_mm())

    # -- rendering ----------------------------------------------------------------------------

    @cached_property
    def _layers(self) -> tuple[list[Image.Image], Image.Image]:
        """Pre-rendered blur levels of the subject, plus its depth map (0 = nearest)."""
        sharp = Image.new("RGB", (WIDTH, HEIGHT), (14, 16, 20))
        depth = Image.new("L", (WIDTH, HEIGHT), 255)
        draw, depth_draw = ImageDraw.Draw(sharp), ImageDraw.Draw(depth)
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
                depth_draw.ellipse(box, fill=int(255 * (1 - height)))
        depth = depth.filter(ImageFilter.GaussianBlur(4))
        layers = [sharp.filter(ImageFilter.GaussianBlur(b)) if b else sharp for b in BLUR_LEVELS]
        return layers, depth

    def _render(self, focus_mm: float) -> bytes:
        layers, depth = self._layers
        focus = (focus_mm - self._near) / self._depth * 255  # focus plane on the depth scale
        frame = layers[-1]
        for level in reversed(range(len(BLUR_LEVELS) - 1)):
            band = 18 * (level + 1)
            lut = [255 if abs(d - focus) < band else 0 for d in range(256)]
            frame = Image.composite(layers[level], frame, depth.point(lut))
        buffer = io.BytesIO()
        frame.save(buffer, "JPEG", quality=80)
        return buffer.getvalue()
