"""Fetches live-view frames while someone is watching, and hands them to every viewer."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from functools import partial

from .base import Camera, CameraError

IDLE_POLL_S = 0.2
ERROR_BACKOFF_S = 1.0


class LiveView:
    def __init__(self, camera: Camera, max_fps: float, paused: Callable[[], bool]) -> None:
        self._camera = camera
        self._interval = 1.0 / max_fps
        self._paused = paused
        self._viewers = 0
        self._frame: bytes | None = None
        self._sequence = 0
        self._new_frame = asyncio.Condition()

    @property
    def viewers(self) -> int:
        return self._viewers

    def _wanted(self) -> bool:
        state = self._camera.state
        return self._viewers > 0 and state.connected and state.live_view and not self._paused()

    async def run(self) -> None:
        while True:
            if not self._wanted():
                await asyncio.sleep(IDLE_POLL_S)
                continue
            started = time.monotonic()
            try:
                frame = await self._camera.preview()
            except CameraError:
                await asyncio.sleep(ERROR_BACKOFF_S)
                continue
            async with self._new_frame:
                self._frame = frame
                self._sequence += 1
                self._new_frame.notify_all()
            await asyncio.sleep(max(0.0, self._interval - (time.monotonic() - started)))

    def _has_frame_after(self, sequence: int) -> bool:
        return self._frame is not None and self._sequence != sequence

    async def frames(self) -> AsyncIterator[bytes]:
        """Yield frames for one viewer, starting with the most recent one."""
        self._viewers += 1
        try:
            seen = 0
            while True:
                async with self._new_frame:
                    await self._new_frame.wait_for(partial(self._has_frame_after, seen))
                    frame, seen = self._frame, self._sequence
                assert frame is not None
                yield frame
        finally:
            self._viewers -= 1
