"""User-facing activity log: recent events shown in the UI, mirrored to the Python logger."""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

Level = Literal["info", "warning", "error"]

_logger = logging.getLogger("macrorail")
_LEVELS: dict[Level, int] = {
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


@dataclass(frozen=True)
class LogEntry:
    time: float
    level: Level
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ActivityLog:
    def __init__(self, capacity: int = 200) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._listeners: list[Callable[[LogEntry], None]] = []

    @property
    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def subscribe(self, listener: Callable[[LogEntry], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def info(self, message: str) -> None:
        self._add("info", message)

    def warning(self, message: str) -> None:
        self._add("warning", message)

    def error(self, message: str) -> None:
        self._add("error", message)

    def _add(self, level: Level, message: str) -> None:
        entry = LogEntry(time.time(), level, message)
        self._entries.append(entry)
        _logger.log(_LEVELS[level], message)
        for listener in list(self._listeners):
            listener(entry)
