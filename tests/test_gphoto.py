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
GP_WIDGET_TEXT = 2
GP_WIDGET_RADIO = 5
GP_FILE_TYPE_NORMAL = 1


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
    extension: str = "JPG"
    pending_events: list[tuple[int, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(
        default_factory=lambda: {
            "batterylevel": ["80%", None],
            "iso": ["100", ["100", "200", "400"]],
            "shutterspeed": ["1/125", ["1/60", "1/125"]],
        }
    )


class FakeWidget:
    def __init__(self, world: FakeWorld, name: str) -> None:
        self.world, self.name = world, name
        self.value, self.choices = world.config[name]

    def get_type(self) -> int:
        return GP_WIDGET_TEXT if self.choices is None else GP_WIDGET_RADIO

    def get_choices(self) -> list[str]:
        return list(self.choices)

    def get_value(self) -> str:
        return str(self.value)

    def get_readonly(self) -> int:
        return 0

    def set_value(self, value: str) -> None:
        if self.choices is not None and value not in self.choices:
            raise GPhoto2Error(-2)
        self.value = value


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
        if name not in self.world.config:
            raise GPhoto2Error(-2)
        return FakeWidget(self.world, name)

    def set_single_config(self, name: str, widget: FakeWidget) -> None:
        self.world.config[name][0] = widget.value

    def file_get(self, folder: str, name: str, kind: int) -> Any:
        assert (folder, kind) == ("/store_00010001", GP_FILE_TYPE_NORMAL)
        return types.SimpleNamespace(get_data_and_size=lambda: memoryview(name.encode()))

    def trigger_capture(self) -> None:
        if self.world.trigger_failures:
            self.world.trigger_failures -= 1
            raise GPhoto2Error(-7)
        self.world.triggers += 1
        name = f"DSC{self.world.triggers:05d}.{self.world.extension}"
        added = types.SimpleNamespace(folder="/store_00010001", name=name)
        self.world.pending_events.append((GP_EVENT_FILE_ADDED, added))

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
    module.GP_WIDGET_RADIO = GP_WIDGET_RADIO  # type: ignore[attr-defined]
    module.GP_WIDGET_MENU = 6  # type: ignore[attr-defined]
    module.GP_FILE_TYPE_NORMAL = GP_FILE_TYPE_NORMAL  # type: ignore[attr-defined]
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
    assert capture.name == "DSC00001.JPG"
    task.cancel()


async def test_capture_reconnects_and_retries_once(world: FakeWorld) -> None:
    camera, task = await start_camera()
    world.trigger_failures = 1
    capture = await camera.capture()
    assert capture.name == "DSC00001.JPG"
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


async def test_settings_are_read_and_written(world: FakeWorld) -> None:
    camera, task = await start_camera()
    keys = {s.key: s for s in camera.state.settings}
    assert set(keys) == {"iso", "shutterspeed"}  # the curated ones this camera has
    assert keys["iso"].choices == ("100", "200", "400")
    await camera.set_setting("iso", "400")
    assert next(s for s in camera.state.settings if s.key == "iso").value == "400"
    with pytest.raises(CameraError, match="refused"):
        await camera.set_setting("iso", "123")
    task.cancel()


async def test_capture_reports_where_the_file_is_and_downloads_it(world: FakeWorld) -> None:
    camera, task = await start_camera()
    capture = await camera.capture()
    assert capture.folder == "/store_00010001"
    assert capture.is_jpeg
    assert await camera.download(capture) == b"DSC00001.JPG"
    task.cancel()
