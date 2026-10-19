from __future__ import annotations

import numpy as np
import pytest

from macrorail.focus.analysis import (
    AnalysisError,
    Sample,
    curve_shift,
    find_range,
    strongest_tile,
)
from macrorail.machine import Machine, OperationError
from macrorail.optics import Optics

from .conftest import homed, idle

POSITIONS = list(range(0, 1000, 10))


def scan(peaks: dict[int, float], tiles: int = 6) -> list[Sample]:
    """Synthetic scan: tile i peaks (gaussian, width 30) at peaks[i]; other tiles are flat."""
    samples = []
    for p in POSITIONS:
        values = np.ones(tiles)
        for tile, centre in peaks.items():
            values[tile] += 20 * np.exp(-(((p - centre) / 30) ** 2))
        samples.append(Sample(p, values))
    return samples


def test_range_spans_every_part_of_the_subject() -> None:
    result = find_range(scan({0: 300, 1: 450, 2: 600}), margin=5)
    assert 250 <= result.start <= 290
    assert 610 <= result.end <= 650
    assert not result.clipped
    assert max(result.coverage) == pytest.approx(1 / 3, abs=0.01)


def test_range_flags_a_subject_cut_off_by_the_scan() -> None:
    assert find_range(scan({0: 0, 1: 500}), margin=0).clipped


def test_range_needs_something_in_focus() -> None:
    with pytest.raises(AnalysisError, match="came into focus"):
        find_range(scan({}), margin=0)


def test_curve_shift_matches_a_flat_topped_curve() -> None:
    """A broad, noisy top has no clear peak; the flanks still pin the shift down."""
    rng = np.random.default_rng(1)

    def curve(offset: float) -> list[float]:
        return [
            float(np.clip(1 - abs(p - 500 - offset) / 200, 0, 0.6) + rng.normal(0, 0.01))
            for p in POSITIONS
        ]

    assert curve_shift(POSITIONS, curve(0), curve(-37), max_shift=100) == pytest.approx(37, abs=2)


def test_curve_shift_beyond_its_range_is_refused() -> None:
    values = [float(np.exp(-(((p - 500) / 40) ** 2))) for p in POSITIONS]
    shifted = [float(np.exp(-(((p - 300) / 40) ** 2))) for p in POSITIONS]
    with pytest.raises(AnalysisError, match="did not line up"):
        curve_shift(POSITIONS, values, shifted, max_shift=100)


def test_strongest_tile() -> None:
    assert strongest_tile(scan({3: 500})) == 3


def test_depth_of_field_and_step() -> None:
    optics = Optics(magnification=4, na=0.10, pixel_um=3.9)
    assert optics.depth_of_field_um == pytest.approx(55 + 9.75)
    assert optics.suggested_step(400) == 13  # 32.4 µm at 2.5 µm per step


async def test_scans_need_live_view(machine: Machine) -> None:
    with pytest.raises(OperationError, match="Home the rail"):
        machine.find_range()


async def test_auto_range_finds_the_simulated_subject(machine: Machine) -> None:
    await machine.update_settings({"scan": {"settle_s": 0.0}})
    await homed(machine)
    machine.set_point("start", 4300)  # inside the dome, which spans 10.0-11.5 mm
    machine.go_to("start")
    await idle(machine)
    machine.find_range()
    await idle(machine, timeout=60)
    assert machine.axis.state.position == 4300  # back where the scan began
    result = machine.scanner.range
    assert result is not None
    assert result.start == pytest.approx(4000, abs=40)  # the dome's top, at 10.0 mm
    assert 4400 <= result.end <= 4600  # its rim: steep and thinly detailed
    machine.apply_range()
    assert machine.settings.stack.start == result.start
    assert machine.settings.stack.end == result.end


async def test_backlash_measurement_matches_the_simulator(machine: Machine) -> None:
    await machine.update_settings({"scan": {"settle_s": 0.0}})
    await homed(machine)
    machine.set_point("start", 4120)  # a sharply detailed part of the dome
    machine.go_to("start")
    await idle(machine)
    machine.measure_backlash()
    await idle(machine, timeout=60)
    assert machine.axis.state.position == 4120
    result = machine.scanner.backlash
    assert result is not None
    assert result.backlash == pytest.approx(16, abs=3)  # SIM_BACKLASH_MM = 0.04 mm = 16 steps
    machine.apply_backlash()
    assert machine.settings.motion.backlash_mm == pytest.approx(
        result.suggested_takeup / 400, abs=0.01
    )
