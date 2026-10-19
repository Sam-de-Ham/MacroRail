from __future__ import annotations

import asyncio
from contextlib import aclosing

from macrorail.camera.liveview import LiveView
from macrorail.sim.camera import SimCamera


async def take(view: LiveView, count: int) -> list[bytes]:
    frames: list[bytes] = []
    async with aclosing(view.frames()) as stream:
        async for frame in stream:
            frames.append(frame)
            if len(frames) == count:
                break
    return frames


async def test_frames_flow_only_while_watched() -> None:
    camera = SimCamera(lambda: 10.5)
    view = LiveView(camera, max_fps=50, paused=lambda: False)
    task = asyncio.create_task(view.run())
    try:
        frames = await asyncio.wait_for(take(view, 2), 5)
        assert all(frame.startswith(b"\xff\xd8") for frame in frames)  # JPEG
        assert view.viewers == 0
    finally:
        task.cancel()


async def test_paused_view_sends_nothing() -> None:
    camera = SimCamera(lambda: 10.5)
    view = LiveView(camera, max_fps=50, paused=lambda: True)
    task = asyncio.create_task(view.run())
    try:
        reader = asyncio.create_task(take(view, 1))
        await asyncio.sleep(0.5)
        assert not reader.done()
        reader.cancel()
    finally:
        task.cancel()
