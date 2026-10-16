"""Polyenergetic forward projection and detector signal simulation.

Photon economy (frozen, docs/PROTOCOL_FREEZE.md S1-6): the spectrum is
normalised to sum 1 inside ``simulate``; ``n0`` is therefore the mean number
of incident photons per detector element per projection, and the mean air
count of all bins together equals ``n0`` (photon conservation).

Two detector models:

- ``pcd`` (default): ideal photon-counting bins. Counts per bin are Poisson
  with mean ``n0 * sum_E w_E theta_bin(E) exp(-p_E)``; superposition makes
  the bin sum exactly Poisson.
- ``eid``: energy-integrating detector. The signal is the compound Poisson
  sum ``sum_E E * N_E`` with ``N_E ~ Poisson(n0 w_E exp(-p_E))``, sampled
  per energy. Its mean and noise statistics differ from the unweighted
  single-bin PCD; do not treat a 1-bin PCD as an EID.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from skimage.transform import radon

from pcctvmi.materials import mu_rho
from pcctvmi.phantom import Phantom
from pcctvmi.spectrum import Spectrum

DEFAULT_ANGLES_DEG = tuple(np.linspace(0.0, 360.0, 720, endpoint=False).tolist())
REFERENCE_N0 = 4.0e7  # frozen: see docs/PROTOCOL_FREEZE.md S1-6


@dataclass
class SimulationResult:
    """Noisy detector projections plus everything reconstruction needs."""

    counts: list[np.ndarray]  # per bin: (n_detector, n_angles)
    expected_counts: list[np.ndarray]  # per bin: noise-free means
    air_counts: np.ndarray  # per bin: mean signal at zero path
    theta_deg: np.ndarray
    thresholds_kev: tuple[float, ...]
    mu_eff: list[dict[str, float]]  # per bin effective mass attenuation coeffs
    reference_water_path_cm: float
    n0: float
    seed: int
    detector: str = "pcd"
    meta: dict = field(default_factory=dict)


def areal_density_projections(
    phantom: Phantom, theta_deg: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Basis-material areal density projections (g/cm^2).

    Uses skimage's radon transform with circular padding disabled so the
    detector length equals the grid size.
    """
    theta = np.asarray(theta_deg, dtype=np.float64)
    a_w = radon(phantom.water_density, theta=theta, circle=True) * phantom.pixel_size_cm
    a_i = radon(phantom.iodine_density, theta=theta, circle=True) * phantom.pixel_size_cm
    return a_w.astype(np.float64), a_i.astype(np.float64)


def simulate(
    spectrum: Spectrum,
    phantom: Phantom,
    theta_deg: np.ndarray | None = None,
    thresholds_kev: tuple[float, ...] = (30.0,),
    n0: float = REFERENCE_N0,
    seed: int = 0,
    detector: str = "pcd",
) -> SimulationResult:
    """Simulate detector projections with exact Poisson statistics.

    Args:
        spectrum: incident X-ray spectrum (relative fluence per keV; it is
            normalised inside, so ``n0`` is photons per detector element).
        phantom: digital phantom with known water/iodine densities.
        theta_deg: projection angles in degrees (default: 720 over 360 deg).
        thresholds_kev: PCD threshold(s). Empty tuple = single unweighted bin.
        n0: incident photons per detector element (scales linearly with mAs).
        seed: seed for the Poisson generator.
        detector: "pcd" (photon-counting bins) or "eid" (energy-integrating;
            requires ``thresholds_kev=()`` and yields float signal, not counts).

    Raises:
        ValueError: degenerate fluence (mean air signal < 100 in any bin),
            unknown detector, or EID with thresholds.
    """
    if n0 < 100:
        raise ValueError(
            f"n0={n0} gives <100 mean air counts; raise the fluence or the "
            "spectrum normalisation (degenerate input is rejected, not floored)"
        )
    if detector not in ("pcd", "eid"):
        raise ValueError(f"unknown detector {detector!r}")
    if detector == "eid" and len(thresholds_kev) != 0:
        raise ValueError("the EID model integrates the full spectrum; use thresholds_kev=()")
    if phantom.water_diameter_cm <= 0:
        raise ValueError("phantom meta missing water_diameter_cm")
    theta = (
        np.asarray(DEFAULT_ANGLES_DEG, dtype=np.float64)
        if theta_deg is None
        else np.asarray(theta_deg, dtype=np.float64)
    )
    a_w, a_i = areal_density_projections(phantom, theta)

    energies = spectrum.energies_kev
    mu_w = mu_rho("water", energies)
    mu_i = mu_rho("iodine", energies)
    # Normalised spectral weights: n0 is photons per detector element.
    weights = spectrum.normalized()
    if detector == "eid":
        w_e = spectrum.fluence * energies
        weights = w_e / w_e.sum()

    rng = np.random.default_rng(seed)
    counts: list[np.ndarray] = []
    expected: list[np.ndarray] = []
    air: list[float] = []

    if detector == "pcd":
        masks = spectrum.bin_masks(thresholds_kev)
        for mask in masks:
            exp_bin = np.zeros_like(a_w, dtype=np.float64)
            for e_idx in np.nonzero(mask)[0]:
                p = mu_w[e_idx] * a_w + mu_i[e_idx] * a_i  # line integral at energy E
                exp_bin += weights[e_idx] * np.exp(-p)
            exp_bin *= n0
            exp_counts = exp_bin.astype(np.float64)
            mean_air = float(n0 * weights[mask].sum())
            if mean_air < 100.0:
                raise ValueError("mean air counts < 100 in a bin; increase n0")
            air.append(mean_air)
            expected.append(exp_counts)
            counts.append(rng.poisson(exp_counts).astype(np.int64))
    else:  # eid: exact compound Poisson, sampled per energy
        signal = np.zeros_like(a_w, dtype=np.float64)
        exp_signal = np.zeros_like(a_w, dtype=np.float64)
        mean_air = float(n0 * weights.sum())
        if mean_air < 100.0:
            raise ValueError("mean air signal < 100; increase n0")
        for e_idx in range(spectrum.n_energies):
            p = mu_w[e_idx] * a_w + mu_i[e_idx] * a_i
            lam = n0 * weights[e_idx] * np.exp(-p)
            exp_signal += energies[e_idx] * lam
            signal += energies[e_idx] * rng.poisson(lam)
        air.append(mean_air)
        expected.append(exp_signal)
        counts.append(signal)

    # Mean chord length (pi/4 * D) as the transmission-weighting reference
    # path: the expectation value of the ray path through a convex body for
    # isotropic angles — an a-priori choice, not fitted to results.
    ref_path = np.pi / 4.0 * phantom.water_diameter_cm
    mu_eff = spectrum.effective_mu_rho(
        thresholds_kev, ref_path, energy_weighted=(detector == "eid")
    )

    return SimulationResult(
        counts=counts,
        expected_counts=expected,
        air_counts=np.asarray(air, dtype=np.float64),
        theta_deg=theta,
        thresholds_kev=tuple(thresholds_kev),
        mu_eff=mu_eff,
        reference_water_path_cm=ref_path,
        n0=float(n0),
        seed=int(seed),
        detector=detector,
        meta={
            "spectrum_energies_kev": energies.copy(),
            "fluence": weights.copy(),
            "pixel_size_cm": phantom.pixel_size_cm,
        },
    )
