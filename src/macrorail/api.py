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
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from . import __version__
from .log import LogEntry
from .machine import Machine, OperationError, Point
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
    # asks for it with the stack's revision), so browsers may keep them.
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
