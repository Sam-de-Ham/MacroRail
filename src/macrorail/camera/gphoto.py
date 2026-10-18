"""USB camera control through libgphoto2 (tested with a Sony A6400 in "PC Remote" mode).

All gphoto2 calls run on one worker thread, so the camera session is only ever used by one
caller at a time. A shot is `trigger_capture` followed by waiting for the camera's
FILE_ADDED event: the image is confirmed written before the stack moves on. (A blocking
`capture()` was unreliable with Sony bodies and dropped the USB session.)
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from ..config import CameraConfig
from ..log import ActivityLog
from .base import CameraError, CameraState, Capture

CHECK_INTERVAL_S = 30.0
RETRY_INTERVAL_S = 3.0

_GP_ERROR_MODEL_NOT_FOUND = -105
_GP_ERROR_IO_USB_CLAIM = -53


class GPhotoCamera:
    def __init__(
        self, config: CameraConfig, log: ActivityLog, on_change: Callable[[], None]
    ) -> None:
        import gphoto2

        self._gp: Any = gphoto2
        self._config = config
        self._log = log
        self._on_change = on_change
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera")
        self._camera: Any = None  # gp.Camera, touched only on the worker thread
        self._state = CameraState(problem="Looking for the camera…")

    @property
    def state(self) -> CameraState:
        return self._state

    async def run(self) -> None:
        last_problem: str | None = None
        while True:
            if not self._state.connected:
                try:
                    model, battery = await self._call(self._open)
                except CameraError as exc:
                    if str(exc) != last_problem:
                        self._log.warning(str(exc))
                    last_problem = str(exc)
                    self._update(problem=str(exc))
                    await asyncio.sleep(RETRY_INTERVAL_S)
                    continue
                last_problem = None
                self._update(connected=True, model=model, battery=battery, problem=None)
                self._log.info(f"Camera connected: {model}.")
            await asyncio.sleep(CHECK_INTERVAL_S)
            if self._state.connected:
                try:
                    battery = await self._call(self._battery)
                    self._update(battery=battery)
                except CameraError as exc:
                    self._lost(exc)

    async def capture(self) -> Capture:
        self._require_connected()
        try:
            return await self._call(self._capture)
        except CameraError as first:
            # Re-open the session and try once more. If the first trigger did fire but its
            # confirmation was lost, this costs one duplicate frame, never a missing one.
            self._log.warning(f"{first} Reconnecting and retrying the shot.")
            try:
                await self._call(self._open)
                return await self._call(self._capture)
            except CameraError as second:
                self._lost(second)
                raise

    async def preview(self) -> bytes:
        self._require_connected()
        try:
            return await self._call(self._preview)
        except CameraError as exc:
            self._lost(exc)
            raise

    # -- helpers on the event loop ------------------------------------------------------------

    async def _call[T](self, fn: Callable[[], T]) -> T:
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn)

    def _require_connected(self) -> None:
        if not self._state.connected:
            raise CameraError(self._state.problem or "The camera is not connected.")

    def _lost(self, exc: CameraError) -> None:
        if self._state.connected:
            self._log.error(f"Camera disconnected: {exc}")
        self._update(connected=False, problem=str(exc))
        self._executor.submit(self._close)

    def _update(self, **changes: Any) -> None:
        new = replace(self._state, **changes)
        if new != self._state:
            self._state = new
            self._on_change()

    # -- worker thread ------------------------------------------------------------------------

    def _open(self) -> tuple[str, str | None]:
        self._close()
        gp = self._gp
        camera = gp.Camera()
        try:
            camera.init()
        except gp.GPhoto2Error as exc:
            raise CameraError(_describe(exc)) from None
        self._camera = camera
        model = str(camera.get_abilities().model)
        return model, self._battery()

    def _close(self) -> None:
        if self._camera is not None:
            with contextlib.suppress(self._gp.GPhoto2Error):  # already gone
                self._camera.exit()
            self._camera = None

    def _battery(self) -> str | None:
        try:
            return str(self._camera.get_single_config("batterylevel").get_value())
        except self._gp.GPhoto2Error as exc:
            if exc.code == self._gp.GP_ERROR_BAD_PARAMETERS:  # body has no battery widget
                return None
            raise CameraError(_describe(exc)) from None

    def _capture(self) -> Capture:
        gp, camera = self._gp, self._camera
        try:
            while camera.wait_for_event(0)[0] != gp.GP_EVENT_TIMEOUT:
                pass  # drop events left over from earlier activity
            started = time.monotonic()
            camera.trigger_capture()
            deadline = started + self._config.capture_timeout_s
            while time.monotonic() < deadline:
                event, data = camera.wait_for_event(250)
                if event == gp.GP_EVENT_FILE_ADDED:
                    return Capture(name=data.name, duration_s=time.monotonic() - started)
        except gp.GPhoto2Error as exc:
            raise CameraError(_describe(exc)) from None
        raise CameraError(
            f"The camera did not confirm the shot within {self._config.capture_timeout_s:g} s."
        )

    def _preview(self) -> bytes:
        try:
            file = self._camera.capture_preview()
            return bytes(file.get_data_and_size())
        except self._gp.GPhoto2Error as exc:
            raise CameraError(_describe(exc)) from None


def _describe(exc: Any) -> str:
    code = getattr(exc, "code", None)
    if code == _GP_ERROR_MODEL_NOT_FOUND:
        return "No camera found. Check the USB cable and that the camera is on in PC Remote mode."
    if code == _GP_ERROR_IO_USB_CLAIM:
        return "The camera is in use by another program (for example a desktop file manager)."
    return f"Camera error: {exc}."
