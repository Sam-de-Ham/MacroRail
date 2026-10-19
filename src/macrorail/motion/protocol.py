"""Message types for the rail controller line protocol (docs/protocol.md)."""

from __future__ import annotations

from dataclasses import dataclass, field

PROTOCOL_VERSION = 3


class ProtocolError(ValueError):
    """A line that does not follow the protocol."""


@dataclass(frozen=True)
class Reply:
    id: int
    ok: bool
    code: str | None = None
    data: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    name: str
    data: dict[str, str] = field(default_factory=dict)


def format_request(request_id: int, command: str, *args: int) -> str:
    return " ".join([str(request_id), command, *(str(int(a)) for a in args)])


def parse_line(line: str) -> Reply | Event:
    tokens = line.split()
    if not tokens:
        raise ProtocolError("empty line")
    if tokens[0] == "!":
        if len(tokens) < 2:
            raise ProtocolError(f"event without a name: {line!r}")
        return Event(tokens[1], _parse_data(tokens[2:], line))
    if len(tokens) < 2 or not tokens[0].isdigit():
        raise ProtocolError(f"not a reply or event: {line!r}")
    request_id = int(tokens[0])
    if tokens[1] == "OK":
        return Reply(request_id, True, None, _parse_data(tokens[2:], line))
    if tokens[1] == "ERR" and len(tokens) >= 3:
        return Reply(request_id, False, tokens[2], _parse_data(tokens[3:], line))
    raise ProtocolError(f"unknown reply status: {line!r}")


def _parse_data(tokens: list[str], line: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep or not key:
            raise ProtocolError(f"expected key=value, got {token!r} in {line!r}")
        data[key] = value
    return data
