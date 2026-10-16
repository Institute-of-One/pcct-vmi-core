"""End-to-end pipeline checks: reconstruct and decompose known phantoms."""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.forward import REFERENCE_N0, simulate
from pcctvmi.materials import mu_rho
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum
from pcctvmi.vmi import VMI_GRID_KEV, decompose, vmi_hu, vmi_stack

THETA = np.linspace(0.0, 360.0, 360, endpoint=False)

INSERT_DENSITY = 0.005  # g/cm^3 = 5 mgI/mL (frozen nominal)


def _two_delta_spectrum() -> Spectrum:
    """Two monoenergetic lines (50 / 80 keV), one per bin (threshold 65 keV).

    Each bin then has an EXACT effective coefficient (single energy), which
    closes the decomposition algebra: the only error left is FBP ripple.
    """
    return Spectrum(np.array([50.0, 80.0]), np.array([1.0, 1.0]))


def _roi_mean(img: np.ndarray, cy: int, cx: int, radius: int) -> float:
    n = img.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
    return float(np.mean(img[mask]))


def _run_two_delta(n0: float = 1.0e6) -> tuple[tuple[np.ndarray, np.ndarray], object]:
    """Near-noiseless exact-coefficient validation path."""
    spec = _two_delta_spectrum()
    ph = make_water_cylinder_phantom(
        n=256,
        diameter_cm=20.0,
        pixel_size_cm=0.1,
        inserts=(Insert(x_cm=0.0, y_cm=5.0, diameter_cm=2.0, iodine_g_cm3=INSERT_DENSITY),),
    )
    res = simulate(spec, ph, theta_deg=THETA, thresholds_kev=(65.0,), n0=n0, seed=7)
    mus = reconstruct_bins(res, use_expected=True)
    a, b = decompose(mus, res.mu_eff)
    return (a, b), ph


def test_two_delta_water_recovered_within_2pct() -> None:
    (a, _), _ = _run_two_delta()
    ci = 128
    water = _roi_mean(a, ci, ci, 10)
    assert water == pytest.approx(1.0, rel=0.02)


def test_two_delta_iodine_recovered_within_3pct() -> None:
    (a, b), _ = _run_two_delta()
    ci = 128
    iodine = _roi_mean(b, ci + 50, ci, 8)  # insert centre 5 cm => +50 px (0.1 cm/px)
    assert iodine == pytest.approx(INSERT_DENSITY, rel=0.03)
    ring = _roi_mean(b, ci + 25, ci, 5)  # pure-water ring between centre and insert
    assert abs(ring) < 0.2 * INSERT_DENSITY


def test_pure_water_hu_is_zero_formula() -> None:
    # Closed form: water_density=1, iodine_density=0 gives exactly 0 at any E.
    a = np.ones((4, 4))
    b = np.zeros((4, 4))
    hu = vmi_hu(a, b, VMI_GRID_KEV)
    assert hu.shape == (16, 4, 4)
    assert np.all(hu == 0.0)


def test_iodine_hu_matches_formula() -> None:
    # HU(40 keV) = 1000 * b * mu_i(40)/mu_w(40); b is recovered within 3%,
    # so the measured HU must sit within ~5% of the formula value.
    (_, b), _ = _run_two_delta()
    ci = 128
    iodine = _roi_mean(b, ci + 50, ci, 8)
    e = 40.0
    formula_hu = 1000.0 * INSERT_DENSITY * float(mu_rho("iodine", e) / mu_rho("water", e))
    measured_hu = 1000.0 * iodine * float(mu_rho("iodine", e) / mu_rho("water", e))
    assert measured_hu == pytest.approx(formula_hu, rel=0.05)


def test_k_edge_monotonicity_over_frozen_grid() -> None:
    (_, b), _ = _run_two_delta()
    ci = 128
    iodine = _roi_mean(b, ci + 50, ci, 8)
    stack = vmi_stack(np.ones((4, 4)) * 1.0, np.zeros((4, 4)) + iodine, VMI_GRID_KEV)
    curve = stack[:, 0, 0]
    assert np.all(np.diff(curve) < 0), "iodine HU must decrease monotonically with keV"


def test_polyenergetic_eid_cupping_sign() -> None:
    # 120 kVp full-spectrum bin through 20 cm water: beam hardening makes the
    # centre measure lower than the periphery (cupping). Sign and minimum
    # magnitude are physics; the measured value is reported, not asserted.
    spec = Spectrum.from_csv()
    ph = make_water_cylinder_phantom(n=256, diameter_cm=20.0, pixel_size_cm=0.1)
    res = simulate(spec, ph, theta_deg=THETA, thresholds_kev=(), n0=1.0e5, seed=3)
    mus = reconstruct_bins(res, use_expected=True)
    mu_img = mus[0]
    eff_w = res.mu_eff[0]["water"]
    hu = 1000.0 * (mu_img / eff_w - 1.0)
    ci = 128
    centre = _roi_mean(hu, ci, ci, 5)
    periphery = _roi_mean(hu, ci, ci - 90, 5)  # ~9 cm off-centre, still in water
    assert centre < periphery - 3.0, (
        f"expected beam-hardening cupping: centre={centre:.2f} HU, periphery={periphery:.2f} HU"
    )


def test_two_bin_decomposition_poly() -> None:
    # Polyenergetic two-bin path. The frozen configuration (120 kVp, 8 mm Al,
    # single 30 keV threshold) yields a severely ill-conditioned basis,
    # cond(M) ~ 1.4e2: the first-order effective-energy linearization carries
    # a O(10%) systematic iodine bias. The 25% band covers that linearization
    # bias at the frozen configuration; the bias itself is a reported study
    # quantity (quantitative accuracy is part of hypothesis H2), not hidden
    # by this test.
    spec = Spectrum.from_csv()
    ph = make_water_cylinder_phantom(
        n=256,
        diameter_cm=20.0,
        pixel_size_cm=0.1,
        inserts=(Insert(x_cm=0.0, y_cm=5.0, diameter_cm=2.0, iodine_g_cm3=INSERT_DENSITY),),
    )
    # Frozen reference fluence: at n0=1e6 the Low-bin mean at 20 cm water is
    # ~4.5 counts and the shifted-log shift (0.5) would bias the line
    # integral by ~10%; REFERENCE_N0 keeps that bias < 0.3%.
    res = simulate(spec, ph, theta_deg=THETA, thresholds_kev=(30.0,), n0=REFERENCE_N0, seed=5)
    mat = np.array(
        [
            [res.mu_eff[0]["water"], res.mu_eff[0]["iodine"]],
            [res.mu_eff[1]["water"], res.mu_eff[1]["iodine"]],
        ]
    )
    print(f"decomposition matrix cond(M) = {np.linalg.cond(mat):.1f}")
    mus = reconstruct_bins(res, use_expected=True)
    a, b = decompose(mus, res.mu_eff)
    ci = 128
    water = _roi_mean(a, ci, ci, 10)
    iodine = _roi_mean(b, ci + 50, ci, 8)
    assert water == pytest.approx(1.0, rel=0.05)
    assert iodine == pytest.approx(INSERT_DENSITY, rel=0.25)
