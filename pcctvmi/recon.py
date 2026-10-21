"""Filtered back-projection of detector projections."""

from __future__ import annotations

import numpy as np
from skimage.transform import iradon

from pcctvmi.forward import SimulationResult

LOG_SHIFT = 0.5  # shifted-log linearisation for low-count projections


def linearize(counts: np.ndarray, air_counts: float, shift: float = LOG_SHIFT) -> np.ndarray:
    """Negative log transmission per detector element.

    Uses the shifted-log estimator ``log((c + shift) / air)``: zero counts
    are linearisable (no -inf), and for a Poisson mean mu the estimator bias
    is O(1/mu^2) — negligible at the frozen dose levels (mean counts >= ~5).
    Negative counts are physically impossible and raise.
    """
    c = np.asarray(counts, dtype=np.float64)
    if np.any(c < 0):
        raise ValueError("negative counts cannot be linearised")
    if air_counts <= 0:
        raise ValueError("air_counts must be positive")
    if shift <= 0:
        raise ValueError("shift must be positive")
    return -np.log((c + shift) / air_counts)


def fbp(line_integrals: np.ndarray, theta_deg: np.ndarray, filter_name: str = "hann") -> np.ndarray:
    """FBP reconstruction (circular FOV, detector length = grid size)."""
    y = np.asarray(line_integrals, dtype=np.float64)
    if y.ndim != 2:
        raise ValueError("line_integrals must be 2-D (n_detector, n_angles)")
    img = iradon(
        y, theta=np.asarray(theta_deg, dtype=np.float64), filter_name=filter_name, circle=True
    )
    return img.astype(np.float64)


def reconstruct_bins(
    result: SimulationResult,
    use_expected: bool = False,
    filter_name: str = "hann",
    bin_indices: list[int] | tuple[int, ...] | None = None,
) -> list[np.ndarray]:
    """Reconstruct every bin into a linear-attenuation image (1/cm).

    skimage's ``iradon`` inverts the unit-pixel-area line sum, so the output
    carries an extra factor of the pixel size; dividing by ``pixel_size_cm``
    restores 1/cm. The pixel size is carried through ``SimulationResult.meta``
    from the phantom, so reconstruction stays consistent with the forward
    model by construction.

    Args:
        result: simulation output.
        use_expected: linearise the noise-free means instead of the noisy
            counts (validation path; deterministic given the phantom).
        filter_name: FBP filter.
        bin_indices: optional subset of bin indices to reconstruct (the
            walnut config's 3-bin simulations skip the hardware-rejected
            sub-15 keV bin via ``bin_indices=(1, 2)``). None = all bins.
    """
    pixel_size_cm = float(result.meta["pixel_size_cm"])
    idxs = range(len(result.counts)) if bin_indices is None else bin_indices
    images: list[np.ndarray] = []
    for idx in idxs:
        data = result.expected_counts[idx] if use_expected else result.counts[idx]
        y = linearize(np.asarray(data, dtype=np.float64), float(result.air_counts[idx]))
        images.append(fbp(y, result.theta_deg, filter_name=filter_name) / pixel_size_cm)
    return images
