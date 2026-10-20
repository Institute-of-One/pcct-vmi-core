"""D2 loss component: the differentiable 2-basis decomposition.

``fit_basis_torch`` must reproduce :func:`pcctvmi.projection.fit_basis` on
the same data (float32 tolerance) — the training loss relies on the identity
decompose(synthesize(a, b)) == (a, b) for the teacher stack.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from pcctvmi.projection import _r_values, fit_basis, fit_basis_torch, gram_matrix
from pcctvmi.vmi import VMI_GRID_KEV, vmi_stack

SEED = 20261020


def _fields(n: int = 12):
    rng = np.random.default_rng(SEED)
    a = 1.0 + 0.05 * rng.normal(size=(n, n))
    b = 0.002 * np.abs(rng.normal(size=(n, n)))
    return a, b


def test_fit_basis_torch_matches_numpy() -> None:
    a, b = _fields()
    stack = vmi_stack(a, b) + np.random.default_rng(SEED + 1).normal(
        0.0, 5.0, (len(VMI_GRID_KEV), 12, 12)
    )
    a_np, b_np = fit_basis(stack)
    r_np = _r_values(np.asarray(VMI_GRID_KEV, dtype=np.float64))
    r_t = torch.tensor(r_np, dtype=torch.float32)
    gram = gram_matrix()
    a_t, b_t = fit_basis_torch(torch.tensor(stack, dtype=torch.float32)[None], r_t, gram)
    assert np.allclose(a_t.numpy()[0], a_np, atol=1e-5)
    assert np.allclose(b_t.numpy()[0], b_np, atol=1e-6)


def test_fit_basis_torch_recovers_synthesized_teacher() -> None:
    # The D2 training identity: decompose(synthesize(a, b)) == (a, b).
    a, b = _fields()
    stack = vmi_stack(a, b)
    r_t = torch.tensor(_r_values(np.asarray(VMI_GRID_KEV, dtype=np.float64)), dtype=torch.float32)
    a_t, b_t = fit_basis_torch(torch.tensor(stack)[None], r_t, gram_matrix())
    assert a_t.numpy()[0] == pytest.approx(a, abs=1e-4)
    assert b_t.numpy()[0] == pytest.approx(b, abs=1e-6)


def test_fit_basis_torch_gradient_flows() -> None:
    # The loss term is differentiated through the decomposition; a zero
    # gradient would silently disable it (the guard the AGENTS.md swallow-loop
    # rule demands an assert for).
    a, b = _fields()
    stack = torch.tensor(vmi_stack(a, b), dtype=torch.float32, requires_grad=True)
    r_t = torch.tensor(_r_values(np.asarray(VMI_GRID_KEV, dtype=np.float64)), dtype=torch.float32)
    _, b_t = fit_basis_torch(stack[None], r_t, gram_matrix())
    loss = (b_t**2).sum()
    loss.backward()
    assert stack.grad is not None
    assert float(stack.grad.abs().sum()) > 0.0


def test_fit_basis_torch_validates_shape() -> None:
    with pytest.raises(ValueError, match="batch, n_energy, ny, nx"):
        fit_basis_torch(torch.zeros(4, 8, 8), torch.zeros(16), gram_matrix())
