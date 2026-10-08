"""Digital phantom: water cylinder with iodine inserts of known concentration."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Insert:
    """Cylindrical iodine insert.

    x_cm / y_cm: centre position relative to the FOV centre.
    diameter_cm: insert diameter.
    iodine_g_cm3: iodine density (e.g. 0.005 g/cm^3 = 5 mgI/mL).
    """

    x_cm: float
    y_cm: float
    diameter_cm: float
    iodine_g_cm3: float

    def __post_init__(self) -> None:
        if self.diameter_cm <= 0:
            raise ValueError("insert diameter must be positive")
        if self.iodine_g_cm3 < 0:
            raise ValueError("insert iodine density must be non-negative")


@dataclass
class Phantom:
    """2-D digital phantom on a square pixel grid.

    water_density / iodine_density: areal mass per volume in g/cm^3.
    """

    water_density: np.ndarray
    iodine_density: np.ndarray
    pixel_size_cm: float
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("water_density", "iodine_density"):
            arr = np.asarray(getattr(self, name), dtype=np.float64)
            if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
                raise ValueError(f"{name} must be a square 2-D array")
            setattr(self, name, arr)
        if self.water_density.shape != self.iodine_density.shape:
            raise ValueError("water_density and iodine_density must have equal shape")
        if self.pixel_size_cm <= 0:
            raise ValueError("pixel_size_cm must be positive")
        if np.any(~np.isfinite(self.water_density)) or np.any(~np.isfinite(self.iodine_density)):
            raise ValueError("phantom densities must be finite")
        if np.any(self.water_density < 0) or np.any(self.iodine_density < 0):
            raise ValueError("phantom densities must be non-negative")

    @property
    def shape(self) -> tuple[int, int]:
        return self.water_density.shape

    @property
    def fov_cm(self) -> float:
        return self.shape[0] * self.pixel_size_cm

    @property
    def water_diameter_cm(self) -> float:
        """Diameter of the water body (from meta, for effective coefficients)."""
        return float(self.meta.get("water_diameter_cm", 0.0))


def make_water_cylinder_phantom(
    n: int = 512,
    diameter_cm: float = 25.0,
    pixel_size_cm: float = 0.05,
    inserts: tuple[Insert, ...] = (),
    water_density_g_cm3: float = 1.0,
) -> Phantom:
    """Water cylinder with optional iodine inserts, all parameters analytic.

    Raises:
        ValueError: water body does not fit the grid, or an insert lies
            partially or fully outside the water body.
    """
    if n < 16:
        raise ValueError("n must be at least 16")
    if diameter_cm <= 0 or diameter_cm > n * pixel_size_cm:
        raise ValueError("water diameter must fit within the grid")
    if water_density_g_cm3 <= 0:
        raise ValueError("water density must be positive")

    grid = (np.arange(n) + 0.5) * pixel_size_cm
    xx, yy = np.meshgrid(grid, grid)
    cx = cy = n * pixel_size_cm / 2.0
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)

    water = np.where(r <= diameter_cm / 2.0, water_density_g_cm3, 0.0)
    iodine = np.zeros((n, n), dtype=np.float64)
    for ins in inserts:
        if np.hypot(ins.x_cm, ins.y_cm) + ins.diameter_cm / 2.0 > diameter_cm / 2.0:
            raise ValueError(f"insert at ({ins.x_cm}, {ins.y_cm}) cm lies outside the water body")
        mask = np.sqrt((xx - cx - ins.x_cm) ** 2 + (yy - cy - ins.y_cm) ** 2) <= (
            ins.diameter_cm / 2.0
        )
        if np.any(iodine[mask] > 0):
            raise ValueError("inserts must not overlap")
        iodine[mask] = ins.iodine_g_cm3

    return Phantom(
        water_density=water,
        iodine_density=iodine,
        pixel_size_cm=pixel_size_cm,
        meta={"water_diameter_cm": diameter_cm, "n": n},
    )
