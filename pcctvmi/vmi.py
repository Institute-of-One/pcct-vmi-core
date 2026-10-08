"""Water/iodine basis decomposition and virtual monoenergetic image synthesis."""

from __future__ import annotations

import numpy as np

from pcctvmi.materials import mu_rho

VMI_GRID_KEV = tuple(range(40, 191, 10))  # frozen: 40-190 keV in 10 keV steps


def decompose(
    mu_images: list[np.ndarray], mu_eff: list[dict[str, float]]
) -> tuple[np.ndarray, np.ndarray]:
    """Solve the per-pixel 2x2 basis system for water and iodine density.

    mu_images[k] is the reconstructed linear attenuation of bin k (1/cm);
    mu_eff[k][material] the bin's effective mass attenuation (cm^2/g).
    Returns (water_density, iodine_density) in g/cm^3.
    """
    if len(mu_images) != len(mu_eff) or len(mu_images) != 2:
        raise ValueError("two bins are required for the two-basis decomposition")
    mat = np.zeros((2, 2), dtype=np.float64)
    for k, coeffs in enumerate(mu_eff):
        mat[k, 0] = coeffs["water"]
        mat[k, 1] = coeffs["iodine"]
    if abs(np.linalg.det(mat)) < 1e-12:
        raise ValueError("decomposition matrix is singular")
    stack = np.stack([np.asarray(m, dtype=np.float64) for m in mu_images], axis=-1)  # (..., 2)
    sol = np.linalg.solve(mat, stack.reshape(-1, 2).T).T.reshape(*stack.shape[:-1], 2)
    return sol[..., 0], sol[..., 1]


def vmi_hu(
    water_density: np.ndarray, iodine_density: np.ndarray, energy_kev: float | np.ndarray
) -> np.ndarray:
    """Virtual monoenergetic image in HU.

    HU(E) = 1000 * (mu(E) - mu_water(E)) / mu_water(E) with
    mu(E) = a * mu/rho_w(E) + b * mu/rho_i(E)  (a in g/cm^3, b in g/cm^3).

    A scalar energy returns an image of the phantom's shape; an energy array
    returns a stack with the energy axis first (see ``vmi_stack``).
    """
    a = np.asarray(water_density, dtype=np.float64)
    b = np.asarray(iodine_density, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("water_density and iodine_density must have equal shape")
    e = np.asarray(energy_kev, dtype=np.float64)
    r = mu_rho("iodine", e) / mu_rho("water", e)  # scalar or (n_energy,)
    if e.ndim == 0:
        return 1000.0 * (a + b * float(r) - 1.0)
    r = r.reshape(-1, 1, 1)
    a = a[None, :, :]
    b = b[None, :, :]
    return 1000.0 * (a + b * r - 1.0)


def vmi_stack(
    water_density: np.ndarray,
    iodine_density: np.ndarray,
    energies_kev: tuple[int, ...] = VMI_GRID_KEV,
) -> np.ndarray:
    """VMI cube with the energy axis first: (n_energy, n_y, n_x)."""
    return vmi_hu(water_density, iodine_density, np.asarray(energies_kev, dtype=np.float64))
