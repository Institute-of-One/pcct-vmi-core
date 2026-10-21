"""Image-domain correlated-noise synthesis for the H4 walnut arm.

PROTOCOL_FREEZE.md §12.3/§12.4: low-count walnut images are simulated by
injecting stationary correlated Gaussian noise into the full-dose (Low,
High) bin images. The target noise model (2-D auto NPS per channel plus the
cross-channel cross-spectrum) is estimated from the simulator at the
walnut-matched configuration by ``tools/walnut_noise_model.py``.

Conventions (identical to ``pcctvmi.observers.nps_2d``):

- pixel pitch ``dx = dy`` in mm; frequencies in cycles/mm;
- ``NPS(u, v) = dx*dy/(nx*ny) * E|DFT{detrended ROI}|^2`` so that
  ``sum(NPS) * du * dv = sigma^2`` exactly;
- white noise of SD ``sigma`` has a flat NPS at ``sigma^2 * dx * dy``.

Synthesis draws unit-white real Gaussian fields in the DFT domain, shapes
them by ``sqrt(S/(dx*dy))`` (which reproduces the target NPS exactly on
the model grid by the convention above), and couples the two channels per
frequency with the correlation coefficient ``rho = S_LH / sqrt(S_LL*S_HH)``
(clip to |rho| <= 1, the exact PSD condition for a 2x2 Hermitian matrix
with non-negative autos). Because the model grid has the same pitch as the
target images, noise is synthesised on the model grid and tiled to cover
the target shape; the verification test (PROTOCOL_FREEZE.md S12-7) measures
the injected NPS on aligned model-sized ROIs and compares it to the target.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NoiseModel:
    """Cross-channel 2-D noise power spectrum on the model frequency grid.

    All arrays are fft2-ordered (row/column 0 = DC) and exactly Hermitian
    (auto: real even; cross: Hermitian), as produced by periodogram
    averaging over detrended ROIs of real fields.

    Attributes:
        s_ll, s_hh: auto NPS of the Low / High channel (HU^2 mm^2).
        s_lh: complex cross-spectrum S_LH (S_HL is its conjugate).
        spacing_mm: pixel pitch in mm.
    """

    s_ll: np.ndarray
    s_hh: np.ndarray
    s_lh: np.ndarray
    spacing_mm: float

    def __post_init__(self) -> None:
        self._validated()

    @staticmethod
    def _neg_index(n: int) -> np.ndarray:
        """Modular negation index map: k -> (-k) mod n (DC and Nyquist fixed)."""
        idx = np.arange(n)
        idx[1:] = n - idx[1:]
        return idx

    def _validated(self) -> None:
        arrs = []
        for name in ("s_ll", "s_hh", "s_lh"):
            arr = np.asarray(getattr(self, name))
            if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
                raise ValueError(f"{name} must be a square 2-D array, got {arr.shape}")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{name} must be finite")
            arrs.append(arr)
        s_ll, s_hh, s_lh = arrs
        if s_ll.shape != s_hh.shape or s_ll.shape != s_lh.shape:
            raise ValueError("s_ll, s_hh, s_lh must share a shape")
        if np.any(s_ll < 0) or np.any(s_hh < 0):
            raise ValueError("auto-spectra must be non-negative")
        # Hermitian symmetry in the DFT sense: X[(-f) mod N] = conj(X[f]).
        # Note this is NOT array reversal: index 0 (DC) and N/2 (Nyquist,
        # even N) are self-conjugate.
        neg_y = self._neg_index(s_ll.shape[0])
        neg_x = self._neg_index(s_ll.shape[1])
        my, mx = np.ix_(neg_y, neg_x)
        if not np.allclose(s_ll, s_ll[my, mx], rtol=1e-10, atol=1e-12):
            raise ValueError("s_ll must be even (Hermitian for a real field)")
        if not np.allclose(s_hh, s_hh[my, mx], rtol=1e-10, atol=1e-12):
            raise ValueError("s_hh must be even (Hermitian for a real field)")
        if not np.allclose(s_lh, np.conj(s_lh[my, mx]), rtol=1e-10, atol=1e-12):
            raise ValueError("s_lh must be Hermitian")
        if not np.isfinite(self.spacing_mm) or self.spacing_mm <= 0:
            raise ValueError("spacing_mm must be positive")

    @property
    def shape(self) -> tuple[int, int]:
        """Model grid size (ny, nx) in pixels."""
        return (self.s_ll.shape[0], self.s_ll.shape[1])

    def save(self, path) -> None:
        np.savez(
            path,
            s_ll=self.s_ll,
            s_hh=self.s_hh,
            s_lh=self.s_lh,
            spacing_mm=self.spacing_mm,
        )

    @classmethod
    def load(cls, path) -> NoiseModel:
        with np.load(path) as z:
            return cls(
                s_ll=z["s_ll"],
                s_hh=z["s_hh"],
                s_lh=z["s_lh"],
                spacing_mm=float(z["spacing_mm"]),
            )


def synthesize(
    model: NoiseModel,
    shape: tuple[int, int],
    rng: np.random.Generator,
) -> np.ndarray:
    """Synthesize a (2, ny, nx) correlated noise field for (Low, High).

    The field is exactly real, stationary within model-grid tiles, with
    per-channel NPS equal to the model on the model grid and per-frequency
    cross-channel correlation ``S_LH / sqrt(S_LL * S_HH)`` clipped to the
    PSD cone (|rho| <= 1).
    """
    ny, nx = shape
    my, mx = model.shape
    if ny < my or nx < mx:
        raise ValueError(f"target shape {shape} smaller than model grid {model.shape}")
    ty, tx = (ny + my - 1) // my, (nx + mx - 1) // mx
    field = _synthesize_tiles(model, (ty, tx), rng)
    return field[:, :ny, :nx]


def _synthesize_tiles(
    model: NoiseModel,
    tiles: tuple[int, int],
    rng: np.random.Generator,
) -> np.ndarray:
    ty, tx = tiles
    my, mx = model.shape
    n_tiles = ty * tx
    # Unit-white real Gaussian fields in the image domain; their DFTs are
    # exactly Hermitian, with E|W(f)|^2 = nx*ny per bin.
    w = rng.standard_normal((n_tiles, 2, my, mx))
    w_l = np.fft.fft2(w[:, 0], axes=(-2, -1))
    w_h = np.fft.fft2(w[:, 1], axes=(-2, -1))

    # Shaping amplitudes: with x = A * W, W = fft2(unit real white) and
    # E|W(f)|^2 = nx*ny, the NPS of ifft2(x) is dx*dy/(nx*ny) * A^2 * nx*ny,
    # so A = sqrt(S) / dx reproduces the target spectrum S exactly.
    dx = model.spacing_mm
    amp_l = np.sqrt(model.s_ll) / dx
    amp_h = np.sqrt(model.s_hh) / dx
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = model.s_lh / np.sqrt(model.s_ll * model.s_hh)
    rho = np.nan_to_num(rho, nan=0.0, posinf=0.0, neginf=0.0)
    mag = np.abs(rho)
    scale = np.where(mag > 1.0, 1.0 / np.maximum(mag, 1e-30), 1.0)
    rho = rho * scale  # exact PSD cone for a 2x2 Hermitian matrix

    # Cross-channel coupling uses the CONJUGATE of the normalised
    # cross-spectrum: the model defines S_LH = E[W_L conj(W_H)], and a
    # factor exp(+i*2*pi*k*d/N) in the H-channel DFT corresponds to a
    # spatial shift, whose cross-spectrum is the conjugate phase. With
    # X_H = conj(rho) * A_H * W_L the realised spectrum is
    # E[X_L conj(X_H)] = rho * A_L * A_H * E|W_L|^2 = S_LH exactly.
    x_l = amp_l[None] * w_l
    x_h = amp_h[None] * (np.conj(rho)[None] * w_l + np.sqrt(1.0 - np.abs(rho)[None] ** 2) * w_h)
    noise_l = np.fft.ifft2(x_l, axes=(-2, -1)).real
    noise_h = np.fft.ifft2(x_h, axes=(-2, -1)).real
    out = np.stack([noise_l, noise_h], axis=1)  # (n_tiles, 2, my, mx)
    # tile layout: tile index is row-major (ty, tx); place tiles adjacently.
    return out.reshape(ty, tx, 2, my, mx).transpose(2, 0, 3, 1, 4).reshape(2, ty * my, tx * mx)
