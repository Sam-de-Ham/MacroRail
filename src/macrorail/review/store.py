"""Finished and running stacks on disk: one folder per stack, for review in the browser.

    stacks/<YYYYmmdd-HHMMSS>/stack.json       the record (name, plan, every shot)
    stacks/<YYYYmmdd-HHMMSS>/frames/0001.jpg  small copy of each shot, when the camera sends JPEGs
    stacks/<YYYYmmdd-HHMMSS>/preview.jpg      quick focus-stacked preview

The full-resolution files stay on the camera's card.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..log import ActivityLog
from .images import focus_stack, shrink

log = logging.getLogger(__name__)

STACK_ID = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
RECORD = "stack.json"
PREVIEW = "preview.jpg"


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

    def create(self, started_at: float) -> str:
        """A new, empty stack folder. Returns its id."""
        stamp = datetime.fromtimestamp(started_at).strftime("%Y%m%d-%H%M%S")
        stack_id, n = stamp, 1
        while (self.root / stack_id).exists():
            n += 1
            stack_id = f"{stamp}-{n}"
        (self.root / stack_id / "frames").mkdir(parents=True)
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
        """Focus-stack the stack's frames into preview.jpg."""
        if self.building is not None:
            raise ReviewError("A preview is already being made.")
        frames = sorted((self._folder(stack_id) / "frames").glob("*.jpg"))
        if len(frames) < 2:
            raise ReviewError("This stack has no downloaded frames to combine.")
        self.building = stack_id
        self._changed()
        try:
            preview = await asyncio.to_thread(lambda: focus_stack([f.read_bytes() for f in frames]))
            (self._folder(stack_id) / PREVIEW).write_bytes(preview)
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
            if not (folder.is_dir() and STACK_ID.match(folder.name)):
                continue
            try:
                record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                record = {}  # still running, or unreadable
            summaries.append(
                {
                    "id": folder.name,
                    "name": record.get("name", ""),
                    "started_at": record.get("started_at"),
                    "outcome": record.get("outcome"),
                    "shots": len(record.get("shots", [])),
                    "planned": record.get("plan", {}).get("count"),
                    "frames": sorted(int(f.stem) for f in (folder / "frames").glob("*.jpg")),
                    "preview": (folder / PREVIEW).exists(),
                }
            )
        return summaries

    def frame_path(self, stack_id: str, index: int) -> Path:
        return self._folder(stack_id) / "frames" / f"{index:04d}.jpg"

    def preview_path(self, stack_id: str) -> Path:
        return self._folder(stack_id) / PREVIEW

    def _folder(self, stack_id: str) -> Path:
        folder = self.root / stack_id
        if not STACK_ID.match(stack_id) or not folder.is_dir():
            raise ReviewError("No such stack.")
        return folder

    def _changed(self) -> None:
        self.revision += 1
        self._on_change()
