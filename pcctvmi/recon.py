"""Filtered back-projection of photon-counting bin projections."""

from __future__ import annotations

import numpy as np
from skimage.transform import iradon

from pcctvmi.forward import SimulationResult


def linearize(counts: np.ndarray, air_counts: float) -> np.ndarray:
    """Negative log transmission per detector element.

    Zero counts would give +inf; the forward model's air-count guard
    (mean air counts >= 100) makes a zero count astronomically unlikely for
    any realistic water path, but we still raise rather than floor silently.
    """
    c = np.asarray(counts, dtype=np.float64)
    if np.any(c <= 0):
        raise ValueError("zero or negative counts cannot be linearised; raise n0")
    if air_counts <= 0:
        raise ValueError("air_counts must be positive")
    return -np.log(c / air_counts)


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
    result: SimulationResult, use_expected: bool = False, filter_name: str = "hann"
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
    """
    pixel_size_cm = float(result.meta["pixel_size_cm"])
    images: list[np.ndarray] = []
    for idx in range(len(result.counts)):
        data = result.expected_counts[idx] if use_expected else result.counts[idx]
        y = linearize(np.asarray(data, dtype=np.float64), float(result.air_counts[idx]))
        images.append(fbp(y, result.theta_deg, filter_name=filter_name) / pixel_size_cm)
    return images
