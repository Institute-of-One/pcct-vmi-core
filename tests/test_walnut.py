"""Tests for the walnut-arm VMI/MD operators and ROI logic (S12.6/S12.7)."""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.noise_inject import NoiseModel
from pcctvmi.noise_inject import synthesize as synthesize_noise
from pcctvmi.walnut import (
    DM_WALNUT,
    VMI_COEF,
    VMI_GRID_KEV,
    flesh_mask,
    md_maps,
    md_rois,
    vmi_stack,
)


def test_dm_condition_number_matches_published() -> None:
    assert np.linalg.cond(DM_WALNUT) == pytest.approx(166.9, abs=0.1)


def test_vmi_coefficients_are_water_normalised() -> None:
    # Two-basis decomposition with water normalisation: cL + cH == 1 at
    # every keV level. A transposed/stale coefficient table breaks this.
    for _, c_l, c_h in VMI_COEF:
        assert c_l + c_h == pytest.approx(1.0, abs=1e-4)


def test_vmi_air_is_minus_1000() -> None:
    # Air: both bins at -1000 HU -> (a, b) = (0, 0) -> VMI = -1000 at any E.
    low = np.full((4, 4), -1000.0)
    high = np.full((4, 4), -1000.0)
    v = vmi_stack(low, high)
    assert v.shape == (len(VMI_GRID_KEV), 4, 4)
    assert np.all(v == pytest.approx(-1000.0))


def test_vmi_linear_map_matches_manual_assembly() -> None:
    # The frozen operator must equal its defining linear map pixelwise
    # (defect pinning: a swapped coefficient pair fails this).
    rng = np.random.default_rng(7)
    low = rng.uniform(-1000.0, 0.0, (32, 32))
    high = rng.uniform(-1000.0, 0.0, (32, 32))
    v = vmi_stack(low, high)
    for i, (_, c_l, c_h) in enumerate(VMI_COEF):
        manual = c_l * (low + 1000.0) + c_h * (high + 1000.0) - 1000.0
        assert np.allclose(v[i], manual, atol=1e-9)


def test_md_maps_are_dm_inverse_linear() -> None:
    rng = np.random.default_rng(11)
    low = rng.uniform(-1000.0, 0.0, (16, 16))
    high = rng.uniform(-1000.0, 0.0, (16, 16))
    pulp, shell = md_maps(low, high)
    dm_inv = np.linalg.inv(DM_WALNUT)
    x = np.stack([low + 1000.0, high + 1000.0])
    ref = np.einsum("ij,j...->i...", dm_inv, x) * 1000.0
    assert np.allclose(pulp, ref[0], atol=1e-6)
    assert np.allclose(shell, ref[1], atol=1e-6)
    # Round trip: synthesise bin images from known (pulp, shell), then the
    # maps must recover them (defect pinning: a transposed DM fails this).
    p0 = np.full((4, 4), 600.0)
    s0 = np.full((4, 4), 800.0)
    x = np.einsum("ij,j...->i...", DM_WALNUT, np.stack([p0 / 1000.0, s0 / 1000.0]))
    p1, s1 = md_maps(x[0] - 1000.0, x[1] - 1000.0)
    assert np.allclose(p1, p0, atol=1e-6)
    assert np.allclose(s1, s0, atol=1e-6)


def test_md_rois_select_anti_correlated_quadrants() -> None:
    # Synthetic 3-region map: left = pulp-rich (pulp 100, shell 0),
    # middle = both high (100, 100), right = shell-rich (pulp 0, shell 100).
    # Pulp ROI must be the left third, shell ROI the right third; the high
    # middle band is excluded ONLY by the secondary-material condition.
    n = 96
    _, xx = np.mgrid[0:n, 0:n]
    mask = np.ones((n, n), dtype=bool)
    pulp = np.where(xx < n // 3, 100.0, np.where(xx < 2 * n // 3, 100.0, 0.0)) + 1e-3 * xx
    shell = np.where(xx < n // 3, 0.0, np.where(xx < 2 * n // 3, 100.0, 100.0)) + 1e-3 * xx
    pr, sr = md_rois(pulp, shell, mask)
    assert pr.sum() > 0 and sr.sum() > 0
    assert pr[:, : n // 3].sum() == pr.sum()  # pulp ROI entirely in the left third
    assert sr[:, 2 * n // 3 :].sum() == sr.sum()  # shell ROI entirely in the right third
    assert not (pr & sr).any()
    # Defect pinning: dropping the secondary-material condition leaks both
    # ROIs into the opposite-rich middle band (the test data punishes it).
    pr_leak = pulp >= np.median(pulp[mask])
    sr_leak = shell >= np.median(shell[mask])
    assert pr_leak[:, n // 3 : 2 * n // 3].any(), "test data must punish the defect"
    assert sr_leak[:, n // 3 : 2 * n // 3].any(), "test data must punish the defect"


def test_flesh_mask_threshold() -> None:
    img = np.array([[-1000.0, -950.0, -899.0, -500.0]])
    m = flesh_mask(img)
    assert m.tolist() == [[False, False, True, True]]


def test_walnut_noise_model_injection_nps_within_5pct() -> None:
    """S12.7: injected noise NPS matches the frozen S12-4 target (< 5%)."""
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "results" / "walnut_noise_model_d0.25.npz"
    if not path.exists():
        pytest.skip("walnut noise model not generated yet")
    model = NoiseModel.load(path)
    rng = np.random.default_rng(5)
    reps = 512
    fields = np.stack([synthesize_noise(model, model.shape, rng) for _ in range(reps)])
    wl = np.fft.fft2(fields[:, 0], axes=(-2, -1))
    wh = np.fft.fft2(fields[:, 1], axes=(-2, -1))
    ny, nx = model.shape
    norm = model.spacing_mm**2 / (ny * nx)
    s_ll = norm * np.mean(np.abs(wl) ** 2, axis=0)
    s_hh = norm * np.mean(np.abs(wh) ** 2, axis=0)
    # Whole-grid relative error of the mean NPS (target is the frozen model).
    rel_ll = float(np.abs(s_ll - model.s_ll).mean() / model.s_ll.mean())
    rel_hh = float(np.abs(s_hh - model.s_hh).mean() / model.s_hh.mean())
    assert rel_ll < 0.05, f"Low NPS rel err {rel_ll:.3f}"
    assert rel_hh < 0.05, f"High NPS rel err {rel_hh:.3f}"


def test_d1w_weights_load_and_run() -> None:
    from pathlib import Path

    import torch

    from pcctvmi.denoiser import VMIDenoiser

    path = Path(__file__).resolve().parent.parent / "results" / "denoiser_d1w_weights.pt"
    if not path.exists():
        pytest.skip("D1w weights not trained yet")
    model = VMIDenoiser(n_channels=2)
    model.load_state_dict(torch.load(path, weights_only=True))
    model.eval()
    with torch.no_grad():
        x = torch.randn(1, 2, 64, 64)
        y = model(x)
    assert y.shape == x.shape
    assert torch.isfinite(y).all()
