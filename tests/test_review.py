from __future__ import annotations

import io
from typing import cast

import numpy as np
import pytest
from PIL import Image, ImageFilter

from macrorail.machine import Machine, OperationError
from macrorail.review.images import focus_stack, shrink
from macrorail.sim.camera import SimCamera

from .conftest import homed, idle, until


def jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95)
    return buffer.getvalue()


def detail(image: Image.Image) -> float:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    return float(np.abs(np.diff(gray, axis=1)).mean())


def test_shrink_limits_the_long_side() -> None:
    small = Image.open(io.BytesIO(shrink(jpeg(Image.new("RGB", (4000, 3000), "gray")))))
    assert max(small.size) == 1600


def test_focus_stack_takes_the_sharp_half_of_each_frame() -> None:
    rng = np.random.default_rng(1)
    texture = Image.fromarray(rng.integers(0, 255, (200, 300, 3), dtype=np.uint8))
    blurred = texture.filter(ImageFilter.GaussianBlur(4))
    left_sharp, right_sharp = blurred.copy(), blurred.copy()
    left_sharp.paste(texture.crop((0, 0, 150, 200)), (0, 0))
    right_sharp.paste(texture.crop((150, 0, 300, 200)), (150, 0))
    result = Image.open(io.BytesIO(focus_stack([jpeg(left_sharp), jpeg(right_sharp)])))
    for half in ((10, 0, 140, 200), (160, 0, 290, 200)):
        assert detail(result.crop(half)) > 2 * detail(blurred.crop(half))


async def stack_of(machine: Machine, name: str = "") -> str:
    await homed(machine)
    await machine.update_settings({"stack": {"name": name}})
    machine.set_point("start", 4000)
    machine.set_point("end", 4020)
    machine.start_stack()
    await idle(machine, timeout=20)
    assert machine.stack is not None
    return machine.stack.id


async def test_stack_downloads_previews_and_builds_a_preview(machine: Machine) -> None:
    stack_id = await stack_of(machine, name="Weevil, dorsal")
    await until(lambda: machine.review.building is None and machine.review.revision > 0)
    await until(lambda: machine.review.preview_path(stack_id).exists(), timeout=10)
    [summary] = machine.review.stacks()
    assert summary["id"] == stack_id
    assert summary["name"] == "Weevil, dorsal"
    assert summary["outcome"] == "done"
    assert summary["frames"] == [1, 2, 3, 4, 5, 6]
    assert summary["preview"]


async def test_previews_can_be_turned_off(machine: Machine) -> None:
    await machine.update_settings({"camera": {"download_previews": False}})
    await stack_of(machine)
    [summary] = machine.review.stacks()
    assert summary["frames"] == []
    assert not summary["preview"]


async def test_running_stack_cannot_be_deleted(machine: Machine) -> None:
    await homed(machine)
    machine.set_point("start", 4000)
    machine.set_point("end", 4400)
    machine.start_stack()
    assert machine.stack is not None
    with pytest.raises(OperationError, match="still running"):
        machine.delete_stack(machine.stack.id)
    await machine.stop()
    await idle(machine, timeout=20)
    machine.delete_stack(machine.stack.id)
    assert machine.review.stacks() == []


async def test_camera_settings(machine: Machine) -> None:
    await machine.set_camera_setting("iso", "400")
    iso = next(s for s in machine.camera.state.settings if s.key == "iso")
    assert iso.value == "400"
    with pytest.raises(OperationError, match="refused"):
        await machine.set_camera_setting("iso", "123456")
    cast(SimCamera, machine.camera).disconnect("No camera found.")
    with pytest.raises(OperationError, match="No camera"):
        await machine.set_camera_setting("iso", "200")
