"""Closed-form and Monte-Carlo tests for the ported model observers (Sprint 2).

Every expectation is a formula evaluated in the test, not a recorded constant:
the white-noise identity ``d' = ||s||/sigma``, the Parseval identity
``int NPS = sigma^2``, the white-noise equivalence of NPW and the ideal
observer, and the Monte-Carlo agreement of the empirical score-based d' with
the closed form. See docs/PROTOCOL_FREEZE.md §7 (S2 freeze).
"""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.observers import (
    auc_from_scores,
    burgess_eye_filter,
    d_prime_from_scores,
    ideal_linear,
    nps_2d,
    npwe,
    score_images,
)

SPACING = 0.5  # mm — the frozen 0.05 cm/px phantom pitch (S2-1 conversion)
SEED = 20261017  # S2-7 seed base


def _blob(shape: tuple[int, int] = (32, 32), spacing: float = SPACING) -> np.ndarray:
    """Smooth rotationally symmetric test signal (Gaussian blob, no aliasing).

    Amplitude 1 with sigma = 4 HU gives d' ~ 1.3 in the white-noise tests —
    a regime where score distributions genuinely overlap, so agreement between
    closed form and simulation is a real check rather than a triviality.
    """
    ny, nx = shape
    y = (np.arange(ny) - (ny - 1) / 2.0) * spacing
    x = (np.arange(nx) - (nx - 1) / 2.0) * spacing
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return 1.0 * np.exp(-(xx**2 + yy**2) / (2.0 * 1.0**2))


# --------------------------------------------------------------------------------------
# NPS measurement
# --------------------------------------------------------------------------------------


def test_nps_integral_equals_variance() -> None:
    # Parseval identity: sum NPS du dv == population variance of detrended ROIs.
    rng = np.random.default_rng(SEED)
    rois = rng.normal(0.0, 3.0, size=(16, 32, 32))
    res = nps_2d(rois, SPACING)
    assert res.variance == pytest.approx(
        float(np.mean((rois - rois.mean(axis=(-2, -1), keepdims=True)) ** 2))
    )
    assert res.integral == pytest.approx(res.variance, rel=1e-10)


def test_white_noise_nps_is_flat_at_sigma2_dxdy() -> None:
    # White noise of SD sigma gives a flat NPS at sigma^2 * dx * dy.
    sigma = 2.5
    rng = np.random.default_rng(SEED + 1)
    rois = rng.normal(0.0, sigma, size=(256, 32, 32))
    res = nps_2d(rois, SPACING)
    expected_level = sigma**2 * SPACING * SPACING
    # Exclude DC (forced to zero by detrending) and radial-average the rest.
    assert res.nps_radial == pytest.approx(expected_level, rel=0.05)


def test_nps_rejects_bad_inputs() -> None:
    rng = np.random.default_rng(SEED + 2)
    rois = rng.normal(0.0, 1.0, size=(8, 16, 16))
    with pytest.raises(ValueError, match="non-finite"):
        nps_2d(np.array([[np.nan]]), SPACING)
    with pytest.raises(ValueError, match="spacing"):
        nps_2d(rois, -1.0)
    with pytest.raises(ValueError, match="detrend"):
        nps_2d(rois, SPACING, detrend="cubic")
    with pytest.raises(ValueError, match="4x4"):
        nps_2d(rng.normal(0.0, 1.0, size=(4, 2, 2)), SPACING)


# --------------------------------------------------------------------------------------
# closed-form observer identities
# --------------------------------------------------------------------------------------


def test_npw_white_noise_identity() -> None:
    # Exact identity: NPW (no eye filter) in white noise of SD sigma has
    # d' = ||s||_2 / sigma, independent of the pixel grid.
    sig = _blob()
    sigma = 4.0
    res = npwe(sig, sigma**2 * SPACING * SPACING, SPACING)
    assert res.name == "npw"
    assert res.d_prime == pytest.approx(float(np.linalg.norm(sig)) / sigma, rel=1e-10)
    # d' = signal_power / sqrt(noise_power) by construction.
    assert res.d_prime == pytest.approx(res.signal_power / np.sqrt(res.noise_power))


def test_ideal_observer_equals_npw_in_white_noise() -> None:
    # With a flat NPS, 1/NPS is a constant, so the prewhitening observer
    # coincides with the matched filter: same d' up to rounding.
    sig = _blob()
    white = 9.0 * SPACING * SPACING
    assert ideal_linear(sig, white, SPACING).d_prime == pytest.approx(
        npwe(sig, white, SPACING).d_prime, rel=1e-10
    )


def test_ideal_observer_upper_bounds_npwe() -> None:
    # The Hotelling observer maximises d' over linear observers; with a
    # non-flat NPS the NPWE must fall short.
    sig = _blob()
    rng = np.random.default_rng(SEED + 3)
    rois = rng.normal(0.0, 1.0, size=(64, 32, 32))
    rois = np.apply_along_axis(
        lambda r: np.convolve(r, [0.25, 0.5, 0.25], mode="same"), axis=-1, arr=rois
    )
    nps = nps_2d(rois, SPACING)
    eye = burgess_eye_filter()
    # The ideal observer needs a strictly positive NPS (it divides by it), and
    # a measured NPS has a zeroed DC bin by construction: fill DC with the
    # mean of its 8 nearest bins — the assumption being that DC carries the
    # local average noise power.
    filled = np.array(nps.nps, dtype=np.float64)
    c = filled.shape[0] // 2
    filled[c, c] = float(np.mean([filled[c - 1 : c + 2, c - 1 : c + 2].ravel()]))
    d_ideal = ideal_linear(sig, filled, SPACING).d_prime
    d_npwe = npwe(sig, nps, SPACING, eye_filter=eye).d_prime
    assert d_npwe < d_ideal


def test_npwe_immune_to_zeroed_dc_bin() -> None:
    # E(0) = 0 puts no weight at DC, so NPWE accepts a measured NPS whose DC
    # bin detrending zeroed, while plain NPW must refuse it.
    sig = _blob()
    rng = np.random.default_rng(SEED + 4)
    rois = rng.normal(0.0, 1.0, size=(64, 32, 32))
    nps = nps_2d(rois, SPACING)  # mean-detrended: DC bin is exactly zero
    assert nps.nps[nps.nps.shape[0] // 2, nps.nps.shape[1] // 2] == 0.0
    res = npwe(sig, nps, SPACING, eye_filter=burgess_eye_filter())
    assert np.isfinite(res.d_prime) and res.d_prime > 0.0
    with pytest.raises(ValueError, match="zero"):
        npwe(sig, nps, SPACING)  # plain NPW: DC carries real weight -> raise


def test_ideal_observer_rejects_floorless_nps() -> None:
    # A Gaussian-correlated NPS with sigma_c = 1 mm decays to ~1e-35 of its
    # peak by the plane's corner frequencies; without a floor the
    # prewhitening answer is built entirely of rounding garbage.
    sig = _blob()
    fr = np.hypot(np.fft.fftfreq(32, d=SPACING)[:, None], np.fft.fftfreq(32, d=SPACING)[None, :])
    gaussian_nps = np.exp(-((2 * np.pi * 1.0 * fr) ** 2))
    assert float(gaussian_nps.max() / gaussian_nps.min()) > 1e8
    with pytest.raises(ValueError, match="dynamic range"):
        ideal_linear(sig, gaussian_nps, SPACING, nps_layout="fft")
    # A declared floor makes it usable and the answer finite.
    res = ideal_linear(sig, gaussian_nps, SPACING, nps_layout="fft", noise_floor=1e-6)
    assert np.isfinite(res.d_prime) and res.d_prime > 0.0
    assert res.meta["noise_floor"] == 1e-6


def test_eye_filter_peaks_at_one() -> None:
    eye = burgess_eye_filter(peak_cycles_per_mm=0.8, exponent=1.3)
    fr = np.array([[0.8]])
    assert float(eye(fr)[0, 0]) == pytest.approx(1.0)
    assert float(eye(np.array([[0.0]]))[0, 0]) == 0.0


# --------------------------------------------------------------------------------------
# Monte-Carlo: empirical scores must reproduce the closed form
# --------------------------------------------------------------------------------------


def test_npw_closed_form_matches_simulated_scores() -> None:
    # Score simulated white-noise images with the closed-form NPW template;
    # the empirical d' must approach the closed form as the ensemble grows.
    sig = _blob()
    sigma = 4.0
    res = npwe(sig, sigma**2 * SPACING * SPACING, SPACING)
    rng = np.random.default_rng(SEED + 5)
    n = 4000
    base = rng.normal(0.0, sigma, size=(n, *sig.shape))
    present = base[: n // 2] + sig
    absent = base[n // 2 :]
    d_emp = d_prime_from_scores(
        score_images(present, res.template), score_images(absent, res.template)
    )
    # d' is ~1.3 here: distributions genuinely overlap, so this tolerance is
    # meaningful (2000 scores per class; sampling error ~1/sqrt(n) scale).
    assert d_emp == pytest.approx(res.d_prime, rel=0.05)


def test_gaussian_auc_matches_empirical_mann_whitney() -> None:
    # The closed-form AUC Phi(d'/sqrt(2)) should match the exact Mann-Whitney
    # AUC of the simulated scores for a linear statistic.
    sig = _blob()
    sigma = 4.0
    res = npwe(sig, sigma**2 * SPACING * SPACING, SPACING)
    rng = np.random.default_rng(SEED + 6)
    n = 4000
    base = rng.normal(0.0, sigma, size=(n, *sig.shape))
    present = base[: n // 2] + sig
    absent = base[n // 2 :]
    auc_emp = auc_from_scores(
        score_images(present, res.template), score_images(absent, res.template)
    )
    assert auc_emp == pytest.approx(res.auc, abs=0.01)


def test_figures_of_merit_basics() -> None:
    p = np.array([2.0, 2.1, 1.9, 2.05])
    a = np.array([0.0, 0.1, -0.1, 0.05])
    d = d_prime_from_scores(p, a)
    assert d > 0.0
    assert d_prime_from_scores(a, p) == pytest.approx(-d)
    assert auc_from_scores(p, a) > 0.99
    assert auc_from_scores(a, p) == pytest.approx(1.0 - auc_from_scores(p, a))
    with pytest.raises(ValueError, match="zero variance"):
        d_prime_from_scores(np.ones(3), np.ones(3))


# --------------------------------------------------------------------------------------
# input validation
# --------------------------------------------------------------------------------------


def test_observer_rejects_degenerate_inputs() -> None:
    sig = _blob()
    white = 4.0 * SPACING * SPACING
    with pytest.raises(ValueError, match="identically zero"):
        npwe(np.zeros((16, 16)), white, SPACING)
    with pytest.raises(ValueError, match="non-finite"):
        bad = sig.copy()
        bad[3, 3] = np.inf
        npwe(bad, white, SPACING)
    with pytest.raises(ValueError, match="power spectrum"):
        npwe(sig, np.full((32, 32), -1.0), SPACING)  # raw array path: negative power
    with pytest.raises(ValueError, match="finite and > 0"):
        npwe(sig, 0.0, SPACING)
    with pytest.raises(ValueError, match="spacing"):
        npwe(sig, white, 0.0)


def test_observer_rejects_mismatched_nps_grid() -> None:
    sig = _blob()
    rng = np.random.default_rng(SEED + 7)
    other = nps_2d(rng.normal(0.0, 1.0, size=(8, 16, 16)), SPACING)  # 16x16, not 32x32
    with pytest.raises(ValueError, match="same grid"):
        npwe(sig, other, SPACING, eye_filter=burgess_eye_filter())
