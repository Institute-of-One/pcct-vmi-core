"""3-D total-variation denoising (Sprint-5 control arm D3, PROTOCOL_FREEZE.md S5-3).

Chambolle's dual algorithm for the Rudin-Osher-Fatemi model on the VMI stack,
with the keV axis treated as a third spatial axis of unit spacing (frozen):

    min_x  0.5 * ||x - y||^2  +  weight * TV(x)

    TV(x) = sum_i |grad x|_i,  grad = (d/dkeV, d/dy, d/dx)

Convergence condition tau <= 1/12 in 3-D (three forward-difference
components). No data-dependent early stopping: the iteration count is
frozen, and the same count is used for every stack.
"""

from __future__ import annotations

import numpy as np
import torch

__all__ = ["chambolle_tv_3d", "laplacian_noise_sd"]


def _grad(v: torch.Tensor) -> torch.Tensor:
    """Forward differences along the last 3 axes; zero boundary padding."""
    g = torch.zeros(v.shape + (3,), dtype=v.dtype)
    g[..., :-1, :, :, 0] = v[..., 1:, :, :] - v[..., :-1, :, :]
    g[..., :, :-1, :, 1] = v[..., :, 1:, :] - v[..., :, :-1, :]
    g[..., :, :, :-1, 2] = v[..., :, :, 1:] - v[..., :, :, :-1]
    return g


def _div(p: torch.Tensor) -> torch.Tensor:
    """Adjoint of :func:`_grad` (transposed differences, zero boundary)."""
    v = torch.zeros(p.shape[:-1], dtype=p.dtype)
    a = p[..., :-1, :, :, 0]
    v[..., :-1, :, :] -= a
    v[..., 1:, :, :] += a
    b = p[..., :, :-1, :, 1]
    v[..., :, :-1, :] -= b
    v[..., :, 1:, :] += b
    c = p[..., :, :, :-1, 2]
    v[..., :, :, :-1] -= c
    v[..., :, :, 1:] += c
    return v


def chambolle_tv_3d(
    stack: np.ndarray,
    weight: float,
    *,
    n_iter: int = 300,
    tau: float = 1.0 / 12.0,
) -> np.ndarray:
    """Denoise one stack ``(c, h, w)`` or a batch ``(n, c, h, w)`` with 3-D TV.

    ``weight`` is the frozen regularisation parameter (HU units, same scale
    as the image values). ``weight = 0`` must return the input unchanged
    (the test pins this identity). Raises on non-finite input or a negative
    weight; a non-positive iteration count is rejected.
    """
    arr = np.asarray(stack, dtype=np.float64)
    if arr.ndim not in (3, 4):
        raise ValueError(f"stack must be (c,h,w) or (n,c,h,w), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("stack contains non-finite values")
    weight = float(weight)
    if not np.isfinite(weight) or weight < 0.0:
        raise ValueError(f"weight must be finite and >= 0, got {weight!r}")
    if n_iter < 1:
        raise ValueError(f"n_iter must be >= 1, got {n_iter}")
    if weight == 0.0:
        return arr.copy()

    batched = arr.ndim == 4
    y = torch.tensor(arr if batched else arr[None], dtype=torch.float32)
    p = torch.zeros(y.shape + (3,), dtype=torch.float32)
    for _ in range(int(n_iter)):
        q = _div(p) - y / weight
        g = _grad(q)
        # Dual ascent with the sign convention x = y - weight * div(p): the
        # fixed point must satisfy p = grad(x)/|grad(x)| where grad(x) != 0
        # (KKT condition of the primal). The '+' sign here converges to -p,
        # which maximises the dual instead of minimising the primal — the
        # observed symptom was output variance *growing* with `weight`.
        # Verified: stationarity residual ~1e-14 and |p - gx/|gx|| ~3e-8 on a
        # closed 8x8 problem; weight -> infinity collapses to the mean.
        p = (p - tau * g) / (1.0 + tau * g.norm(dim=-1, keepdim=True))
    out = y - weight * _div(p)
    result = out.numpy()
    return result if batched else result[0]


def laplacian_noise_sd(stack: np.ndarray) -> float:
    """Robust per-stack noise SD from the 3-D discrete Laplacian.

    6-neighbour Laplacian (centre 6, faces -1): white-noise gain sqrt(42),
    so sigma_hat = MAD(laplacian) / (0.6745 * sqrt(42)). Used only to scale
    the frozen TV weight ``weight = c * sigma_hat^2`` (S5-3); the constant c
    is chosen on validation data, never on the frozen evaluation conditions.
    """
    arr = np.asarray(stack, dtype=np.float64)
    if arr.ndim != 3:
        raise ValueError(f"stack must be (c,h,w), got {arr.shape}")
    lap = 6.0 * arr.copy()
    lap[:-1] -= arr[1:]
    lap[1:] -= arr[:-1]
    lap[:, :-1] -= arr[:, 1:]
    lap[:, 1:] -= arr[:, :-1]
    lap[:, :, :-1] -= arr[:, :, 1:]
    lap[:, :, 1:] -= arr[:, :, :-1]
    med = np.median(lap)
    mad = np.median(np.abs(lap - med))
    return float(mad / (0.6745 * np.sqrt(42.0)))
