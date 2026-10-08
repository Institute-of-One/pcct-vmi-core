"""Closed-form checks for the material table and spectrum model."""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.materials import MATERIALS, energies_kev, mu_rho
from pcctvmi.spectrum import Spectrum

XCOM_WATER_60KEV = 0.2059  # cm^2/g, NIST XCOM reference value


def test_water_mu_rho_matches_xcom_reference() -> None:
    # Expectation written from the external standard, not from a snapshot of
    # our own output.
    value = float(mu_rho("water", 60.0))
    assert value == pytest.approx(XCOM_WATER_60KEV, rel=0.02)


def test_iodine_k_edge_jump() -> None:
    # Iodine K edge at 33.2 keV: attenuation just above must exceed the
    # just-below value by more than 2x (photoelectric discontinuity).
    below = float(mu_rho("iodine", 33.0))
    above = float(mu_rho("iodine", 34.0))
    assert above > 2.0 * below


def test_unknown_material_rejected() -> None:
    with pytest.raises(ValueError):
        mu_rho("lead", 60.0)


def test_energy_out_of_range_rejected() -> None:
    with pytest.raises(ValueError):
        mu_rho("water", 250.0)


def test_table_grid_is_contiguous_1kev() -> None:
    grid = energies_kev()
    assert grid[0] == 10.0
    assert grid[-1] == 200.0
    assert np.all(np.diff(grid) == 1.0)


def test_all_materials_positive() -> None:
    grid = energies_kev()
    for m in MATERIALS:
        assert np.all(mu_rho(m, grid) > 0)


def test_spectrum_from_csv_properties() -> None:
    spec = Spectrum.from_csv()
    assert spec.n_energies > 50
    assert spec.min_energy_kev >= 10.0
    assert spec.max_energy_kev <= 120.0
    assert np.all(spec.fluence >= 0)
    assert 0.99 < float(spec.normalized().sum()) < 1.01


def test_spectrum_bin_masks_partition() -> None:
    spec = Spectrum.from_csv()
    masks = spec.bin_masks((30.0,))
    assert len(masks) == 2
    union = np.zeros(spec.n_energies, dtype=bool)
    for m in masks:
        assert m.any(), "empty bin"
        assert not np.any(union & m), "bins overlap"
        union |= m
    assert union.all()


def test_spectrum_validation() -> None:
    with pytest.raises(ValueError):
        Spectrum(np.array([10.0, 20.0]), np.array([0.0, 0.0]))
    with pytest.raises(ValueError):
        Spectrum(np.array([20.0, 10.0]), np.array([1.0, 1.0]))
    with pytest.raises(ValueError):
        Spectrum.mono(-5.0)


def test_effective_coefficients_between_mono_extremes() -> None:
    # Transmission weighting must give an effective coefficient inside the
    # range spanned by the bin's monoenergetic values.
    spec = Spectrum.from_csv()
    eff = spec.effective_mu_rho((30.0,), reference_water_path_cm=20.0)
    assert len(eff) == 2
    for k, mask in enumerate(spec.bin_masks((30.0,))):
        for material in ("water", "iodine"):
            mono_vals = np.array([mu_rho(material, e) for e in spec.energies_kev[mask]])
            assert eff[k][material] <= mono_vals.max() * 1.0001
            assert eff[k][material] >= mono_vals.min() * 0.9999
