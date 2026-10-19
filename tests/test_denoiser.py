"""Tests for the VMI denoiser model (S3-2): shape, size budget, determinism."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from pcctvmi.denoiser import (
    MAX_FEATURES,
    VMIDenoiser,
    from_model_output,
    n_parameters,
    to_model_input,
)

SEED = 20261019


def test_parameter_budget() -> None:
    model = VMIDenoiser()
    n = n_parameters(model)
    assert 0 < n < 1_000_000  # frozen budget (S3-2)
    assert MAX_FEATURES == 64


def test_forward_shape_and_grid_invariance() -> None:
    model = VMIDenoiser().eval()
    with torch.no_grad():
        # training crop size, evaluation size, and an odd size must all work
        # (fully convolutional, two downsamplings).
        for size in ((32, 32), (128, 128), (30, 30)):
            x = torch.zeros(1, 16, *size)
            y = model(x)
            assert y.shape == x.shape


def test_eval_mode_is_deterministic() -> None:
    rng = np.random.default_rng(SEED)
    model = VMIDenoiser().eval()
    x = torch.from_numpy(rng.normal(0, 100, size=(1, 16, 32, 32)).astype(np.float32))
    with torch.no_grad():
        y1 = model(x).numpy().copy()
        y2 = model(x).numpy().copy()
    np.testing.assert_array_equal(y1, y2)


def test_training_reduces_loss_on_overfit_batch() -> None:
    # The architecture must be trainable at all: measured on CPU, 200 Adam
    # steps toward the identity map on a fixed 8-sample batch reduce the L2
    # loss well below the random-init value (a from-scratch UNet converges
    # slowly; this is a connectivity probe, not a convergence check).
    torch.manual_seed(SEED)
    model = VMIDenoiser(base=16)
    rng = np.random.default_rng(SEED)
    x = torch.from_numpy(rng.normal(0, 100, size=(8, 16, 32, 32)).astype(np.float32))
    target = x.clone()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    losses = []
    for _ in range(200):
        opt.zero_grad()
        loss = torch.mean((model(x) - target) ** 2)
        loss.backward()
        opt.step()
        losses.append(float(loss.detach()))
    assert losses[-1] < 0.75 * losses[0]


def test_io_helpers_roundtrip() -> None:
    stack = np.random.default_rng(SEED).normal(0, 50, size=(16, 10, 12))
    tensor = to_model_input(stack)
    assert tensor.shape == (1, 16, 10, 12)
    assert tensor.dtype == torch.float32
    out = from_model_output(tensor)
    # float64 -> float32 is lossy; the roundtrip is exact only against the
    # float32-representable value.
    np.testing.assert_array_equal(out, stack.astype(np.float32).astype(np.float64))
    with pytest.raises(ValueError, match="n_kev"):
        to_model_input(stack[0])
    with pytest.raises(ValueError, match="single-sample"):
        from_model_output(tensor[0])
