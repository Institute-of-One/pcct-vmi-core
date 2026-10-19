"""Small 2D UNet denoiser for VMI stacks (Sprint 3 freeze, PROTOCOL_FREEZE.md S3-2).

The model maps a noisy VMI stack ``(n_kev, ny, nx)`` to a denoised stack of
the same shape, treating the keV levels as input/output channels. It is
fully convolutional, so it trains on 128^2 crops and evaluates on the full
512^2 images (and on smaller crops around ROIs) without any change.

This study's contribution is the evaluation framework, not the architecture:
the network is the minimal standard UNet, deliberately small (<1M
parameters) so the whole training pipeline is reproducible on a CPU.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

__all__ = ["VMIDenoiser", "n_parameters"]

#: Maximum channel width of the frozen architecture (S3-2).
MAX_FEATURES = 64


class _ConvBlock(nn.Module):
    """Two 3x3 convolutions with GroupNorm (channel-group normalisation)."""

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1),
            nn.GroupNorm(num_groups=8, num_channels=out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1),
            nn.GroupNorm(num_groups=8, num_channels=out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class VMIDenoiser(nn.Module):
    """UNet with two downsamplings: n_kev -> 32 -> 64 -> 64 -> 32 -> n_kev.

    GroupNorm is used throughout so the frozen BatchNorm-free architecture is
    batch-size independent (evaluation runs with batch size 1) and
    deterministic given fixed weights.
    """

    def __init__(self, n_channels: int = 16, base: int = 32) -> None:
        super().__init__()
        if base * 2 > MAX_FEATURES:
            raise ValueError(f"base={base} exceeds the frozen maximum {MAX_FEATURES // 2}")
        self.enc1 = _ConvBlock(n_channels, base)
        self.enc2 = _ConvBlock(base, base * 2)
        self.bottleneck = _ConvBlock(base * 2, MAX_FEATURES)
        self.pool = nn.MaxPool2d(2)
        self.up2 = nn.ConvTranspose2d(MAX_FEATURES, base * 2, kernel_size=2, stride=2)
        self.dec2 = _ConvBlock(base * 4, base * 2)
        self.up1 = nn.ConvTranspose2d(base * 2, base, kernel_size=2, stride=2)
        self.dec1 = _ConvBlock(base * 2, base)
        self.head = nn.Conv2d(base, n_channels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Pad to a multiple of 4 (two 2x downsamplings) with reflection, and
        # crop back — any input grid size works, not just multiples of 4.
        h, w = x.shape[2], x.shape[3]
        ph, pw = (4 - h % 4) % 4, (4 - w % 4) % 4
        if ph or pw:
            x = nn.functional.pad(x, (0, pw, 0, ph), mode="reflect")
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        bot = self.bottleneck(self.pool(e2))
        d2 = self.up2(bot)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))
        d1 = self.up1(d2)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))
        return self.head(d1)[:, :, :h, :w]


def n_parameters(model: nn.Module) -> int:
    """Total number of scalar parameters (frozen budget check: < 1e6)."""
    return int(sum(p.numel() for p in model.parameters()))


def to_model_input(stack_hu: np.ndarray) -> torch.Tensor:
    """(n_kev, ny, nx) HU numpy array -> (1, n_kev, ny, nx) float32 tensor."""
    arr = np.asarray(stack_hu, dtype=np.float32)
    if arr.ndim != 3:
        raise ValueError(f"stack must be (n_kev, ny, nx), got {arr.shape}")
    return torch.from_numpy(arr[None, ...])


def from_model_output(output: torch.Tensor) -> np.ndarray:
    """(1, n_kev, ny, nx) tensor -> (n_kev, ny, nx) float64 numpy array."""
    if output.ndim != 4 or output.shape[0] != 1:
        raise ValueError(f"expected a single-sample batch, got {tuple(output.shape)}")
    return output[0].detach().cpu().numpy().astype(np.float64)
