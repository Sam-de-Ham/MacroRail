"""GPhotoCamera against a fake python-gphoto2 module (libgphoto2 isn't available in CI)."""

from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

from macrorail.camera.base import CameraError
from macrorail.config import CameraConfig
from macrorail.log import ActivityLog

GP_EVENT_TIMEOUT = 0
GP_EVENT_FILE_ADDED = 2


class GPhoto2Error(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"[{code}] gphoto2 error")
        self.code = code


@dataclass
class FakeWorld:
    """What the fake cameras do; shared by every Camera() the code creates."""

    present: bool = True
    trigger_failures: int = 0
    inits: int = 0
    exits: int = 0
    triggers: int = 0
    pending_events: list[tuple[int, Any]] = field(default_factory=list)


class FakeCamera:
    world: FakeWorld

    def init(self) -> None:
        if not self.world.present:
            raise GPhoto2Error(-105)
        self.world.inits += 1

    def exit(self) -> None:
        self.world.exits += 1

    def get_abilities(self) -> Any:
        return types.SimpleNamespace(model="Sony Alpha-A6400 (Control)")

    def get_single_config(self, name: str) -> Any:
        assert name == "batterylevel"
        return types.SimpleNamespace(get_value=lambda: "80%")

    def trigger_capture(self) -> None:
        if self.world.trigger_failures:
            self.world.trigger_failures -= 1
            raise GPhoto2Error(-7)
        self.world.triggers += 1
        name = f"DSC{self.world.triggers:05d}.ARW"
        self.world.pending_events.append((GP_EVENT_FILE_ADDED, types.SimpleNamespace(name=name)))

    def wait_for_event(self, timeout_ms: int) -> tuple[int, Any]:
        if self.world.pending_events:
            return self.world.pending_events.pop(0)
        return GP_EVENT_TIMEOUT, None

    def capture_preview(self) -> Any:
        return types.SimpleNamespace(get_data_and_size=lambda: memoryview(b"\xff\xd8jpeg"))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> FakeWorld:
    state = FakeWorld()
    module = types.ModuleType("gphoto2")
    module.Camera = type("Camera", (FakeCamera,), {"world": state})  # type: ignore[attr-defined]
    module.GPhoto2Error = GPhoto2Error  # type: ignore[attr-defined]
    module.GP_EVENT_TIMEOUT = GP_EVENT_TIMEOUT  # type: ignore[attr-defined]
    module.GP_EVENT_FILE_ADDED = GP_EVENT_FILE_ADDED  # type: ignore[attr-defined]
    module.GP_ERROR_BAD_PARAMETERS = -2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gphoto2", module)
    return state


async def start_camera() -> tuple[Any, asyncio.Task[None]]:
    from macrorail.camera.gphoto import GPhotoCamera

    camera = GPhotoCamera(CameraConfig(capture_timeout_s=0.5), ActivityLog(), lambda: None)
    task = asyncio.create_task(camera.run())
    for _ in range(100):
        if camera.state.connected or camera.state.problem != "Looking for the camera…":
            break
        await asyncio.sleep(0.01)
    return camera, task


async def test_connects_with_live_view(world: FakeWorld) -> None:
    camera, task = await start_camera()
    assert camera.state.connected
    assert camera.state.live_view
    assert camera.state.model == "Sony Alpha-A6400 (Control)"
    assert camera.state.battery == "80%"
    assert await camera.preview() == b"\xff\xd8jpeg"
    task.cancel()


async def test_capture_waits_for_the_new_file(world: FakeWorld) -> None:
    camera, task = await start_camera()
    capture = await camera.capture()
    assert capture.name == "DSC00001.ARW"
    task.cancel()


async def test_capture_reconnects_and_retries_once(world: FakeWorld) -> None:
    camera, task = await start_camera()
    world.trigger_failures = 1
    capture = await camera.capture()
    assert capture.name == "DSC00001.ARW"
    assert world.inits == 2
    assert camera.state.connected
    task.cancel()


async def test_capture_gives_up_after_the_retry(world: FakeWorld) -> None:
    camera, task = await start_camera()
    world.trigger_failures = 2
    with pytest.raises(CameraError):
        await camera.capture()
    assert not camera.state.connected
    task.cancel()


async def test_missing_camera_is_explained(world: FakeWorld) -> None:
    world.present = False
    camera, task = await start_camera()
    assert not camera.state.connected
    assert camera.state.problem is not None
    assert "No camera found" in camera.state.problem
    task.cancel()


async def test_shutdown_closes_the_session(world: FakeWorld) -> None:
    camera, task = await start_camera()
    assert camera.state.connected
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert world.exits == 1
