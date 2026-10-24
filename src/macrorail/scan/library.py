"""The 3D scans on disk: one folder per scan under `scans/`, holding its record."""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from ..review.store import ReviewError, ReviewStore, zip_stream
from .runner import RECORD, read_record

SCAN_ID = re.compile(r"^\d{8}-\d{6}(-\d+)?$")


class ScanLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root

    def new_id(self, started_at: float) -> str:
        stamp = datetime.fromtimestamp(started_at).strftime("%Y%m%d-%H%M%S")
        scan_id, n = stamp, 1
        while (self.root / scan_id).exists():
            n += 1
            scan_id = f"{stamp}-{n}"
        return scan_id

    def folder(self, scan_id: str) -> Path:
        if not SCAN_ID.match(scan_id):
            raise KeyError(scan_id)
        return self.root / scan_id

    def record(self, scan_id: str) -> dict[str, Any] | None:
        return read_record(self.folder(scan_id))

    def scans(self) -> list[dict[str, Any]]:
        """Every scan's summary, newest first."""
        if not self.root.exists():
            return []
        summaries = []
        for folder in sorted(self.root.iterdir(), reverse=True):
            if not (folder.is_dir() and SCAN_ID.match(folder.name)):
                continue
            record = read_record(folder)
            if record is None:
                continue
            results = record.get("results", {})
            summaries.append(
                {
                    "id": folder.name,
                    "name": record.get("plan", {}).get("name", ""),
                    "test": bool(record.get("plan", {}).get("test")),
                    "started_at": record.get("started_at"),
                    "outcome": record.get("outcome"),
                    "done": sum(1 for r in results.values() if r.get("outcome") == "done"),
                    "total": len(record.get("poses", [])),
                }
            )
        return summaries

    def archive(self, scan_id: str, review: ReviewStore) -> tuple[str, Iterator[bytes]]:
        """A zip for 3D reconstruction: one all-in-focus preview and its depth maps per pose,
        named by pose and angles (COLMAP and Meshroom take the folder of previews as it
        is), plus the scan record and a pose table with the camera's file names."""
        folder = self.folder(scan_id)
        record = read_record(folder)
        if record is None:
            raise ReviewError("That scan's record can't be read.")
        poses = {p["index"]: p for p in record.get("poses", [])}
        table = io.StringIO()
        writer = csv.writer(table)
        writer.writerow(
            ["pose", "tilt_deg", "yaw_deg", "image", "stack", "shots", "first_file", "last_file"]
        )
        base = f"MacroRail-scan-{scan_id}"
        entries: list[tuple[Path | bytes, str]] = [(folder / RECORD, f"{base}/scan.json")]
        for index, result in sorted((int(i), r) for i, r in record.get("results", {}).items()):
            if result.get("outcome") != "done":
                continue
            pose = poses.get(index, {"tilt_deg": 0.0, "yaw_deg": 0.0})
            name = f"pose-{index + 1:03d}_tilt{pose['tilt_deg']:+04.0f}_yaw{pose['yaw_deg']:03.0f}"
            preview = review.preview_path(result["stack"])
            if preview.is_file():
                entries.append((preview, f"{base}/images/{name}.jpg"))
            for colour, suffix in ((False, ".png"), (True, "-colour.jpg")):
                depth = review.depth_path(result["stack"], colour)
                if depth.is_file():
                    entries.append((depth, f"{base}/depth/{name}{suffix}"))
            files = result.get("files", [])
            writer.writerow(
                [
                    index + 1,
                    pose["tilt_deg"],
                    pose["yaw_deg"],
                    f"images/{name}.jpg",
                    result["stack"],
                    result.get("shots", len(files)),
                    files[0] if files else "",
                    files[-1] if files else "",
                ]
            )
        if len(entries) == 1:
            raise ReviewError("This scan has no finished poses yet.")
        entries.append((table.getvalue().encode("utf-8"), f"{base}/poses.csv"))
        entries.append(
            (json.dumps(_readme(record), indent=2).encode("utf-8"), f"{base}/about.json")
        )
        return f"{base}.zip", zip_stream(entries)

    def delete(self, scan_id: str) -> list[str]:
        """Remove the scan's folder. Returns its poses' stack ids (the caller deletes them)."""
        record = self.record(scan_id) or {}
        stacks = [r["stack"] for r in record.get("results", {}).values() if r.get("stack")]
        shutil.rmtree(self.folder(scan_id))
        return stacks


def _readme(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "what": "A MacroRail 3D scan: one all-in-focus image per pose, for photogrammetry.",
        "angles": "tilt 0 is level, + turns the specimen's back towards the camera; yaw + is "
        "counter-clockwise seen from above. The camera stays put; the specimen turns.",
        "depth": "depth/*.png: 16-bit grey, white = the stack's first shot.",
        "full_size": "The full-size files stay on the camera's card; poses.csv and scan.json "
        "name them per pose.",
        "plan": record.get("plan", {}),
    }
