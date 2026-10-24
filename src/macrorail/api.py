"""HTTP interface: REST commands, a WebSocket that pushes state, MJPEG live view, the UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, FiniteFloat
from starlette.websockets import WebSocketDisconnect

from . import __version__
from .log import LogEntry
from .machine import Machine, OperationError, Point
from .motion.module import Rotary
from .review.store import ReviewError

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"
mimetypes.add_type("application/manifest+json", ".webmanifest")
STATE_INTERVAL_S = 0.05  # at most 20 state messages a second per client


class JogBody(BaseModel):
    delta: int


class PointBody(BaseModel):
    position: int | None = None


class MotorsBody(BaseModel):
    enabled: bool


class ModuleHomeBody(BaseModel):
    axes: tuple[Rotary, ...] = ("tilt", "yaw")


class ModuleJogBody(BaseModel):
    axis: Rotary
    delta_deg: FiniteFloat


class ScanStartBody(BaseModel):
    test: bool = False


class PoseBody(BaseModel):
    tilt: FiniteFloat | None = Field(None, ge=-90, le=120)
    yaw: FiniteFloat | None = Field(None, ge=-3600, le=3600)


class CameraSettingBody(BaseModel):
    key: str
    value: str


def create_app(machine: Machine) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(machine.run())
        yield
        task.cancel()
        (outcome,) = await asyncio.gather(task, return_exceptions=True)
        if not isinstance(outcome, asyncio.CancelledError | None):
            log.error("background tasks failed", exc_info=outcome)

    app = FastAPI(title="MacroRail", version=__version__, lifespan=lifespan)

    @app.exception_handler(OperationError)
    async def refused(_: Request, exc: OperationError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ReviewError)
    async def not_found(_: Request, exc: ReviewError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.middleware("http")
    async def no_stale_ui(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"  # always revalidate after updates
        return response

    def in_control(x_client_id: Annotated[str | None, Header()] = None) -> None:
        if not machine.control.is_holder(x_client_id):
            raise HTTPException(403, "Another device is in control. Tap Take control first.")

    controlled = [Depends(in_control)]

    def snapshot(client_id: str | None) -> dict[str, Any]:
        return {
            **machine.snapshot(),
            "control": {
                "mine": machine.control.is_holder(client_id),
                "held": machine.control.holder is not None,
            },
        }

    # -- state --------------------------------------------------------------------------------

    @app.get("/api/state")
    async def state(client: str | None = None) -> dict[str, Any]:
        return snapshot(client)

    @app.websocket("/api/ws")
    async def updates(websocket: WebSocket, client: str) -> None:
        await websocket.accept()
        machine.control.connect(client)
        dirty = asyncio.Event()
        pending: list[LogEntry] = []

        def on_log(entry: LogEntry) -> None:
            pending.append(entry)
            dirty.set()

        unsubscribe_state = machine.subscribe(dirty.set)
        unsubscribe_log = machine.log.subscribe(on_log)

        async def send() -> None:
            history = [entry.to_dict() for entry in machine.log.entries]
            await websocket.send_json({"type": "log", "entries": history})
            while True:
                await websocket.send_json({"type": "state", "state": snapshot(client)})
                await asyncio.sleep(STATE_INTERVAL_S)
                await dirty.wait()
                dirty.clear()
                if pending:
                    entries = [entry.to_dict() for entry in pending]
                    pending.clear()
                    await websocket.send_json({"type": "log", "entries": entries})

        async def receive(scope: anyio.CancelScope) -> None:
            with contextlib.suppress(WebSocketDisconnect):
                while True:
                    await websocket.receive_text()  # nothing expected; this detects a close
            scope.cancel()

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(receive, group.cancel_scope)
                with contextlib.suppress(WebSocketDisconnect):
                    await send()
                group.cancel_scope.cancel()
        finally:
            unsubscribe_state()
            unsubscribe_log()

    @app.get("/api/liveview")
    async def live_view() -> StreamingResponse:
        async def frames() -> AsyncIterator[bytes]:
            async for frame in machine.live_view.frames():
                header = (
                    f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n"
                )
                yield header.encode() + frame + b"\r\n"

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    # -- commands -----------------------------------------------------------------------------

    @app.post("/api/control/take", status_code=204)
    async def take_control(x_client_id: Annotated[str, Header()]) -> None:
        machine.control.take(x_client_id)

    @app.post("/api/stop", status_code=204)
    async def stop() -> None:
        """Stop whatever is running. Allowed from any device, in control or not."""
        await machine.stop()

    @app.post("/api/rail/home", status_code=204, dependencies=controlled)
    async def home() -> None:
        machine.home()

    @app.post("/api/rail/jog", status_code=204, dependencies=controlled)
    async def jog(body: JogBody) -> None:
        machine.jog(body.delta)

    @app.post("/api/rail/motors", status_code=204, dependencies=controlled)
    async def motors(body: MotorsBody) -> None:
        await machine.set_motors(body.enabled)

    @app.post("/api/module/home", status_code=204, dependencies=controlled)
    async def home_module(body: ModuleHomeBody) -> None:
        machine.home_module(body.axes)

    @app.post("/api/module/jog", status_code=204, dependencies=controlled)
    async def jog_module(body: ModuleJogBody) -> None:
        machine.jog_module(body.axis, body.delta_deg)

    @app.post("/api/module/pose", status_code=204, dependencies=controlled)
    async def pose(body: PoseBody) -> None:
        machine.pose(body.tilt, body.yaw)

    @app.post("/api/module/calibrate/yaw", status_code=204, dependencies=controlled)
    async def calibrate_yaw() -> None:
        machine.calibrate_yaw()

    @app.post("/api/module/calibrate/tilt", status_code=204, dependencies=controlled)
    async def calibrate_tilt() -> None:
        machine.calibrate_tilt()

    @app.post("/api/module/centring", status_code=204, dependencies=controlled)
    async def measure_centring() -> None:
        machine.measure_centring()

    @app.post("/api/module/height", status_code=204, dependencies=controlled)
    async def measure_height() -> None:
        machine.measure_height()

    @app.post("/api/module/specimen", status_code=204, dependencies=controlled)
    async def new_specimen() -> None:
        machine.new_specimen()

    @app.patch("/api/scan3d/plan", status_code=204, dependencies=controlled)
    async def update_scan_plan(patch: dict[str, Any]) -> None:
        machine.update_scan_plan(patch)

    @app.post("/api/scan3d/start", status_code=204, dependencies=controlled)
    async def start_scan(body: ScanStartBody) -> None:
        machine.start_scan(test=body.test)

    @app.post("/api/scan3d/pause", status_code=204, dependencies=controlled)
    async def pause_scan() -> None:
        machine.pause_scan()

    @app.post("/api/scan3d/resume", status_code=204, dependencies=controlled)
    async def resume_scan() -> None:
        machine.resume_scan()

    @app.post("/api/scans/{scan_id}/continue", status_code=204, dependencies=controlled)
    async def continue_scan(scan_id: str) -> None:
        machine.continue_scan(scan_id)

    @app.delete("/api/scans/{scan_id}", status_code=204, dependencies=controlled)
    async def delete_scan(scan_id: str) -> None:
        machine.delete_scan(scan_id)

    @app.get("/api/scans")
    async def list_scans() -> list[dict[str, Any]]:
        return machine.scans.scans()

    @app.get("/api/scans/{scan_id}/stacks")
    async def scan_stacks(scan_id: str) -> list[dict[str, Any]]:
        try:
            record = machine.scans.record(scan_id)
        except KeyError:
            record = None
        if record is None:
            raise HTTPException(404, "No such scan.")
        ids = [r["stack"] for r in record.get("results", {}).values() if r.get("stack")]
        return machine.review.summaries(ids)

    @app.get("/api/scans/{scan_id}/zip")
    async def scan_zip(scan_id: str) -> StreamingResponse:
        try:
            name, chunks = machine.scans.archive(scan_id, machine.review)
        except KeyError:
            raise HTTPException(404, "No such scan.") from None
        except ReviewError as exc:
            raise HTTPException(409, str(exc)) from None
        return StreamingResponse(
            chunks,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/scans/{scan_id}")
    async def scan_record(scan_id: str) -> dict[str, Any]:
        try:
            record = machine.scans.record(scan_id)
        except KeyError:
            record = None
        if record is None:
            raise HTTPException(404, "No such scan.")
        return record

    @app.post("/api/points/{point}", status_code=204, dependencies=controlled)
    async def set_point(point: Point, body: PointBody) -> None:
        machine.set_point(point, body.position)

    @app.post("/api/points/{point}/go", status_code=204, dependencies=controlled)
    async def go_to_point(point: Point) -> None:
        machine.go_to(point)

    @app.post("/api/preview", status_code=204, dependencies=controlled)
    async def preview() -> None:
        machine.preview_range()

    @app.post("/api/stack/start", status_code=204, dependencies=controlled)
    async def start_stack() -> None:
        machine.start_stack()

    @app.post("/api/stack/pause", status_code=204, dependencies=controlled)
    async def pause_stack() -> None:
        machine.pause_stack()

    @app.post("/api/stack/resume", status_code=204, dependencies=controlled)
    async def resume_stack() -> None:
        machine.resume_stack()

    @app.post("/api/camera/test", status_code=204, dependencies=controlled)
    async def test_shot() -> None:
        machine.capture_test()

    @app.post("/api/scan/range", status_code=204, dependencies=controlled)
    async def find_range() -> None:
        machine.find_range()

    @app.post("/api/scan/range/apply", status_code=204, dependencies=controlled)
    async def apply_range() -> None:
        machine.apply_range()

    @app.post("/api/scan/backlash", status_code=204, dependencies=controlled)
    async def measure_backlash() -> None:
        machine.measure_backlash()

    @app.post("/api/scan/backlash/apply", status_code=204, dependencies=controlled)
    async def apply_backlash() -> None:
        machine.apply_backlash()

    @app.post("/api/camera/settings", status_code=204, dependencies=controlled)
    async def set_camera_setting(body: CameraSettingBody) -> None:
        await machine.set_camera_setting(body.key, body.value)

    @app.post("/api/camera/settings/refresh", status_code=204)
    async def refresh_camera_settings() -> None:
        await machine.refresh_camera_settings()

    # -- review -------------------------------------------------------------------------------

    @app.get("/api/stacks")
    async def stacks() -> list[dict[str, Any]]:
        return machine.review.stacks()

    @app.get("/api/stacks/{stack_id}/frames/{number}")
    async def frame(stack_id: str, number: int) -> FileResponse:
        return _image(machine.review.frame_path(stack_id, number))

    @app.get("/api/stacks/{stack_id}/preview")
    async def preview_image(stack_id: str) -> FileResponse:
        return _image(machine.review.preview_path(stack_id))

    @app.get("/api/stacks/{stack_id}/depth")
    async def depth_image(stack_id: str, colour: bool = False) -> FileResponse:
        return _image(machine.review.depth_path(stack_id, colour))

    @app.get("/api/stacks/{stack_id}/zip")
    async def stack_zip(stack_id: str) -> StreamingResponse:
        filename, chunks = machine.review.archive(stack_id)
        return StreamingResponse(
            chunks,  # a plain iterator: written in a worker thread, chunk by chunk
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/stacks/{stack_id}/preview", status_code=204, dependencies=controlled)
    async def build_preview(stack_id: str) -> None:
        await machine.build_preview(stack_id)

    @app.delete("/api/stacks/{stack_id}", status_code=204, dependencies=controlled)
    async def delete_stack(stack_id: str) -> None:
        machine.delete_stack(stack_id)

    @app.patch("/api/settings", status_code=204, dependencies=controlled)
    async def update_settings(patch: dict[str, dict[str, Any]]) -> None:
        await machine.update_settings(patch)

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def _image(path: Path) -> FileResponse:
    if not path.is_file():
        raise ReviewError("No such image.")
    # Stack images never change once written (a new preview replaces the file, and the UI
    # asks for it by the time it was made), so browsers may keep them.
    media_type = "image/png" if path.suffix == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "max-age=86400"})
