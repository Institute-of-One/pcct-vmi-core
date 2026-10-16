"""Closed-form checks for phantom construction and the forward model."""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.forward import areal_density_projections, simulate
from pcctvmi.materials import mu_rho
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.spectrum import Spectrum

THETA_SMALL = np.linspace(0.0, 360.0, 180, endpoint=False)


def _center_index(n: int) -> int:
    return n // 2


def test_phantom_known_values() -> None:
    ph = make_water_cylinder_phantom(
        n=128,
        diameter_cm=12.0,
        pixel_size_cm=0.1,
        inserts=(Insert(x_cm=0.0, y_cm=3.0, diameter_cm=1.0, iodine_g_cm3=0.005),),
    )
    assert ph.shape == (128, 128)
    assert ph.water_diameter_cm == 12.0
    ci = _center_index(128)
    assert ph.water_density[ci, ci] == pytest.approx(1.0)
    assert ph.iodine_density[ci, ci] == 0.0
    # insert centre: 3 cm below centre => row index centre + 30 pixels
    assert ph.iodine_density[ci + 30, ci] == pytest.approx(0.005)
    # outside the water body: zero
    assert ph.water_density[2, 2] == 0.0
    assert ph.iodine_density[2, 2] == 0.0


def test_phantom_insert_outside_water_rejected() -> None:
    with pytest.raises(ValueError):
        make_water_cylinder_phantom(
            n=128,
            diameter_cm=12.0,
            pixel_size_cm=0.1,
            inserts=(Insert(x_cm=0.0, y_cm=5.9, diameter_cm=1.0, iodine_g_cm3=0.005),),
        )


def test_phantom_negative_density_rejected() -> None:
    with pytest.raises(ValueError):
        make_water_cylinder_phantom(
            n=64,
            diameter_cm=5.0,
            pixel_size_cm=0.1,
            inserts=(Insert(0.0, 0.0, 1.0, -0.001),),
        )


def test_areal_projection_center_closed_form() -> None:
    # Uniform disk of diameter D at density rho: the areal density through
    # the centre ray is exactly rho * D.
    ph = make_water_cylinder_phantom(n=256, diameter_cm=20.0, pixel_size_cm=0.1)
    theta = np.array([0.0])
    a_w, _ = areal_density_projections(ph, theta)
    ci = _center_index(256)
    expected = 1.0 * 20.0  # g/cm^2
    # radon places the FOV centre at row index n//2
    assert float(a_w[ci, 0]) == pytest.approx(expected, rel=0.01)


def test_forward_air_and_centre_closed_form() -> None:
    # Monoenergetic 60 keV, 20 cm water: mean counts at the centre detector
    # element must be n0 * exp(-mu_w(60) * 20), and air counts exactly n0.
    e0 = 60.0
    n0 = 1.0e5
    spec = Spectrum.mono(e0)
    ph = make_water_cylinder_phantom(n=256, diameter_cm=20.0, pixel_size_cm=0.1)
    res = simulate(spec, ph, theta_deg=THETA_SMALL, thresholds_kev=(), n0=n0, seed=1)
    assert len(res.counts) == 1
    assert float(res.air_counts[0]) == pytest.approx(n0, rel=1e-6)
    expected = res.expected_counts[0]
    ci = _center_index(256)
    formula = n0 * float(np.exp(-mu_rho("water", e0) * 20.0))
    assert float(expected[ci, 0]) == pytest.approx(formula, rel=1e-3)


def test_forward_degenerate_n0_rejected() -> None:
    spec = Spectrum.mono(60.0)
    ph = make_water_cylinder_phantom(n=64, diameter_cm=5.0, pixel_size_cm=0.1)
    with pytest.raises(ValueError):
        simulate(spec, ph, theta_deg=THETA_SMALL, thresholds_kev=(), n0=10.0, seed=0)


def test_linearize_negative_counts_rejected() -> None:
    from pcctvmi.recon import linearize

    with pytest.raises(ValueError):
        linearize(np.array([[-1.0, 1.0]]), air_counts=1.0e5)


def test_linearize_zero_counts_finite() -> None:
    # Shifted-log policy: zero counts must linearise to a finite value.
    from pcctvmi.recon import linearize

    y = linearize(np.array([[0.0]]), air_counts=1.0e5)
    assert np.all(np.isfinite(y))
