"""The centring wizard's measurements, end to end against the simulated rig."""

from __future__ import annotations

import pytest

from macrorail.machine import Machine, OperationError
from macrorail.sim.specimen import SimSpecimen

from .conftest import idle, until


async def rig(machine: Machine) -> SimSpecimen:
    """Rail and module homed, the specimen roughly in focus."""
    await until(lambda: machine.module.state.connected and machine.camera.state.connected)
    await machine.update_settings({"scan": {"span_mm": 3.0}})
    machine.home()
    await idle(machine, timeout=30)
    machine.home_module(("tilt", "yaw"))
    await idle(machine, timeout=30)
    specimen: SimSpecimen = machine.camera._specimen()[0]  # type: ignore[attr-defined]
    machine.set_point("start", round(18.5 * machine.axis.steps_per_mm))
    machine.go_to("start")
    await idle(machine, timeout=30)
    return specimen


async def test_centring_needs_the_rig(machine: Machine) -> None:
    await until(lambda: machine.module.state.connected)
    with pytest.raises(OperationError, match="Home"):
        machine.measure_centring()
    with pytest.raises(OperationError, match="Home"):
        machine.measure_height()


async def test_centring_rounds_converge(machine: Machine) -> None:
    specimen = await rig(machine)
    specimen.offset_mm = (0.6, -0.4, 0.15)

    machine.measure_centring()
    await idle(machine, timeout=120)
    assert machine.centring, machine.log.entries[-1].message
    first = machine.centring[-1]
    assert first.offset_x_mm == pytest.approx(0.6, abs=0.05)
    assert first.offset_y_mm == pytest.approx(-0.4, abs=0.05)
    assert not first.centred
    # The rail's direction and the axis's place in the image are learnt for later.
    assert machine.module_settings.rail_sign == 1
    assert machine.module_settings.axis_image_x == pytest.approx(0.5, abs=0.01)

    # Turn the screws as advised.
    advice = machine.snapshot()["module"]["centring"]["turns"]
    assert {t["screw"]: t["turns"] for t in advice} == {"x": 1.25, "y": -0.75}
    for turn in advice:
        specimen.turn_screw(turn["screw"], turn["turns"])

    machine.measure_centring()
    await idle(machine, timeout=120)
    second = machine.centring[-1]
    assert second.centred, second
    assert machine.snapshot()["module"]["centring"]["turns"] == []

    machine.measure_height()
    await idle(machine, timeout=120)
    assert machine.height_mm == pytest.approx(0.15, abs=0.04), machine.log.entries[-1].message
    assert abs(machine.module.tilt_deg()) < 0.2

    machine.new_specimen()
    snapshot = machine.snapshot()["module"]["centring"]
    assert snapshot["rounds"] == []
    assert snapshot["height_mm"] is None
