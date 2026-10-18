import pytest

from macrorail.motion.protocol import Event, ProtocolError, Reply, format_request, parse_line


def test_format_request() -> None:
    assert format_request(7, "MOVE", 4000, 400, 4000) == "7 MOVE 4000 400 4000"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("3 OK", Reply(3, True)),
        ("3 OK pos=12", Reply(3, True, None, {"pos": "12"})),
        ("4 ERR LIMIT", Reply(4, False, "LIMIT")),
        ("4 ERR STOPPED pos=-5", Reply(4, False, "STOPPED", {"pos": "-5"})),
        ("! POS pos=99", Event("POS", {"pos": "99"})),
        (
            "! READY fw=1.0.0 proto=1 driver=ok",
            Event("READY", {"fw": "1.0.0", "proto": "1", "driver": "ok"}),
        ),
    ],
)
def test_parse_line(line: str, expected: Reply | Event) -> None:
    assert parse_line(line) == expected


@pytest.mark.parametrize("line", ["", "!", "x OK", "3 MAYBE", "3 ERR", "3 OK pos", "! POS =1"])
def test_parse_line_rejects_malformed(line: str) -> None:
    with pytest.raises(ProtocolError):
        parse_line(line)
