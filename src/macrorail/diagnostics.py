"""Health of the Pi, the rail controller, its driver and the camera, for the diagnostics panel.

Refreshed every few seconds in the background. Readings a platform doesn't offer (the Pi's
temperature and power flags on a development PC, say) are left out rather than faked.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .camera.base import Camera
from .motion.base import Axis, AxisError

REFRESH_S = 5.0

# Bits of `vcgencmd get_throttled`.
THROTTLE_FLAGS = {
    0: "Under-voltage now",
    1: "CPU frequency capped now",
    2: "Throttled now",
    3: "Soft temperature limit now",
    16: "Under-voltage since boot",
    17: "CPU frequency capped since boot",
    18: "Throttled since boot",
    19: "Soft temperature limit since boot",
}


class Diagnostics:
    def __init__(
        self,
        axis: Axis,
        camera: Camera,
        data_dir: Path,
        driver_idle: Callable[[], bool],
        on_change: Callable[[], None],
    ) -> None:
        self._axis = axis
        self._camera = camera
        self._data_dir = data_dir
        self._driver_idle = driver_idle
        self._on_change = on_change
        self._started = time.time()
        self._system: dict[str, Any] = {}
        self._driver: dict[str, Any] | None = None

    async def run(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(REFRESH_S)

    async def refresh(self) -> None:
        self._system = await asyncio.to_thread(read_system, self._data_dir)
        if self._driver_idle():
            try:
                self._driver = parse_driver(await self._axis.read_driver())
            except AxisError:
                self._driver = None  # busy or gone: keep trying on the next refresh
        elif not self._axis.state.driver_ok:
            self._driver = None
        self._on_change()

    def snapshot(self) -> dict[str, Any]:
        rail = self._axis.state
        camera = self._camera.state
        return {
            "app": {"version": __version__, "started_at": self._started},
            "system": self._system,
            "rail": {
                **self._axis.diagnostics(),
                "connected": rail.connected,
                "firmware": rail.firmware,
                "driver": self._driver,
            },
            "camera": {
                "connected": camera.connected,
                "model": camera.model,
                "battery": camera.battery,
                "problem": camera.problem,
            },
        }


def parse_driver(data: dict[str, str]) -> dict[str, Any]:
    """The controller's DRIVER reply, typed."""
    number = {key: int(value) for key, value in data.items()}
    return {
        "current_scale": number["cs"],  # 0-31 of the configured full scale
        "stealthchop": bool(number["stealth"]),
        "standstill": bool(number["stst"]),
        "temperature_above_c": number["temp"],  # 0 when below the first threshold (120 °C)
        "overtemperature_warning": bool(number["otpw"]),
        "overtemperature": bool(number["ot"]),
        "short_circuit": bool(number["short"]),
        "open_load": bool(number["openload"]),
        "run_current_scale": number["irun"],
        "hold_current_scale": number["ihold"],
        "microsteps": number["mres"],
        "controller_uptime_s": number["up"],
    }


def read_system(data_dir: Path) -> dict[str, Any]:
    """What can be read about the computer this runs on (the Pi, in production)."""
    info: dict[str, Any] = {
        "host": platform.node(),
        "os": platform.platform(terse=True),
        "python": platform.python_version(),
    }
    usage = shutil.disk_usage(data_dir if data_dir.exists() else Path.home())
    info["disk_free_gb"] = round(usage.free / 1e9, 1)
    temperature = _read(Path("/sys/class/thermal/thermal_zone0/temp"))
    if temperature is not None:
        info["cpu_temp_c"] = round(int(temperature) / 1000, 1)
    if hasattr(os, "getloadavg"):
        info["load"] = round(os.getloadavg()[0], 2)
    meminfo = _read(Path("/proc/meminfo"))
    if meminfo is not None:
        fields = {line.split(":")[0]: int(line.split()[1]) for line in meminfo.splitlines()}
        info["memory_used_pct"] = round(100 * (1 - fields["MemAvailable"] / fields["MemTotal"]))
    uptime = _read(Path("/proc/uptime"))
    if uptime is not None:
        info["uptime_s"] = round(float(uptime.split()[0]))
    throttled = _throttled()
    if throttled is not None:
        info["power"] = [label for bit, label in THROTTLE_FLAGS.items() if throttled >> bit & 1]
    return info


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _throttled() -> int | None:
    """The Pi's power and throttling flags, or None when not on a Raspberry Pi."""
    if shutil.which("vcgencmd") is None:
        return None
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2, check=True
        )
        return int(result.stdout.strip().split("=")[1], 16)
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
