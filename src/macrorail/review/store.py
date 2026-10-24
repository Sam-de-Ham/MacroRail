"""Finished and running stacks on disk: one folder per stack, for review in the browser.

    stacks/<YYYYmmdd-HHMMSS>/stack.json       the record (name, plan, every shot)
    stacks/<YYYYmmdd-HHMMSS>/frames/0001.jpg  small copy of each shot, when the camera sends JPEGs
    stacks/<YYYYmmdd-HHMMSS>/preview.jpg      quick focus-stacked preview
    stacks/<YYYYmmdd-HHMMSS>/depth.png        its depth map, 16-bit grey (white = first shot)
    stacks/<YYYYmmdd-HHMMSS>/depth-colour.jpg the same in false colour

`archive` streams a stack's folder as a zip, for downloading it to the viewing device.

The full-resolution files stay on the camera's card.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import zipfile
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from ..log import ActivityLog
from .images import focus_stack, shrink

log = logging.getLogger(__name__)

STACK_ID = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
RECORD = "stack.json"
PREVIEW = "preview.jpg"
DEPTH = "depth.png"
DEPTH_COLOUR = "depth-colour.jpg"


class ReviewError(Exception):
    """A review request could not be served. The message is written for the user."""


class ReviewStore:
    def __init__(
        self, root: Path, activity_log: ActivityLog, on_change: Callable[[], None]
    ) -> None:
        self.root = root
        self._log = activity_log
        self._on_change = on_change
        self.revision = 0  # bumped on every change, so viewers know to refresh their list
        self.building: str | None = None  # stack whose preview is being made

    def snapshot(self) -> dict[str, object]:
        return {"revision": self.revision, "building": self.building}

    # -- writing ------------------------------------------------------------------------------

    def create(self, started_at: float, tags: dict[str, Any] | None = None) -> str:
        """A new, empty stack folder. Returns its id. `tags` start its record at once (a 3D
        scan's pose is known as one from the start, so the 2D list never shows it)."""
        stamp = datetime.fromtimestamp(started_at).strftime("%Y%m%d-%H%M%S")
        stack_id, n = stamp, 1
        while (self.root / stack_id).exists():
            n += 1
            stack_id = f"{stamp}-{n}"
        (self.root / stack_id / "frames").mkdir(parents=True)
        if tags:
            self.write_record(stack_id, dict(tags))
        self._changed()
        return stack_id

    async def add_frame(self, stack_id: str, index: int, jpeg: bytes) -> None:
        small = await asyncio.to_thread(shrink, jpeg)
        await asyncio.to_thread(self.frame_path(stack_id, index).write_bytes, small)
        self._changed()

    def write_record(self, stack_id: str, record: dict[str, Any]) -> None:
        path = self._folder(stack_id) / RECORD
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self._changed()

    async def build_preview(self, stack_id: str) -> None:
        """Focus-stack the stack's frames into the preview and its depth map."""
        if self.building is not None:
            raise ReviewError("A preview is already being made.")
        folder = self._folder(stack_id)
        frames = sorted((folder / "frames").glob("*.jpg"))
        if len(frames) < 2:
            raise ReviewError("This stack has no downloaded frames to combine.")
        numbers = [int(f.stem) for f in frames]
        heights = _focus_heights(_read_record(folder), numbers) or [float(n) for n in numbers]
        self.building = stack_id
        self._changed()
        try:
            stacked = await asyncio.to_thread(
                lambda: focus_stack([f.read_bytes() for f in frames], heights)
            )
            (folder / DEPTH).write_bytes(stacked.depth)
            (folder / DEPTH_COLOUR).write_bytes(stacked.depth_colour)
            (folder / PREVIEW).write_bytes(stacked.image)  # last: its presence means all are there
        finally:
            self.building = None
            self._changed()

    def delete(self, stack_id: str) -> None:
        shutil.rmtree(self._folder(stack_id))
        self._changed()

    # -- reading ------------------------------------------------------------------------------

    def stacks(self) -> list[dict[str, Any]]:
        """Every stack, newest first."""
        if not self.root.exists():
            return []
        summaries = []
        for folder in sorted(self.root.iterdir(), reverse=True):
            if not (folder.is_dir() and STACK_ID.fullmatch(folder.name)):
                continue
            record = _read_record(folder)
            if record.get("scan") is not None:
                continue  # a 3D scan's pose: shown with its scan
            summaries.append(_summary(folder, record))
        return summaries

    def summaries(self, stack_ids: list[str]) -> list[dict[str, Any]]:
        """The summaries of these stacks (a scan's poses), skipping any that are gone."""
        out = []
        for stack_id in stack_ids:
            folder = self.root / stack_id
            if STACK_ID.fullmatch(stack_id) and folder.is_dir():
                out.append(_summary(folder, _read_record(folder)))
        return out

    def archive(self, stack_id: str) -> tuple[str, Iterator[bytes]]:
        """A zip of the stack's record, preview and frames: its file name, and its bytes in
        chunks as it is written. JPEGs are stored as they are, since they don't compress."""
        folder = self._folder(stack_id)
        files = [
            folder / RECORD,
            folder / PREVIEW,
            folder / DEPTH,
            folder / DEPTH_COLOUR,
            *sorted((folder / "frames").glob("*.jpg")),
        ]
        files = [f for f in files if f.is_file()]
        if not any(f.parent.name == "frames" for f in files):
            raise ReviewError("This stack has no downloaded frames.")
        name = _read_record(folder).get("name", "")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:40]
        base = f"MacroRail-{stack_id}" + (f"-{slug}" if slug else "")
        return f"{base}.zip", _zip_chunks(base, folder, files)

    def stacks_of_scan(self, scan_id: str) -> list[str]:
        """The stacks a 3D scan's poses made, including any its record missed (a restart)."""
        if not self.root.exists():
            return []
        return [
            folder.name
            for folder in self.root.iterdir()
            if folder.is_dir()
            and STACK_ID.fullmatch(folder.name)
            and _read_record(folder).get("scan") == scan_id
        ]

    async def keep_frames(self, stack_id: str, every: int) -> None:
        """Delete all but every `every`-th frame (and the last), once the preview is made."""
        folder = self._folder(stack_id) / "frames"

        def thin() -> None:
            frames = sorted(folder.glob("*.jpg"), key=lambda f: int(f.stem))
            for i, frame in enumerate(frames):
                if every > 1 and i % every and i != len(frames) - 1:
                    frame.unlink(missing_ok=True)

        await asyncio.to_thread(thin)
        self._changed()

    def frame_path(self, stack_id: str, index: int) -> Path:
        return self._folder(stack_id) / "frames" / f"{index:04d}.jpg"

    def preview_path(self, stack_id: str) -> Path:
        return self._folder(stack_id) / PREVIEW

    def depth_path(self, stack_id: str, colour: bool) -> Path:
        return self._folder(stack_id) / (DEPTH_COLOUR if colour else DEPTH)

    def _folder(self, stack_id: str) -> Path:
        folder = self.root / stack_id
        if not STACK_ID.fullmatch(stack_id) or not folder.is_dir():
            raise ReviewError("No such stack.")
        return folder

    def _changed(self) -> None:
        self.revision += 1
        self._on_change()


def _summary(folder: Path, record: dict[str, Any]) -> dict[str, Any]:
    frames = sorted(int(f.stem) for f in (folder / "frames").glob("*.jpg"))
    heights = _focus_heights(record, frames) if frames else None
    preview = folder / PREVIEW
    return {
        "id": folder.name,
        "name": record.get("name", ""),
        "started_at": record.get("started_at"),
        "outcome": record.get("outcome"),
        "shots": len(record.get("shots", [])),
        "planned": record.get("plan", {}).get("count"),
        "frames": frames,
        "preview": preview.exists(),
        # when the preview stack was made: tells viewers when to fetch it again
        "made_at": preview.stat().st_mtime if preview.exists() else None,
        "depth": (folder / DEPTH).exists(),
        "depth_mm": round(max(heights), 4) if heights else None,
    }


def _read_record(folder: Path) -> dict[str, Any]:
    try:
        record: dict[str, Any] = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # still running, or unreadable
    return record


def _focus_heights(record: dict[str, Any], numbers: list[int]) -> list[float] | None:
    """Each frame's focus distance from the first frame's in mm, from the shots in the
    record. None when the record doesn't say."""
    positions = {shot["index"] + 1: shot["position"] for shot in record.get("shots", [])}
    steps_per_mm = record.get("steps_per_mm")
    if not steps_per_mm or not all(n in positions for n in numbers):
        return None
    first = positions[numbers[0]]
    return [abs(positions[n] - first) / steps_per_mm for n in numbers]


class _Chunks:
    """A write-only file that hands out what was written since the last `take`. zipfile
    writes to it as to an unseekable stream (sizes go after each file's data)."""

    def __init__(self) -> None:
        self._parts: list[bytes] = []

    def write(self, data: bytes) -> int:
        self._parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def take(self) -> bytes:
        data, self._parts = b"".join(self._parts), []
        return data


def _zip_chunks(base: str, folder: Path, files: list[Path]) -> Iterator[bytes]:
    return zip_stream([(path, f"{base}/{path.relative_to(folder).as_posix()}") for path in files])


def zip_stream(entries: list[tuple[Path | bytes, str]]) -> Iterator[bytes]:
    """An uncompressed zip of files (or bytes), in chunks as it is written: nothing is staged
    on the card. Each entry is (its content, its name in the zip)."""
    sink = _Chunks()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED) as archive:
        for content, name in entries:
            if isinstance(content, bytes):
                archive.writestr(name, content)
            else:
                archive.write(content, name)
            yield sink.take()
    yield sink.take()
