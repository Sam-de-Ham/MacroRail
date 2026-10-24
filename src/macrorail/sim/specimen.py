"""A simulated specimen on the scan module, as the camera sees it (sim and tests).

Geometry (docs/3d-scanning.md), all in mm:

- World frame: origin where the yaw and tilt axes cross, X towards the camera, Y along the tilt
  axis, Z up (at tilt 0).
- A specimen point p in the head frame (which turns with yaw) sits at q = p + o, where o is the
  hidden centring error (ox, oy: the centring plate; oz: the pin height). Its world position is
  R_y(tilt) · R_z(yaw) · q. R_z turns counter-clockwise seen from above; R_y takes +Z towards
  +X for a positive tilt (x' = x cos t + z sin t, z' = -x sin t + z cos t).
- The camera looks along -X. Image right is +Y, image up is +Z, and the image centre is the
  world origin. Pixel (u, v) has its centre at Y = (u - (W - 1) / 2) · PIXEL_MM and
  Z = ((H - 1) / 2 - v) · PIXEL_MM.
- The rail moves the specimen along X. A point is in focus when
  world X + rail_mm - focus_ref_mm == 0; its defocus is that sum.

Rendering casts one orthographic ray per pixel against the specimen's analytic surface, which
gives a sharp image and a per-pixel world X. Blurred copies of the sharp image are made once per
pose; each frame then only blends, per pixel, the two copies whose blur matches its defocus.
"""

from __future__ import annotations

import io
import math
import threading
from collections import OrderedDict
from typing import Literal

import numpy as np
from PIL import Image, ImageFilter

from .camera import HEIGHT, WIDTH

FIELD_MM = 5.5  # field width at 4.27x on the A6400 (the height follows from the pixel size)
PIXEL_MM = FIELD_MM / WIDTH
BLUR_RADII = tuple(0.8 * level for level in range(16))  # px, one blur level per half DOF
BACKGROUND = (14, 16, 20)
PLATE_TRAVEL_MM = 2.5  # the centring plate's travel each way
SCREW_PITCH_MM = 0.5  # M3
FACET_MM = 0.035  # texture cell size (ommatidia-like facets, about 6 px)
CACHE_POSES = 3

# Insect: one ellipsoid, semi-axes along head x, y, z (2.2 x 1.2 x 1.0 mm), centred on the origin.
INSECT_AXES = (1.1, 0.6, 0.5)
# Needle: a straight pin along head z.
NEEDLE_RADIUS = 0.175
NEEDLE_HALF = 1.6

Kind = Literal["insect", "needle"]
# Where the blurred crop sits in the frame (top, left), its layers (levels, h, w, 3), world X.
_Pose = tuple[tuple[int, int], np.ndarray, np.ndarray]


def rotation(tilt_deg: float, yaw_deg: float) -> np.ndarray:
    """R = R_y(tilt) · R_z(yaw): head frame to world frame."""
    t, y = math.radians(tilt_deg), math.radians(yaw_deg)
    ct, st, cy, sy = math.cos(t), math.sin(t), math.cos(y), math.sin(y)
    r_y = np.array([[ct, 0.0, st], [0.0, 1.0, 0.0], [-st, 0.0, ct]])
    r_z = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    result: np.ndarray = r_y @ r_z
    return result


class SimSpecimen:
    def __init__(
        self,
        kind: Kind = "insect",
        *,
        offset_mm: tuple[float, float, float] = (0.6, -0.4, 0.15),
        focus_ref_mm: float = 20.0,
        dof_mm: float = 0.064,
        seed: int = 0,
    ) -> None:
        self.kind = kind
        self.focus_ref_mm = focus_ref_mm
        self.dof_mm = dof_mm
        self._seed = seed
        self._offset = np.zeros(3)
        self.offset_mm = offset_mm
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple[float, ...], _Pose | None] = OrderedDict()
        u = np.arange(WIDTH, dtype=np.float32)
        v = np.arange(HEIGHT, dtype=np.float32)
        self._world_y = (u - (WIDTH - 1) / 2) * PIXEL_MM  # (W,)
        self._world_z = ((HEIGHT - 1) / 2 - v) * PIXEL_MM  # (H,)

    # -- hidden truth --------------------------------------------------------------------------

    @property
    def offset_mm(self) -> tuple[float, float, float]:
        x, y, z = (float(c) for c in self._offset)
        return (x, y, z)

    @offset_mm.setter
    def offset_mm(self, value: tuple[float, float, float]) -> None:
        offset = np.array(value, dtype=float)
        offset[:2] = np.clip(offset[:2], -PLATE_TRAVEL_MM, PLATE_TRAVEL_MM)
        self._offset = offset

    def turn_screw(self, axis: Literal["x", "y"], turns: float) -> None:
        """Turn a centring screw in by `turns` (negative: out). In pushes the plate away from it."""
        offset = self._offset.copy()
        offset["xy".index(axis)] -= SCREW_PITCH_MM * turns
        self.offset_mm = (offset[0], offset[1], offset[2])

    def world(self, tilt_deg: float, yaw_deg: float) -> np.ndarray:
        """World position of the head-frame origin (the specimen's centre)."""
        return rotation(tilt_deg, yaw_deg) @ self._offset

    def subject_px(self, tilt_deg: float, yaw_deg: float) -> tuple[float, float]:
        """Image position (u right, v down, px) of the specimen's centre."""
        _, y, z = self.world(tilt_deg, yaw_deg)
        return ((WIDTH - 1) / 2 + y / PIXEL_MM, (HEIGHT - 1) / 2 - z / PIXEL_MM)

    def true_depth_mm(self, tilt_deg: float, yaw_deg: float) -> float:
        """World X of the specimen's centre; it is in focus at rail = focus_ref_mm - this."""
        return float(self.world(tilt_deg, yaw_deg)[0])

    # -- rendering -----------------------------------------------------------------------------

    def render(self, tilt_deg: float, yaw_deg: float, rail_mm: float) -> bytes:
        """One JPEG frame of the specimen at this pose, with the rail at `rail_mm`."""
        with self._lock:
            pose = self._pose(tilt_deg, yaw_deg)
        frame = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
        frame[:] = BACKGROUND
        if pose is not None:
            (top, left), layers, depth = pose
            levels, height, width, _ = layers.shape
            level = np.abs(depth + (rail_mm - self.focus_ref_mm)) * (2 / self.dof_mm)
            np.clip(level, 0, levels - 1, out=level)
            low = level.astype(np.intp)
            high = np.minimum(low + 1, levels - 1)
            frac = (level - low)[..., None]
            pixels = np.arange(height * width).reshape(height, width)
            flat = layers.reshape(-1, 3)
            a = flat[low * (height * width) + pixels].astype(np.float32)
            b = flat[high * (height * width) + pixels].astype(np.float32)
            frame[top : top + height, left : left + width] = a + (b - a) * frac
        buffer = io.BytesIO()
        Image.fromarray(frame).save(buffer, "JPEG", quality=80)
        return buffer.getvalue()

    def _pose(self, tilt_deg: float, yaw_deg: float) -> _Pose | None:
        """The blurred layers around the specimen, cached per pose; None if it is out of view."""
        key = (round(tilt_deg, 2), round(yaw_deg % 360, 2), *np.round(self._offset, 3).tolist())
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        sharp, depth, hit = self._rasterise(tilt_deg, yaw_deg)
        pose: _Pose | None = None
        rows, cols = np.flatnonzero(hit.any(axis=1)), np.flatnonzero(hit.any(axis=0))
        if rows.size:
            # Only the specimen and its widest blur need blurring: the rest is plain background.
            pad = math.ceil(3 * BLUR_RADII[-1])
            top, bottom = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, HEIGHT)
            left, right = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, WIDTH)
            image = Image.fromarray(sharp[top:bottom, left:right])
            layers = np.stack(
                [np.asarray(image.filter(ImageFilter.GaussianBlur(r)) if r else image)
                 for r in BLUR_RADII]
            )  # fmt: skip
            pose = ((int(top), int(left)), layers, depth[top:bottom, left:right])
        self._cache[key] = pose
        while len(self._cache) > CACHE_POSES:
            self._cache.popitem(last=False)
        return pose

    def _rasterise(
        self, tilt_deg: float, yaw_deg: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The sharp image (H, W, 3), the world X each pixel sees, and the specimen's mask.

        Pixels that miss the specimen get the X where their ray passes closest to it, so the
        blurred edge around the silhouette is as far out of focus as the edge itself.
        """
        rot = rotation(tilt_deg, yaw_deg).astype(np.float32)
        d = rot[0]  # the ray direction (world +X) in the head frame
        # Ray through pixel (Y, Z) in the head frame: p(s) = p0 + s * d, with s = world X.
        p0 = (
            self._world_y[None, :, None] * rot[1]
            + self._world_z[:, None, None] * rot[2]
            - self._offset.astype(np.float32)
        )
        if self.kind == "insect":
            s, hit, normal = _ellipsoid(p0, d, np.array(INSECT_AXES, dtype=np.float32))
            tint = np.array((235, 170, 90), dtype=np.float32)
        else:
            s, hit, normal = _needle(p0, d)
            tint = np.array((215, 218, 228), dtype=np.float32)

        sharp = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
        sharp[:] = BACKGROUND
        points = p0[hit] + s[hit][:, None] * d
        facing = np.clip(np.einsum("ij,j->i", normal, d), 0, 1)
        shade = 0.3 + 0.7 * facing
        sharp[hit] = np.clip(_texture(points, self._seed)[:, None] * shade[:, None] * tint, 0, 255)
        return sharp, s, hit


def _ellipsoid(
    p0: np.ndarray, d: np.ndarray, axes: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nearest-camera hit X per pixel, the hit mask, and unit normals at the hits."""
    a = d / axes
    b = p0 / axes
    aa = float(a @ a)
    ab = b @ a
    disc = ab * ab - aa * (np.einsum("...i,...i->...", b, b) - 1)
    hit = disc >= 0
    s = -ab / aa  # closest approach (the silhouette's depth) where the ray misses
    s[hit] += np.sqrt(disc[hit]) / aa
    points = p0[hit] + s[hit][:, None] * d
    normal = points / (axes * axes)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    return s, hit, normal


def _needle(p0: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Like `_ellipsoid`, for a capped cylinder along head z."""
    shape = p0.shape[:2]
    best = np.full(shape, -np.inf, dtype=np.float32)
    normal = np.zeros((*shape, 3), dtype=np.float32)
    dxy = float(d[0] * d[0] + d[1] * d[1])
    if dxy > 1e-9:  # the side
        b = p0[..., 0] * d[0] + p0[..., 1] * d[1]
        c = p0[..., 0] ** 2 + p0[..., 1] ** 2 - NEEDLE_RADIUS**2
        disc = b * b - dxy * c
        side = (-b + np.sqrt(np.maximum(disc, 0))) / dxy
        z = p0[..., 2] + side * d[2]
        ok = (disc >= 0) & (np.abs(z) <= NEEDLE_HALF)
        best[ok] = side[ok]
        normal[ok, 0] = (p0[ok, 0] + side[ok] * d[0]) / NEEDLE_RADIUS
        normal[ok, 1] = (p0[ok, 1] + side[ok] * d[1]) / NEEDLE_RADIUS
        closest = -b / dxy
    else:
        closest = None
    caps = []
    if abs(float(d[2])) > 1e-9:
        for end in (NEEDLE_HALF, -NEEDLE_HALF):
            cap = (end - p0[..., 2]) / d[2]
            x = p0[..., 0] + cap * d[0]
            y = p0[..., 1] + cap * d[1]
            caps.append(cap)
            ok = (x * x + y * y <= NEEDLE_RADIUS**2) & (cap > best)
            best[ok] = cap[ok]
            normal[ok] = (0.0, 0.0, math.copysign(1.0, end))
    hit = np.isfinite(best)
    if closest is None:
        closest = np.maximum(caps[0], caps[1])
    s = np.where(hit, best, closest).astype(np.float32)
    return s, hit, normal[hit]


def _texture(points: np.ndarray, seed: int) -> np.ndarray:
    """Brightness (0..1) of facets: a 3D grid of cells with random brightness and dark seams."""
    cells = points / FACET_MM
    index = np.floor(cells)
    seam = np.min(np.minimum(cells - index, index + 1 - cells), axis=1) < 0.1
    i = index.astype(np.int64)
    h = (i[:, 0] * 73856093) ^ (i[:, 1] * 19349663) ^ (i[:, 2] * 83492791) ^ (seed * 2654435761)
    h ^= h >> 13
    h *= 1274126177
    h ^= h >> 16
    value = 0.3 + 0.7 * ((h & 0xFFFF) / 65535.0)
    return np.where(seam, 0.12, value).astype(np.float32)
