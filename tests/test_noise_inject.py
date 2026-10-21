"""Tests for pcctvmi.noise_inject (PROTOCOL_FREEZE.md S12-7).

The acceptance criterion is statistical: the synthesised noise must
reproduce the model NPS (auto, per channel) and cross-spectrum within
ensemble tolerance, measured with the same estimator and ROI geometry as
the model itself (observers.nps_2d convention).

Known-defect pinning (AGENTS.md §7): the reproduction measurement must
DISCRIMINATE — the same synthesised noise must mismatch a scaled target
(2x spectrum), so a broken or mis-scaled synthesiser cannot pass silently.
"""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.noise_inject import NoiseModel, synthesize

SPACING = 0.05  # mm, walnut-matched pitch
GRID = 64  # small model grid keeps the test fast; synthesize tiles it
ROIS_PER_DRAW = 16  # 4x4 tiles
N_DRAWS = 8  # independent draws -> 128 ROIs for the ensemble estimate


def _flat_model(sigma_hu: float, rho: float = 0.0) -> NoiseModel:
    white = (sigma_hu**2) * SPACING * SPACING
    s_ll = np.full((GRID, GRID), white)
    s_hh = np.full((GRID, GRID), white * 4.0)  # High channel noisier
    amp = np.sqrt(s_ll * s_hh)
    if rho != 0.0:
        # Hermitian-valid complex cross-spectrum: a REAL correlation
        # coefficient times a linear phase (= integer-pixel cross-channel
        # shift, DFT shift property). The phase is what makes individual
        # bins complex; a constant complex rho would violate s[-f]=conj(s[f])
        # and is rejected by the model validation on purpose.
        ku = np.fft.fftfreq(GRID) * GRID  # integer fft bin indices
        kv = np.fft.fftfreq(GRID) * GRID
        phase = np.exp(2j * np.pi * (ku[None, :] * 1 + kv[:, None] * 2) / GRID)
        s_lh = rho * amp * phase
    else:
        s_lh = np.zeros((GRID, GRID))
    return NoiseModel(s_ll=s_ll, s_hh=s_hh, s_lh=s_lh, spacing_mm=SPACING)


def _ensemble_spectra(
    model: NoiseModel, seed: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Independent draws, tiled, stacked into ROIs; DFT-product spectral estimates."""
    s_ll_acc: np.ndarray | None = None
    s_hh_acc: np.ndarray | None = None
    s_lh_acc: np.ndarray | None = None
    resid_all = []
    tiles_y = tiles_x = int(np.sqrt(ROIS_PER_DRAW))
    for draw in range(N_DRAWS):
        rng = np.random.default_rng(seed + draw)
        big = synthesize(model, (tiles_y * GRID, tiles_x * GRID), rng)
        rois = big.reshape(2, tiles_y, GRID, tiles_x, GRID).transpose(0, 1, 3, 2, 4)
        rois = rois.reshape(2, ROIS_PER_DRAW, GRID, GRID)
        resid = rois - rois.mean(axis=(-2, -1), keepdims=True)
        resid_all.append(resid)
        wl = np.fft.fft2(resid[0], axes=(-2, -1))
        wh = np.fft.fft2(resid[1], axes=(-2, -1))
        norm = SPACING * SPACING / (GRID * GRID)
        a = norm * np.mean(np.abs(wl) ** 2, axis=0)
        b = norm * np.mean(np.abs(wh) ** 2, axis=0)
        c = norm * np.mean(wl * np.conj(wh), axis=0)
        s_ll_acc = a if s_ll_acc is None else s_ll_acc + a
        s_hh_acc = b if s_hh_acc is None else s_hh_acc + b
        s_lh_acc = c if s_lh_acc is None else s_lh_acc + c
    n = N_DRAWS
    resid = np.concatenate(resid_all, axis=1)
    assert s_ll_acc is not None and s_hh_acc is not None and s_lh_acc is not None
    return s_ll_acc / n, s_hh_acc / n, s_lh_acc / n, resid


def test_model_validation() -> None:
    white = np.ones((GRID, GRID))
    with pytest.raises(ValueError):
        NoiseModel(s_ll=-white, s_hh=white, s_lh=white, spacing_mm=SPACING)
    with pytest.raises(ValueError):
        NoiseModel(s_ll=white, s_hh=white, s_lh=white, spacing_mm=-1.0)
    bad_cross = np.ones((GRID, GRID)) * (1 + 1j)  # not Hermitian
    with pytest.raises(ValueError):
        NoiseModel(s_ll=white, s_hh=white, s_lh=bad_cross, spacing_mm=SPACING)
    m = NoiseModel(s_ll=white, s_hh=white, s_lh=np.zeros((GRID, GRID)), spacing_mm=SPACING)
    assert m.shape == (GRID, GRID)


def test_auto_nps_reproduction() -> None:
    model = _flat_model(sigma_hu=30.0)
    s_ll, s_hh, _, resid = _ensemble_spectra(model, seed=1)
    for s, target in ((s_ll, model.s_ll), (s_hh, model.s_hh)):
        rel = np.abs(s - target) / target
        assert np.median(rel) < 0.12, f"median rel err {np.median(rel):.3f}"
    sd0 = resid[0].std(axis=(-2, -1)).mean()
    sd1 = resid[1].std(axis=(-2, -1)).mean()
    assert abs(sd0 - 30.0) / 30.0 < 0.05
    assert abs(sd1 - 60.0) / 60.0 < 0.05


def test_reproduction_discriminates_scaled_target() -> None:
    """Known-defect pinning: the measurement must FAIL against a 2x-scaled target."""
    model = _flat_model(sigma_hu=30.0)
    s_ll, _, _, _ = _ensemble_spectra(model, seed=5)
    rel = np.abs(s_ll - 4.0 * model.s_ll) / (4.0 * model.s_ll)
    assert np.median(rel) > 0.5, "measurement does not discriminate a 2x spectrum error"


def test_cross_spectrum_reproduction() -> None:
    rho = 0.3  # real correlation; the (1, 2)-pixel shift supplies the complex phase
    model = _flat_model(sigma_hu=30.0, rho=rho)
    s_ll, s_hh, s_lh, _ = _ensemble_spectra(model, seed=2)
    ku = np.fft.fftfreq(GRID) * GRID
    kv = np.fft.fftfreq(GRID) * GRID
    phase = np.exp(2j * np.pi * (ku[None, :] * 1 + kv[:, None] * 2) / GRID)
    rho_hat = s_lh / np.sqrt(s_ll * s_hh) * np.conj(phase)
    err = np.abs(rho_hat - rho)
    assert np.median(err) < 0.08, f"median |rho_hat - rho| = {np.median(err):.3f}"


def test_psd_cone_clipping() -> None:
    """A cross-spectrum outside the PSD cone (|rho| > 1) must be clipped, not crash."""
    white = np.full((GRID, GRID), (30.0**2) * SPACING * SPACING)
    s_lh = white * 4.0  # |rho| = 4 / sqrt(1*4) = 2 > 1
    model = NoiseModel(s_ll=white, s_hh=white * 4.0, s_lh=s_lh, spacing_mm=SPACING)
    rng = np.random.default_rng(3)
    noise = synthesize(model, (GRID * 2, GRID * 2), rng)
    assert np.all(np.isfinite(noise))
    wl = np.fft.fft2(noise[0])
    wh = np.fft.fft2(noise[1])
    norm = SPACING * SPACING / (noise.shape[1] * noise.shape[2])
    cross = norm * np.mean(wl * np.conj(wh))
    auto = norm * np.mean(np.abs(wl) ** 2)
    auto_h = norm * np.mean(np.abs(wh) ** 2)
    assert abs(cross) / np.sqrt(auto * auto_h) <= 1.0 + 0.1


def test_determinism() -> None:
    model = _flat_model(sigma_hu=10.0, rho=0.5)
    a = synthesize(model, (GRID * 2, GRID * 2), np.random.default_rng(7))
    b = synthesize(model, (GRID * 2, GRID * 2), np.random.default_rng(7))
    np.testing.assert_array_equal(a, b)


def test_shape_smaller_than_model_rejected() -> None:
    model = _flat_model(sigma_hu=1.0)
    with pytest.raises(ValueError):
        synthesize(model, (GRID // 2, GRID), np.random.default_rng(0))
