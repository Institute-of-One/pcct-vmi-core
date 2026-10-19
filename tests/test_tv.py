"""Sprint-5 tests: 3-D TV denoiser control arm (S5-3 freeze)."""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.tv import chambolle_tv_3d, laplacian_noise_sd

SHAPE = (16, 32, 32)


def _noisy(seed: int = 0, sigma: float = 50.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(1000.0, sigma, SHAPE)


def test_tv_zero_weight_is_identity() -> None:
    y = _noisy()
    out = chambolle_tv_3d(y, 0.0, n_iter=5)
    assert out is not y  # copy, not an alias
    assert np.array_equal(out, y)


def test_tv_constant_image_unchanged() -> None:
    y = np.full(SHAPE, 777.0)
    out = chambolle_tv_3d(y, 100.0, n_iter=100)
    assert out == pytest.approx(y, abs=1e-3)


def test_tv_noise_sd_decreases_with_weight() -> None:
    # Monotonicity in the regularisation strength — the direction every
    # correct TV implementation must show, independent of any tuned value.
    y = _noisy(sigma=80.0)
    sd_small = float(chambolle_tv_3d(y, 50.0, n_iter=150).std())
    sd_large = float(chambolle_tv_3d(y, 500.0, n_iter=150).std())
    assert sd_large < sd_small < float(y.std())


def test_tv_batch_matches_single() -> None:
    y = _noisy()
    batch = np.stack([y, _noisy(seed=1)])
    out_b = chambolle_tv_3d(batch, 100.0, n_iter=50)
    out_s = chambolle_tv_3d(y, 100.0, n_iter=50)
    assert out_b[0] == pytest.approx(out_s, abs=1e-4)


def test_tv_guards() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        bad = _noisy()
        bad[0, 0, 0] = np.nan
        chambolle_tv_3d(bad, 10.0)
    with pytest.raises(ValueError, match="weight"):
        chambolle_tv_3d(_noisy(), -1.0)
    with pytest.raises(ValueError, match="n_iter"):
        chambolle_tv_3d(_noisy(), 10.0, n_iter=0)
    with pytest.raises(ValueError, match="stack must be"):
        chambolle_tv_3d(np.zeros((4, 4)), 10.0)


def test_laplacian_noise_sd_recovers_sigma() -> None:
    # White noise: MAD/sqrt(gain^2) scaling must return the SD (closed form).
    rng = np.random.default_rng(7)
    for sigma in (10.0, 100.0):
        stack = rng.normal(0.0, sigma, (16, 64, 64))
        assert laplacian_noise_sd(stack) == pytest.approx(sigma, rel=0.05)
