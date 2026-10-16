"""Sprint-1 physics/statistics audit tests (independent of the pipeline tests).

Verifies photon conservation, Poisson statistics, the shifted-log estimator,
and the PCD/EID distinction — the properties a denoising study stands on.
"""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.forward import REFERENCE_N0, simulate
from pcctvmi.phantom import make_water_cylinder_phantom
from pcctvmi.recon import LOG_SHIFT
from pcctvmi.spectrum import Spectrum

THETA = np.linspace(0.0, 360.0, 180, endpoint=False)


def _phantom(n: int = 256, diameter_cm: float = 20.0):
    return make_water_cylinder_phantom(n=n, diameter_cm=diameter_cm, pixel_size_cm=0.1)


def test_photon_conservation_across_bins() -> None:
    # n0 is the mean number of incident photons per detector element: the
    # bins partition the spectrum, so their air means must sum to exactly n0.
    spec = Spectrum.from_csv()
    res = simulate(spec, _phantom(), theta_deg=THETA, thresholds_kev=(30.0,), n0=1.0e7, seed=0)
    assert float(res.air_counts.sum()) == pytest.approx(1.0e7, rel=1e-12)


def test_photon_conservation_single_bin_equals_n0() -> None:
    spec = Spectrum.from_csv()
    res = simulate(spec, _phantom(), theta_deg=THETA, thresholds_kev=(), n0=5.0e6, seed=0)
    assert float(res.air_counts[0]) == pytest.approx(5.0e6, rel=1e-12)


def test_poisson_statistics_global_z_scores() -> None:
    # Independent Poisson check: over the whole sinogram, (c - mu)/sqrt(mu)
    # must have mean ~ 0 and variance ~ 1 (SE = 1/sqrt(N) and sqrt(2/N)).
    # circle=True leaves no air rows in the sinogram, so use the expected
    # field as the reference for every element with mu >= 100.
    spec = Spectrum.from_csv()
    res = simulate(spec, _phantom(), theta_deg=THETA, thresholds_kev=(30.0,), n0=1.0e6, seed=11)
    for idx in range(2):
        mu = res.expected_counts[idx]
        c = res.counts[idx].astype(np.float64)
        mask = mu >= 100.0
        z = (c[mask] - mu[mask]) / np.sqrt(mu[mask])
        n = int(z.size)
        assert float(z.mean()) == pytest.approx(0.0, abs=5.0 / np.sqrt(n))
        assert float(z.var()) == pytest.approx(1.0, rel=0.03)


def test_reference_n0_keeps_low_bin_usable_at_lowest_dose() -> None:
    # Frozen criterion: at the 25% dose level the mean Low-bin count at the
    # longest water path (25 cm) stays >= 5, keeping shifted-log bias small.
    spec = Spectrum.from_csv()
    ph = make_water_cylinder_phantom(n=256, diameter_cm=25.0, pixel_size_cm=0.1)
    res = simulate(
        spec,
        ph,
        theta_deg=np.array([0.0]),
        thresholds_kev=(30.0,),
        n0=0.25 * REFERENCE_N0,
        seed=0,
    )
    ci = 128
    assert float(res.expected_counts[0][ci, 0]) >= 5.0


def test_shifted_log_bias_negligible_at_reference_counts() -> None:
    # E[log(Pois(mu) + 0.5)] ~= log(mu) for the count levels the frozen dose
    # levels produce. Fixed seed -> deterministic Monte-Carlo check.
    rng = np.random.default_rng(123)
    for mu in (5.0, 100.0, 1000.0):
        sample = rng.poisson(mu, size=200_000)
        est = float(np.log(sample + LOG_SHIFT).mean())
        assert est == pytest.approx(float(np.log(mu)), abs=0.02)


def test_eid_differs_from_unweighted_single_bin_pcd() -> None:
    # Energy integration weights transmitted (harder) photons more, so the
    # EID centre signal exceeds the unweighted 1-bin PCD signal through the
    # same water path, and its effective water coefficient is lower.
    # The EID/PCD signal ratio equals the closed-form transmitted-photon
    # mean energy sum(E w e^-p)/sum(w e^-p) — consistency, not a hard-coded
    # threshold.
    spec = Spectrum.from_csv()
    ph = _phantom()
    pcd = simulate(spec, ph, theta_deg=np.array([0.0]), thresholds_kev=(), n0=1.0e7, seed=0)
    eid = simulate(
        spec, ph, theta_deg=np.array([0.0]), thresholds_kev=(), n0=1.0e7, seed=0, detector="eid"
    )
    ci = 128
    centre_pcd = float(pcd.expected_counts[0][ci, 0])
    centre_eid = float(eid.expected_counts[0][ci, 0])
    assert centre_eid > centre_pcd
    assert eid.mu_eff[0]["water"] < pcd.mu_eff[0]["water"]
    w = spec.normalized()
    e = spec.energies_kev
    from pcctvmi.materials import mu_rho

    p = mu_rho("water", e) * 20.0  # 20 cm water at the centre ray
    w_e = spec.fluence * e
    w_e = w_e / w_e.sum()  # EID detection weights (energy-integrating)
    ratio_theory = float((w_e * e * np.exp(-p)).sum() / (w * np.exp(-p)).sum())
    assert centre_eid / centre_pcd == pytest.approx(ratio_theory, rel=1e-6)


def test_eid_compound_poisson_variance() -> None:
    # Var(EID signal) = sum_E E^2 lambda_E (compound Poisson). The
    # variance/mean ratio therefore equals the closed-form spectral
    # quantity sum(E^2 w)/sum(E w) — computed here from the spectrum
    # itself, not hard-coded.
    spec = Spectrum.from_csv()
    w = spec.normalized()
    e = spec.energies_kev
    ratio_theory = float((w * e**2).sum() / (w * e).sum())
    ph = _phantom()
    res = simulate(spec, ph, theta_deg=THETA, thresholds_kev=(), n0=1.0e5, seed=3, detector="eid")
    col = res.counts[0][-3, :].astype(np.float64)
    var_hat = float(col.var())
    mean_hat = float(col.mean())
    assert var_hat / mean_hat == pytest.approx(ratio_theory, rel=0.10)


def test_eid_rejects_thresholds() -> None:
    spec = Spectrum.from_csv()
    with pytest.raises(ValueError):
        simulate(spec, _phantom(), theta_deg=THETA, thresholds_kev=(30.0,), detector="eid")
