"""USB camera control through libgphoto2 (tested with a Sony A6400 in "PC Remote" mode).

All gphoto2 calls run on one worker thread, so the camera session is only ever used by one
caller at a time. A shot is `trigger_capture` followed by waiting for the camera's
FILE_ADDED event: the image is confirmed written before the stack moves on. (A blocking
`capture()` was unreliable with Sony bodies and dropped the USB session.)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from ..config import CameraConfig
from ..log import ActivityLog
from .base import CameraError, CameraSetting, CameraState, Capture

logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = 30.0
RETRY_INTERVAL_S = 3.0

# The settings shown in the UI, by gphoto2 widget name. Ones a camera lacks are skipped.
SETTINGS = (
    ("iso", "ISO"),
    ("shutterspeed", "Shutter"),
    ("f-number", "Aperture"),
    ("exposurecompensation", "Exposure compensation"),
    ("whitebalance", "White balance"),
    ("imagequality", "Image quality"),
    ("imagesize", "Image size"),
    ("focusmode", "Focus mode"),
)

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
        self._lost_event = asyncio.Event()

    @property
    def state(self) -> CameraState:
        return self._state

    async def run(self) -> None:
        try:
            while True:
                try:
                    await self._supervise()
                except Exception as exc:  # the supervisor must outlive any bug: reconnect
                    logger.exception("camera supervision failed")
                    self._lost(CameraError(f"Unexpected camera error ({exc}). Reconnecting."))
                    await asyncio.sleep(RETRY_INTERVAL_S)
        finally:
            # End the camera's remote session cleanly: a Sony left mid-session stops answering
            # until it is switched off and on again.
            await asyncio.get_running_loop().run_in_executor(self._executor, self._close)

    async def _supervise(self) -> None:
        last_problem: str | None = None
        while True:
            if not self._state.connected:
                try:
                    model, battery = await self._call(self._open)
                    settings = await self._call(self._read_settings)
                except CameraError as exc:
                    if str(exc) != last_problem:
                        self._log.warning(str(exc))
                    last_problem = str(exc)
                    self._update(problem=str(exc))
                    await asyncio.sleep(RETRY_INTERVAL_S)
                    continue
                last_problem = None
                self._update(
                    connected=True,
                    model=model,
                    battery=battery,
                    live_view=True,
                    settings=settings,
                    problem=None,
                )
                self._log.info(f"Camera connected: {model}.")
            self._lost_event.clear()
            with contextlib.suppress(TimeoutError):  # a lost camera is looked for right away
                await asyncio.wait_for(self._lost_event.wait(), CHECK_INTERVAL_S)
            if self._state.connected:
                try:
                    battery = await self._call(self._battery)
                    self._update(battery=battery, settings=await self._call(self._read_settings))
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

    async def download(self, capture: Capture) -> bytes:
        self._require_connected()
        return await self._call(lambda: self._download(capture))

    async def preview(self) -> bytes:
        self._require_connected()
        try:
            return await self._call(self._preview)
        except CameraError as exc:
            self._lost(exc)
            raise

    async def refresh_settings(self) -> None:
        self._require_connected()
        self._update(settings=await self._call(self._read_settings))

    async def set_setting(self, key: str, value: str) -> None:
        self._require_connected()
        await self._call(lambda: self._write_setting(key, value))
        self._update(settings=await self._call(self._read_settings))

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
        self._lost_event.set()

    def _update(self, **changes: Any) -> None:
        new = replace(self._state, **changes)
        if new != self._state:
            self._state = new
            self._on_change()

    # -- worker thread ------------------------------------------------------------------------

    def _open(self) -> tuple[str, str | None]:
        self._close()
        gp = self._gp
        try:
            camera = gp.Camera()
            camera.init()
            self._camera = camera
            return str(camera.get_abilities().model), self._battery()
        except gp.GPhoto2Error as exc:
            self._close()
            raise CameraError(_describe(exc)) from None

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
                    elapsed = time.monotonic() - started
                    return Capture(folder=data.folder, name=data.name, duration_s=elapsed)
        except gp.GPhoto2Error as exc:
            raise CameraError(_describe(exc)) from None
        raise CameraError(
            f"The camera did not confirm the shot within {self._config.capture_timeout_s:g} s."
        )

    def _download(self, capture: Capture) -> bytes:
        gp = self._gp
        try:
            file = self._camera.file_get(capture.folder, capture.name, gp.GP_FILE_TYPE_NORMAL)
            return bytes(file.get_data_and_size())
        except gp.GPhoto2Error as exc:
            raise CameraError(f"Could not download {capture.name}: {_describe(exc)}") from None

    def _read_settings(self) -> tuple[CameraSetting, ...]:
        gp = self._gp
        settings = []
        for key, label in SETTINGS:
            try:
                widget = self._camera.get_single_config(key)
            except gp.GPhoto2Error:
                continue  # this camera doesn't have it
            listed = widget.get_type() in (gp.GP_WIDGET_RADIO, gp.GP_WIDGET_MENU)
            choices = tuple(str(c) for c in widget.get_choices()) if listed else ()
            readonly = bool(widget.get_readonly())
            value = str(widget.get_value())
            settings.append(CameraSetting(key, label, value, choices, readonly))
        return tuple(settings)

    def _write_setting(self, key: str, value: str) -> None:
        gp = self._gp
        try:
            widget = self._camera.get_single_config(key)
            widget.set_value(value)
            self._camera.set_single_config(key, widget)
        except gp.GPhoto2Error as exc:
            raise CameraError(f"The camera refused {key} = {value}: {_describe(exc)}") from None

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
