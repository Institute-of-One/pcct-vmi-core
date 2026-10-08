"""Determinism and contract tests."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from pcctvmi.forward import simulate
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum

THETA_SMALL = np.linspace(0.0, 360.0, 90, endpoint=False)


def _small_result(seed: int):
    spec = Spectrum.from_csv()
    ph = make_water_cylinder_phantom(
        n=128,
        diameter_cm=10.0,
        pixel_size_cm=0.1,
        inserts=(Insert(0.0, -3.0, 0.6, 0.005),),
    )
    return simulate(spec, ph, theta_deg=THETA_SMALL, thresholds_kev=(30.0,), n0=5.0e4, seed=seed)


def _digest(arrays: list[np.ndarray]) -> str:
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).view(np.uint8).tobytes())
    return h.hexdigest()


def test_same_seed_bit_exact() -> None:
    r1 = _small_result(42)
    r2 = _small_result(42)
    for c1, c2 in zip(r1.counts, r2.counts, strict=True):
        assert np.array_equal(c1, c2)
    assert _digest(r1.counts) == _digest(r2.counts)
    i1 = reconstruct_bins(r1)
    i2 = reconstruct_bins(r2)
    assert _digest(i1) == _digest(i2)


def test_different_seed_differs() -> None:
    r1 = _small_result(1)
    r2 = _small_result(2)
    assert not np.array_equal(r1.counts[0], r2.counts[0])


def test_reconstruct_rejects_zero_counts() -> None:
    r = _small_result(0)
    r.counts[0][0, 0] = 0  # manufactured degenerate measurement
    with pytest.raises(ValueError):
        reconstruct_bins(r)


def test_decompose_rejects_singular() -> None:
    from pcctvmi.vmi import decompose

    with pytest.raises(ValueError):
        decompose(
            [np.zeros((4, 4)), np.zeros((4, 4))],
            [
                {"water": 0.2, "iodine": 0.3},
                {"water": 0.2, "iodine": 0.3},
            ],
        )
