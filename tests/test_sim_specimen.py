"""The simulated 3D specimen: geometry, focus and the SimCamera hook (sim/specimen.py)."""

from __future__ import annotations

import io
import math
import time

import numpy as np
import pytest
from PIL import Image

from macrorail.focus.sharpness import tile_sharpness
from macrorail.sim.camera import SimCamera
from macrorail.sim.specimen import PIXEL_MM, SimSpecimen

YAWS = (0.0, 90.0, 180.0, 270.0)


def energy(jpeg: bytes) -> np.ndarray:
    """Laplacian energy per pixel, like focus/sharpness.py but at full size."""
    gray = np.asarray(Image.open(io.BytesIO(jpeg)).convert("L"), dtype=np.float32)
    laplacian = (
        4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    )
    out = np.zeros_like(gray)
    out[1:-1, 1:-1] = laplacian * laplacian
    return out


def detail_centroid(specimen: SimSpecimen, tilt: float, yaw: float) -> tuple[float, float]:
    """(u, v) centroid of where the frame has detail, focusing through the visible depth."""
    depth = specimen.true_depth_mm(tilt, yaw)
    best = np.zeros(1)
    for towards_camera in np.arange(-0.2, 1.25, 0.12):
        rail = specimen.focus_ref_mm - depth - towards_camera
        best = np.maximum(best, energy(specimen.render(tilt, yaw, rail)))
    v, u = np.nonzero(best > 0.05 * np.percentile(best, 99.5))
    return float(u.mean()), float(v.mean())


def peak_rail(specimen: SimSpecimen, tilt: float, yaw: float, rails: np.ndarray) -> np.ndarray:
    """Per tile row and in total, the rail position where the frame is sharpest."""
    tiles = np.array([tile_sharpness(specimen.render(tilt, yaw, r)) for r in rails])
    rows = tiles.sum(axis=2)  # (rails, rows)
    return rails[np.argmax(np.column_stack([rows, rows.sum(axis=1)]), axis=0)]


def test_a_centred_insect_stays_put_while_it_turns() -> None:
    specimen = SimSpecimen(offset_mm=(0.0, 0.0, 0.0))
    for yaw in YAWS:
        u, v = detail_centroid(specimen, 0, yaw)
        assert specimen.subject_px(0, yaw) == pytest.approx((479.5, 319.5))
        assert abs(u - 479.5) < 2, yaw
        assert abs(v - 319.5) < 2, yaw


def test_an_offset_insect_circles_as_the_geometry_says() -> None:
    ox, oy = 0.6, -0.4
    specimen = SimSpecimen(offset_mm=(ox, oy, 0.0))
    for yaw in YAWS:
        u, v = detail_centroid(specimen, 0, yaw)
        expected_u, expected_v = specimen.subject_px(0, yaw)
        assert abs(u - expected_u) < 3, yaw
        assert abs(v - expected_v) < 3, yaw
        # Seen from +X with image right = +Y: u follows ox·sin(yaw) + oy·cos(yaw) ...
        theta = math.radians(yaw)
        sideways = (ox * math.sin(theta) + oy * math.cos(theta)) / PIXEL_MM
        assert expected_u - 479.5 == pytest.approx(sideways)
        # ... and depth (towards the camera) follows ox·cos(yaw) - oy·sin(yaw).
        towards = ox * math.cos(theta) - oy * math.sin(theta)
        assert specimen.true_depth_mm(0, yaw) == pytest.approx(towards)
    # Explicitly: at yaw 0 screw X points at the camera and +Y is image right; +yaw is CCW
    # from above, so at yaw 90 the head's +X points along world +Y (image right).
    assert specimen.subject_px(0, 0)[0] < 479.5  # oy < 0: left of centre
    assert specimen.subject_px(0, 90)[0] > 479.5  # ox > 0 turned to +Y: right of centre


def test_tilt_moves_a_raised_point_towards_the_camera_and_down() -> None:
    specimen = SimSpecimen(offset_mm=(0.0, 0.0, 1.0))
    assert specimen.true_depth_mm(30, 0) == pytest.approx(math.sin(math.radians(30)))
    u, v = specimen.subject_px(30, 0)
    assert u == pytest.approx(479.5)
    assert v == pytest.approx(319.5 - math.cos(math.radians(30)) / PIXEL_MM)


def test_the_focus_position_follows_the_offset_depth() -> None:
    specimen = SimSpecimen(offset_mm=(0.6, -0.4, 0.15))
    # The insect's front surface is half a body length (yaw 0/180) or width (90/270) in front
    # of its centre; opposite yaws show the same extent, so their peaks differ by the depth.
    half_extent = {0.0: 1.1, 180.0: 1.1, 90.0: 0.6, 270.0: 0.6}
    peaks = {}
    for yaw in YAWS:
        depth = specimen.true_depth_mm(0, yaw)
        front = specimen.focus_ref_mm - depth - half_extent[yaw]
        peaks[yaw] = peak_rail(specimen, 0, yaw, front + np.arange(-0.05, 0.36, 0.025))[-1]
    for a, b in ((0.0, 180.0), (90.0, 270.0)):
        moved = specimen.true_depth_mm(0, b) - specimen.true_depth_mm(0, a)
        assert peaks[a] - peaks[b] == pytest.approx(moved, abs=0.03)
    assert peaks[0.0] - peaks[180.0] == pytest.approx(-1.2, abs=0.03)  # nearer: in focus sooner


@pytest.mark.parametrize("tilt", [0.0, 10.0, -10.0])
def test_a_tilted_needle_focuses_top_and_bottom_apart(tilt: float) -> None:
    needle = SimSpecimen("needle", offset_mm=(0.0, 0.0, 0.0))
    rails = needle.focus_ref_mm + np.arange(-0.6, 0.61, 0.02)
    peaks = peak_rail(needle, tilt, 0, rails)
    top_minus_bottom = peaks[0] - peaks[-2]
    # With tilt t a point at head height z sits at world X = z·sin t: the top comes towards
    # the camera and focuses at a smaller rail position. The needle is 3.2 mm long.
    expected = -3.2 * math.sin(math.radians(tilt))
    if tilt == 0:
        assert abs(top_minus_bottom) <= needle.dof_mm
    else:
        assert math.copysign(1, top_minus_bottom) == math.copysign(1, expected)
        assert abs(top_minus_bottom) == pytest.approx(abs(expected), rel=0.25)


def test_turning_a_screw_pushes_the_plate_away_and_clamps() -> None:
    specimen = SimSpecimen(offset_mm=(0.6, -0.4, 0.15))
    specimen.turn_screw("x", 1.0)
    assert specimen.offset_mm == pytest.approx((0.1, -0.4, 0.15))
    specimen.turn_screw("y", -0.5)
    assert specimen.offset_mm == pytest.approx((0.1, -0.15, 0.15))
    specimen.turn_screw("x", 10)
    assert specimen.offset_mm == pytest.approx((-2.5, -0.15, 0.15))
    specimen.turn_screw("y", -10)
    assert specimen.offset_mm == pytest.approx((-2.5, 2.5, 0.15))
    specimen.offset_mm = (0.0, 0.0, 0.0)
    assert specimen.offset_mm == (0.0, 0.0, 0.0)


def test_the_render_follows_a_changed_offset() -> None:
    specimen = SimSpecimen(offset_mm=(0.0, 0.0, 0.0))
    before = specimen.render(0, 90, 20.0)
    specimen.turn_screw("x", 1.0)  # at yaw 90 head x is image right: the insect moves left
    after = specimen.render(0, 90, 20.0)
    assert before != after
    assert specimen.subject_px(0, 90)[0] == pytest.approx(479.5 - 0.5 / PIXEL_MM)


async def test_sim_camera_keeps_the_dome_without_a_specimen() -> None:
    focus = [10.0]
    plain = SimCamera(lambda: focus[0], capture_s=0)
    hidden = SimCamera(lambda: focus[0], capture_s=0, specimen=lambda: None)
    for value in (9.5, 10.4, 11.2):
        focus[0] = value
        dome = plain._render(value)
        assert await plain.preview() == dome
        assert await hidden.preview() == dome
        capture = await hidden.capture()
        assert await hidden.download(capture) == dome


async def test_sim_camera_shows_the_specimen_when_asked() -> None:
    specimen = SimSpecimen()
    view: list[tuple[SimSpecimen, float, float] | None] = [(specimen, 15.0, 45.0)]
    camera = SimCamera(lambda: 19.7, capture_s=0, specimen=lambda: view[0])
    assert await camera.preview() == specimen.render(15.0, 45.0, 19.7)
    capture = await camera.capture()
    assert await camera.download(capture) == specimen.render(15.0, 45.0, 19.7)
    view[0] = None
    assert await camera.preview() == camera._render(19.7)


def test_render_speed() -> None:
    specimen = SimSpecimen()
    specimen.render(0, 0, 20.0)  # warm up
    start = time.perf_counter()
    for yaw in (10.0, 20.0, 30.0):
        specimen.render(5, yaw, 20.0)
    new_pose = (time.perf_counter() - start) / 3
    start = time.perf_counter()
    for k in range(10):
        specimen.render(5, 30.0, 20.0 + 0.01 * k)
    cached = (time.perf_counter() - start) / 10
    # Generous bounds (CI machines vary); typical laptop: ~110 ms new, ~20 ms cached.
    assert new_pose < 0.6
    assert cached < 0.2
