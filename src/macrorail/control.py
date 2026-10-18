"""Which browser may operate the rail: one at a time, handed over with one tap.

Each browser keeps a random client id. The first one to connect gets control; every other
browser watches until it presses "Take control". Control follows the id, not the
connection, so a phone that sleeps and reconnects keeps it.
"""

from __future__ import annotations

from collections.abc import Callable


class ControlLease:
    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self.holder: str | None = None

    def connect(self, client_id: str) -> None:
        if self.holder is None:
            self.take(client_id)

    def take(self, client_id: str) -> None:
        if self.holder != client_id:
            self.holder = client_id
            self._on_change()

    def is_holder(self, client_id: str | None) -> bool:
        return client_id is not None and client_id == self.holder
