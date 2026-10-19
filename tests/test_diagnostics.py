from __future__ import annotations

from pathlib import Path

from macrorail.diagnostics import THROTTLE_FLAGS, parse_driver, read_system
from macrorail.machine import Machine


def test_parse_driver() -> None:
    line = (
        "cs=12 stealth=1 stst=0 temp=120 otpw=1 ot=0 short=0 openload=0 "
        "irun=12 ihold=4 mres=16 up=42"
    )
    reply = dict(field.split("=") for field in line.split())
    driver = parse_driver(reply)
    assert driver["stealthchop"] is True
    assert driver["temperature_above_c"] == 120
    assert driver["overtemperature_warning"] is True
    assert driver["microsteps"] == 16
    assert driver["controller_uptime_s"] == 42


def test_read_system_reports_what_exists(tmp_path: Path) -> None:
    info = read_system(tmp_path)
    assert info["disk_free_gb"] > 0
    assert info["python"]
    assert set(info.get("power", [])) <= set(THROTTLE_FLAGS.values())


async def test_machine_reports_driver_and_link(machine: Machine) -> None:
    await machine.diagnostics.refresh()
    rail = machine.snapshot()["diagnostics"]["rail"]
    assert rail["connected"]
    assert rail["connections"] == 1
    assert rail["driver"]["microsteps"] == 16
    # Until it has been idle a while, the motor holds at full current (no change mid-work).
    assert rail["driver"]["run_current_scale"] == rail["driver"]["hold_current_scale"]
