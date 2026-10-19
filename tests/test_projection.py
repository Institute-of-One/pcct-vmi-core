"""Closed-form tests for the 2-basis projection of VMI stacks (S3-9)."""

from __future__ import annotations

import numpy as np
import pytest

from pcctvmi.projection import basis_residual, fit_basis
from pcctvmi.vmi import VMI_GRID_KEV, vmi_stack

SEED = 20261019


def _random_fields(n: int = 24, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    a = 1.0 + 0.02 * rng.normal(size=(n, n))
    b = 0.005 * np.abs(rng.normal(size=(n, n)))
    return a, b


def test_fit_basis_recovers_synthesized_stack_exactly() -> None:
    # A VMI stack synthesized from (a, b) lies exactly on the 2-basis
    # manifold; the closed-form normal equations must invert the synthesis.
    a, b = _random_fields()
    stack = vmi_stack(a, b)
    a_fit, b_fit = fit_basis(stack)
    assert a_fit == pytest.approx(a, rel=1e-10)
    assert b_fit == pytest.approx(b, rel=1e-10)
    assert basis_residual(stack) == pytest.approx(0.0, abs=1e-9)


def test_residual_is_orthogonal_component_of_perturbation() -> None:
    # Adding a per-keV perturbation off the manifold, the residual is the
    # perturbation minus its own least-squares 2-basis fit — the component
    # orthogonal (in the design-matrix metric) to span{1, r_k}.
    a, b = _random_fields()
    stack = vmi_stack(a, b)
    rng = np.random.default_rng(SEED + 1)
    n_kev = len(VMI_GRID_KEV)
    delta = 40.0 * rng.normal(size=(n_kev, 1, 1))  # spatially uniform, per-keV
    from pcctvmi.projection import _r_values

    r = _r_values(np.asarray(VMI_GRID_KEV, dtype=np.float64))
    design = np.stack([np.ones_like(r), r], axis=1)  # (n_kev, 2)
    coef, *_ = np.linalg.lstsq(design, delta[:, 0, 0], rcond=None)
    expected_residual = delta[:, 0, 0] - design @ coef
    res = basis_residual(stack + delta)
    assert np.all(res == pytest.approx(float(np.sqrt(np.mean(expected_residual**2))), rel=1e-9))


def test_fit_basis_validates_inputs() -> None:
    a, b = _random_fields(n=8)
    stack = vmi_stack(a, b)
    with pytest.raises(ValueError, match="n_energy, ny, nx"):
        fit_basis(stack[0])
    with pytest.raises(ValueError, match="slices"):
        fit_basis(stack, energies_kev=VMI_GRID_KEV[:8])
    # A grid whose iodine/water ratios are all identical is degenerate:
    # the 2x2 normal equations are singular and must raise, not return NaN.
    with pytest.raises(ValueError, match="degenerate"):
        fit_basis(stack, energies_kev=(70.0,) * len(VMI_GRID_KEV))
