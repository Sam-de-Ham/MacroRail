"""Depth of field and step sizes for a lens, from its magnification and numerical aperture.

DOF ≈ λ·n/NA² + n·e/(M·NA): the wave-optics term plus the geometric term for a sensor that
resolves `e` (its pixel pitch). Air (n = 1) and green light (λ = 0.55 µm) are assumed.
A stack step of half the depth of field gives each slice a comfortable overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

WAVELENGTH_UM = 0.55
STEP_FRACTION = 0.5  # step = half the depth of field


@dataclass(frozen=True)
class Optics:
    magnification: float
    na: float
    pixel_um: float

    @property
    def depth_of_field_um(self) -> float:
        return WAVELENGTH_UM / self.na**2 + self.pixel_um / (self.magnification * self.na)

    def suggested_step(self, steps_per_mm: int) -> int:
        """The recommended stack step, in motor steps (at least one)."""
        step_um = self.depth_of_field_um * STEP_FRACTION
        return max(1, round(step_um * steps_per_mm / 1000))
