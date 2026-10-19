"""Sprint-5 tests: channelized Hotelling observer (S5-2 freeze).

Closed-form anchoring per AGENTS.md §7: in white noise of SD sigma with a
single channel g, the CHO collapses to |<s,g>| / (sigma ||g||) — derived
here from the definitions, not from a previously measured number.
"""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.observers import cho, gabor_channel_bank

SPACING = 0.5  # mm/px, the frozen S2-4 grid
ROI = (32, 32)


def _gauss_signal(sigma_mm: float = 1.0, amp: float = 30.0) -> np.ndarray:
    y, x = np.mgrid[0 : ROI[0], 0 : ROI[1]]
    xm = (x - (ROI[1] - 1) / 2.0) * SPACING
    ym = (y - (ROI[0] - 1) / 2.0) * SPACING
    return amp * np.exp(-(xm**2 + ym**2) / (2.0 * sigma_mm**2))


def test_cho_single_channel_white_noise_closed_form() -> None:
    # White noise SD sigma, one channel g: t = <n, g> dx^2 is Gaussian with
    # variance sigma^2 dx^4 sum(g^2), so d' = |<s,g>| / (sigma ||g||).
    # The dx factors cancel exactly; the test formula keeps them explicit.
    rng = np.random.default_rng(1234)
    sigma = 20.0
    n = 60_000
    rois = rng.normal(0.0, sigma, (n, *ROI))
    sig = _gauss_signal()
    ch = gabor_channel_bank(ROI, SPACING, frequencies_cyc_mm=(0.5,), orientations_deg=(0.0,))
    g = ch[0]
    res = cho(sig, rois, SPACING, ch)
    dx2 = SPACING * SPACING
    closed = abs(float((sig * g).sum()) * dx2) / (sigma * float(np.sqrt((g * g).sum() * dx2 * dx2)))
    assert res.d_prime == pytest.approx(closed, rel=0.03)


def test_cho_channel_scale_invariance() -> None:
    # d' must not change when a channel is multiplied by a constant: the
    # response and the covariance row/column scale together.
    rng = np.random.default_rng(99)
    rois = rng.normal(0.0, 15.0, (4_000, *ROI))
    sig = _gauss_signal()
    ch = gabor_channel_bank(ROI, SPACING)
    scaled = ch.copy()
    scaled[3] *= 7.3
    assert cho(sig, rois, SPACING, scaled).d_prime == pytest.approx(
        cho(sig, rois, SPACING, ch).d_prime, rel=1e-12
    )


def test_cho_9channel_bank_is_full_rank_on_grid() -> None:
    # The frozen 3x3 bank must be linearly independent on the pixel grid —
    # the exact degeneracy found in review was a carrier at 1 cycle/pixel,
    # where cos(2 pi k) = 1 erases the orientation dependence.
    ch = gabor_channel_bank(ROI, SPACING)
    flat = ch.reshape(ch.shape[0], -1)
    gram = flat @ flat.T
    assert np.linalg.matrix_rank(gram) == ch.shape[0]


def test_cho_rejects_nyquist_carrier() -> None:
    with pytest.raises(ValueError, match="Nyquist"):
        gabor_channel_bank(ROI, SPACING, frequencies_cyc_mm=(1.0,))  # 1 cy/px at 0.5 mm


def test_cho_guards() -> None:
    rng = np.random.default_rng(5)
    rois = rng.normal(0.0, 1.0, (64, *ROI))
    sig = _gauss_signal()
    ch = gabor_channel_bank(ROI, SPACING)
    with pytest.raises(ValueError, match="identically zero"):
        cho(np.zeros(ROI), rois, SPACING, ch)
    with pytest.raises(ValueError, match=r"at least n_channels\+1"):
        cho(sig, rois[:4], SPACING, ch)  # 9 channels, 4 ROIs
    with pytest.raises(ValueError, match="non-zero somewhere"):
        cho(sig, rois, SPACING, np.zeros_like(ch))
    with pytest.raises(ValueError, match="shape"):
        cho(sig, rois, SPACING, ch[:, :16, :16])
