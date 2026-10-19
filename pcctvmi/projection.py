"""Least-squares projection of a VMI stack onto the 2-basis spectral manifold.

A virtual monoenergetic image is, by construction, exactly a 2-parameter
family in energy:

    V(k) = 1000 * (a + b * r_k - 1),   r_k = mu_i(E_k) / mu_w(E_k)

with ``a`` the water density and ``b`` the iodine density at that pixel.
:func:`fit_basis` inverts this per pixel by solving the 2x2 normal equations
in closed form, giving a quantitation path that works on *any* VMI stack —
including denoised ones whose two-bin origin has been processed away.
:func:`basis_residual` is the RMS of the component the 2 bases cannot
explain; it is the Sprint-3 subsidiary metric (PROTOCOL_FREEZE.md S3-8/S3-9).
"""

from __future__ import annotations

import numpy as np

from pcctvmi.materials import mu_rho
from pcctvmi.vmi import VMI_GRID_KEV

__all__ = ["fit_basis", "basis_residual"]


def _r_values(energies_kev: np.ndarray) -> np.ndarray:
    return np.asarray(
        mu_rho("iodine", energies_kev) / mu_rho("water", energies_kev), dtype=np.float64
    )


def fit_basis(
    stack_hu: np.ndarray, energies_kev: tuple[float, ...] = VMI_GRID_KEV
) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel least-squares fit of a VMI stack to the 2-basis model.

    Parameters
    ----------
    stack_hu:
        VMI cube ``(n_energy, ny, nx)`` in HU.
    energies_kev:
        The keV level of each cube slice (defaults to the frozen grid).

    Returns
    -------
    (water_density, iodine_density):
        ``(ny, nx)`` each, in g/cm^3, from the closed-form 2x2 normal
        equations of the design matrix ``[1, r_k]`` against ``V(k)/1000 + 1``.

    Notes
    -----
    The design columns are ``[1, r_k]``; the Gram matrix
    ``[[n, sum r], [sum r, sum r^2]]`` has determinant ``n sum r^2 - (sum r)^2``
    which is positive for any grid containing two distinct r values (i.e.
    energies where the iodine/water attenuation ratio differs) — guaranteed on
    the frozen grid, which spans the iodine K edge. The solution is therefore
    unique and is computed directly, without a solver.
    """
    v = np.asarray(stack_hu, dtype=np.float64)
    if v.ndim != 3:
        raise ValueError(f"stack_hu must be (n_energy, ny, nx), got {v.shape}")
    r = _r_values(np.asarray(energies_kev, dtype=np.float64))
    if r.shape[0] != v.shape[0]:
        raise ValueError(f"{v.shape[0]} VMI slices but {r.shape[0]} energies were given")
    y = v / 1000.0 + 1.0  # (n_energy, ny, nx)
    n = float(r.size)
    s_r = float(r.sum())
    s_rr = float(r @ r)
    det = n * s_rr - s_r * s_r
    if det <= 0.0:
        raise ValueError(
            "degenerate energy grid: the 2-basis fit needs two distinct "
            "iodine/water attenuation ratios"
        )
    # Normal equations: [n, s_r; s_r, s_rr] @ [a; b] = [sum y; sum r y]
    s_y = y.sum(axis=0)  # (ny, nx)
    s_ry = (r[:, None, None] * y).sum(axis=0)
    a = (s_rr * s_y - s_r * s_ry) / det
    b = (n * s_ry - s_r * s_y) / det
    return a, b


def basis_residual(
    stack_hu: np.ndarray,
    energies_kev: tuple[float, ...] = VMI_GRID_KEV,
) -> np.ndarray:
    """Per-pixel RMS of the component the 2 bases cannot explain, in HU.

    ``sqrt(mean_k (V(k) - 1000(a + b r_k - 1))^2)`` for the per-pixel fit —
    zero to rounding for any stack that is exactly 2-basis (e.g. synthesized
    or noiseless), growing when a denoiser pushes VMI values off the
    2-basis manifold.
    """
    v = np.asarray(stack_hu, dtype=np.float64)
    a, b = fit_basis(v, energies_kev)
    r = _r_values(np.asarray(energies_kev, dtype=np.float64))
    model = 1000.0 * (a[None] + b[None] * r[:, None, None] - 1.0)
    return np.sqrt(np.mean((v - model) ** 2, axis=0))
