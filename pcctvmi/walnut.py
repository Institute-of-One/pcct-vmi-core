"""Walnut real-data arm (H4): the system's VMI/MD operators and ROI logic.

The walnut scanner's VMI is EXACTLY linear in the bin images
(verified 2026-10-21 against the dataset's own VirtualMonoImg DICOMs,
R^2 >= 0.9999988 at all 8 keV levels, slice-to-slice coefficient drift
< 2.1e-3): VMI(E) = cL(E)*(Low+1000) + cH(E)*(High+1000) - 1000. The
per-keV coefficients below are that regression, frozen. cL+cH = 1 at every
level (two-basis decomposition with water normalisation), which the tests
pin.

The reference material decomposition (MD) is computed with the published
WalnutMDTable matrix (PROTOCOL_FREEZE.md §12.1: the dataset's own
MD_Pulp_Shell series is inconsistent with every linear map of the provided
bin images — dataset-side drift — so the reference MD is self-computed):

    [Pulp; Shell] = DM^-1 @ [Low+1000; High+1000] * 1000     (mg/cm^3-scale)

with cond(DM) = 166.88 (measured, matches the published 166.9).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "VMI_COEF",
    "VMI_GRID_KEV",
    "DM_WALNUT",
    "flesh_mask",
    "vmi_stack",
    "md_maps",
    "md_rois",
]

#: Frozen VMI operator coefficients, measured 2026-10-21 by regressing the
#: dataset's VirtualMonoImg (Walnut_1, slice 530) on (Low+1000, High+1000).
#: R^2 >= 0.9999988 at every level; slice 500/559 coefficient drift < 2.1e-3.
#: (keV, cL, cH)
VMI_COEF: tuple[tuple[float, float, float], ...] = (
    (10.0, 3.484588, -2.484586),
    (20.0, 2.921757, -1.921757),
    (30.0, 1.389459, -0.389439),
    (40.0, 0.299314, 0.700676),
    (50.0, -0.296628, 1.296628),
    (60.0, -0.622059, 1.622064),
    (70.0, -0.808229, 1.808230),
    (80.0, -0.920806, 1.920815),
)

#: Evaluation keV grid (§12.6): 10-80 keV, 10 keV steps.
VMI_GRID_KEV: tuple[float, ...] = tuple(c[0] for c in VMI_COEF)

#: Published WalnutMDTable decomposition matrix (rows: Low, High;
#: columns: pulp, shell). cond = 166.88 (measured; published 166.9).
DM_WALNUT = np.array([[784.34, 890.25], [1025.52, 1135.36]])

_DM_INV = np.linalg.inv(DM_WALNUT)


def flesh_mask(low_hu: np.ndarray, threshold: float = -900.0) -> np.ndarray:
    """Tissue mask from a bin image: HU above the air threshold."""
    return np.asarray(low_hu, dtype=np.float64) > threshold


def vmi_stack(low_hu: np.ndarray, high_hu: np.ndarray) -> np.ndarray:
    """VMI at the frozen keV grid. Returns (n_kev, ny, nx) HU."""
    low = np.asarray(low_hu, dtype=np.float64)
    high = np.asarray(high_hu, dtype=np.float64)
    xl = low + 1000.0
    xh = high + 1000.0
    out = np.empty((len(VMI_COEF),) + low.shape, dtype=np.float64)
    for i, (_, c_l, c_h) in enumerate(VMI_COEF):
        out[i] = c_l * xl + c_h * xh - 1000.0
    return out


def md_maps(low_hu: np.ndarray, high_hu: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reference material decomposition. Returns (pulp, shell), mg/cm^3-scale."""
    low = np.asarray(low_hu, dtype=np.float64)
    high = np.asarray(high_hu, dtype=np.float64)
    x = np.stack([low + 1000.0, high + 1000.0], axis=0)
    ab = np.einsum("ij,j...->i...", _DM_INV, x) * 1000.0
    return ab[0], ab[1]


def md_rois(
    pulp_ref: np.ndarray,
    shell_ref: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Pulp/shell ROIs from the REFERENCE MD maps (§12.6 definition).

    pulp ROI: reference pulp in the upper half of its masked distribution
    AND reference shell in the lower quartile of its. shell ROI: same shape
    with the roles swapped. ``mask`` is the search region — per §12.6 the
    "slice central region" of the flesh (caller supplies flesh & central).
    """
    pulp = np.asarray(pulp_ref, dtype=np.float64)[mask]
    shell = np.asarray(shell_ref, dtype=np.float64)[mask]
    p_med = float(np.median(pulp))
    s_med = float(np.median(shell))
    p_q1 = float(np.quantile(pulp, 0.25))
    s_q1 = float(np.quantile(shell, 0.25))
    pr = np.zeros(mask.shape, dtype=bool)
    sr = np.zeros(mask.shape, dtype=bool)
    pr[mask] = (pulp >= p_med) & (shell <= s_q1)
    sr[mask] = (shell >= s_med) & (pulp <= p_q1)
    return pr, sr
