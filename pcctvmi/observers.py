"""Model observers and NPS measurement for VMI task detectability (H1).

Ported from taskiq-core (IORN-003, validated against closed forms) under the
Sprint-2 freeze (docs/PROTOCOL_FREEZE.md §7). Everything here is **mm-based**:
``spacing_mm`` is the pixel pitch in mm, NPS values are in HU^2 mm^2, and
frequencies are in cycles/mm. The rest of the package is cm-based; convert at
the module boundary.

Two closed-form Fourier-domain linear observers are provided:

* :func:`npwe` — non-prewhitening with an eye filter, ``W = S E^2``,

  ``d'^2 = [int |S|^2 E^2 df]^2 / int |S|^2 E^4 NPS df``.

  With no eye filter this is the plain NPW observer, which in white noise of
  standard deviation ``sigma`` collapses exactly to ``d' = ||s||_2 / sigma`` —
  the identity the unit tests hold the NPS normalisation to.

* :func:`ideal_linear` — the prewhitening matched filter, ``W = S / NPS``,
  which for stationary Gaussian noise is the Hotelling observer and hence the
  upper bound on every linear observer: ``d'^2 = int |S|^2 / NPS df``.

Both raise rather than return a plausible number when the noise model cannot
support them (see the ported guard docstrings). :func:`nps_2d` measures an
ensemble 2-D NPS whose integral equals the ROI variance to machine precision.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.special import ndtr

__all__ = [
    "NPSResult",
    "ObserverResult",
    "auc_from_scores",
    "burgess_eye_filter",
    "cho",
    "d_prime_from_scores",
    "gabor_channel_bank",
    "ideal_linear",
    "nps_2d",
    "npwe",
    "score_images",
]


# --------------------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class NPSResult:
    """Ensemble 2-D noise power spectrum.

    Attributes
    ----------
    nps:
        2-D NPS in ``value^2 mm^2``, DC-centred (``fftshift`` layout), such that
        ``int NPS du dv = sigma^2``.
    fx, fy:
        Frequency axes in cycles/mm matching the columns and rows of ``nps``.
    frequency:
        Radial frequency bin centres (DC excluded).
    nps_radial, radial_counts:
        Radially averaged NPS and the number of bins per radial bin.
    variance, integral:
        Pixel variance of the detrended ROIs and ``sum NPS du dv``; equal to
        machine precision — the identity the tests check rather than assume.
    spacing, n_rois, roi_shape, detrend:
        Echo of the inputs.
    """

    nps: np.ndarray
    fx: np.ndarray
    fy: np.ndarray
    frequency: np.ndarray
    nps_radial: np.ndarray
    radial_counts: np.ndarray
    variance: float
    integral: float
    spacing: float
    n_rois: int
    roi_shape: tuple[int, int]
    detrend: str

    @property
    def nyquist(self) -> float:
        """Pixel Nyquist frequency ``1 / (2 * spacing)`` in cycles/mm."""
        return 1.0 / (2.0 * self.spacing)


@dataclass(frozen=True, eq=False)
class ObserverResult:
    """Detectability of a closed-form Fourier-domain linear observer.

    d_prime is computed from the closed form, not simulated trials. auc is the
    equal-variance Gaussian value ``Phi(d' / sqrt(2))`` — exact here because a
    linear functional of Gaussian noise is Gaussian with the same variance
    under both hypotheses. signal_power / noise_power are the numerator and
    denominator of ``d_prime**2``, kept so a surprising d' can be traced.
    """

    name: str
    d_prime: float
    auc: float
    template: np.ndarray
    signal_power: float
    noise_power: float
    spacing: float
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# NPS measurement
# --------------------------------------------------------------------------------------


def nps_2d(
    images: np.ndarray,
    spacing_mm: float,
    *,
    detrend: str = "mean",
    radial_bin_width: float | None = None,
    f_max: float | None = None,
) -> NPSResult:
    r"""Ensemble 2-D noise power spectrum and its radial average.

    Normalisation: for ROIs of ``ny x nx`` pixels with pitch ``dx``,

    ``NPS(u_k, v_l) = dx dy / (n_x n_y) * mean_roi |DFT{detrended ROI}|^2``

    which makes ``sum NPS du dv = sigma^2`` an exact identity (checked in the
    tests at rtol=1e-10). White noise of SD ``sigma`` gives a flat NPS at
    ``sigma^2 dx dy``.

    Parameters
    ----------
    images:
        One ROI ``(ny, nx)`` or a stack ``(n, ny, nx)``. A single periodogram
        bin carries 100 % relative standard deviation, so an ensemble (and the
        radial average) is what makes the estimate usable.
    spacing_mm:
        Pixel pitch in mm.
    detrend:
        ``"mean"`` (default) subtracts each ROI's own mean — right for a
        genuinely uniform background. ``"poly2"`` removes a 2-D second-order
        polynomial per ROI. ``"none"`` leaves the ROI alone (all background
        power lands in the DC bin).
    radial_bin_width, f_max:
        Radial binning in cycles/mm; defaults to the coarser DFT bin spacing
        and the pixel Nyquist.
    """
    arr = np.asarray(images, dtype=np.float64)
    if arr.ndim == 2:
        arr = arr[None, ...]
    if arr.ndim != 3:
        raise ValueError(f"images must have shape (ny, nx) or (n, ny, nx), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("images contain non-finite values; refusing to estimate an NPS from them")

    n_rois, ny, nx = arr.shape
    if ny < 4 or nx < 4:
        raise ValueError(f"ROIs must be at least 4x4 pixels, got ({ny}, {nx})")

    spacing = float(spacing_mm)
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError(f"spacing_mm must be a finite positive number, got {spacing_mm!r}")

    if detrend == "mean":
        resid = arr - arr.mean(axis=(-2, -1), keepdims=True)
    elif detrend == "poly2":
        resid = _detrend_poly2(arr)
    elif detrend == "none":
        resid = arr
    else:
        raise ValueError(f"detrend must be one of 'mean', 'poly2', 'none'; got {detrend!r}")

    power = np.abs(np.fft.fft2(resid, axes=(-2, -1))) ** 2
    if detrend != "none":
        # Detrending removes the DC component by construction; enforce it
        # exactly (mean subtraction leaves ~1e-32 float residue) so downstream
        # consumers — the NPWE zero-NPS guard in particular — can rely on it.
        power[..., 0, 0] = 0.0
    nps = (spacing * spacing / (ny * nx)) * power.mean(axis=0)

    du = 1.0 / (nx * spacing)
    dv = 1.0 / (ny * spacing)
    integral = float(nps.sum() * du * dv)
    variance = float(np.mean(resid**2))

    nps_shift = np.fft.fftshift(nps)
    fx = np.fft.fftshift(np.fft.fftfreq(nx, d=spacing))
    fy = np.fft.fftshift(np.fft.fftfreq(ny, d=spacing))

    freq, nps_radial, counts = _radial_average(
        nps_shift, fx, fy, radial_bin_width=radial_bin_width, f_max=f_max, spacing=spacing
    )

    return NPSResult(
        nps=nps_shift,
        fx=fx,
        fy=fy,
        frequency=freq,
        nps_radial=nps_radial,
        radial_counts=counts,
        variance=variance,
        integral=integral,
        spacing=spacing,
        n_rois=n_rois,
        roi_shape=(ny, nx),
        detrend=detrend,
    )


def _detrend_poly2(arr: np.ndarray) -> np.ndarray:
    """Remove a per-ROI 2-D second-order polynomial (6 terms) by least squares."""
    _, ny, nx = arr.shape
    if ny < 3 or nx < 3:
        raise ValueError(f"detrend='poly2' needs ROIs of at least 3x3 pixels, got ({ny}, {nx})")
    y, x = np.meshgrid(np.linspace(-1.0, 1.0, ny), np.linspace(-1.0, 1.0, nx), indexing="ij")
    basis = np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1).reshape(ny * nx, 6)
    flat = arr.reshape(arr.shape[0], ny * nx).T
    coeffs, *_ = np.linalg.lstsq(basis, flat, rcond=None)
    fit = (basis @ coeffs).T.reshape(arr.shape)
    return arr - fit


def _radial_average(
    nps_shift: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
    *,
    radial_bin_width: float | None,
    f_max: float | None,
    spacing: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Radially average a centred 2-D NPS, excluding the DC bin (detrending
    forces DC to zero, so including it would drag the lowest bin toward zero)."""
    ny, nx = nps_shift.shape
    fxx, fyy = np.meshgrid(fx, fy, indexing="xy")
    fr = np.hypot(fxx, fyy)

    if radial_bin_width is None:
        radial_bin_width = max(1.0 / (nx * spacing), 1.0 / (ny * spacing))
    radial_bin_width = float(radial_bin_width)
    if not np.isfinite(radial_bin_width) or radial_bin_width <= 0.0:
        raise ValueError(f"radial_bin_width must be finite and > 0, got {radial_bin_width!r}")

    if f_max is None:
        f_max = 1.0 / (2.0 * spacing)
    f_max = float(f_max)
    if not np.isfinite(f_max) or f_max <= radial_bin_width:
        raise ValueError(
            f"f_max must be finite and larger than radial_bin_width "
            f"({radial_bin_width:.4g}), got {f_max!r}"
        )

    # Bins are centred on multiples of the width so the lowest bin is nonempty.
    n_bins = int(np.floor(f_max / radial_bin_width))
    if n_bins < 1:
        raise ValueError(
            f"f_max={f_max:.4g} leaves no radial bins at radial_bin_width={radial_bin_width:.4g}"
        )
    edges = (np.arange(n_bins + 1, dtype=np.float64) + 0.5) * radial_bin_width

    valid = (fr >= edges[0]) & (fr < edges[-1])  # DC excluded by construction
    idx = np.digitize(fr[valid], edges) - 1
    counts = np.bincount(idx, minlength=n_bins)
    if np.any(counts == 0):
        n_empty = int(np.count_nonzero(counts == 0))
        raise ValueError(
            f"{n_empty} of {n_bins} radial NPS bins are empty (radial_bin_width="
            f"{radial_bin_width:.4g} cycles/mm is too fine for a {ny}x{nx} ROI). Widen "
            "radial_bin_width or use larger ROIs."
        )
    sums = np.bincount(idx, weights=nps_shift[valid], minlength=n_bins)

    centers = (np.arange(n_bins, dtype=np.float64) + 1.0) * radial_bin_width
    return centers, sums / counts, counts


# --------------------------------------------------------------------------------------
# observers
# --------------------------------------------------------------------------------------


def _check_spacing(spacing_mm: float) -> float:
    spacing = float(spacing_mm)
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError(f"spacing_mm must be a finite positive number of mm, got {spacing_mm!r}")
    return spacing


def _as_signal(signal: np.ndarray) -> np.ndarray:
    sig = np.asarray(signal, dtype=np.float64)
    if sig.ndim != 2:
        raise ValueError(f"signal must be a 2-D image, got shape {sig.shape}")
    if not np.all(np.isfinite(sig)):
        raise ValueError("signal contains non-finite values")
    if not np.any(sig):
        raise ValueError("signal is identically zero: there is nothing to detect")
    return sig


def _frequency_grid(shape: tuple[int, int], spacing: float) -> np.ndarray:
    """Radial frequency in cycles/mm on the ``fft2`` layout (DC at ``[0, 0]``)."""
    ny, nx = shape
    fy = np.fft.fftfreq(ny, d=spacing)[:, None]
    fx = np.fft.fftfreq(nx, d=spacing)[None, :]
    return np.hypot(fy, fx)


def _nps_grid(
    nps: NPSResult | np.ndarray | Callable[[np.ndarray], np.ndarray] | float,
    shape: tuple[int, int],
    spacing: float,
    *,
    layout: str = "centered",
    require_positive: bool = False,
) -> np.ndarray:
    """Normalise any accepted NPS specification to an ``fft2``-layout grid.

    Accepts an :class:`NPSResult`, a scalar (white noise), a callable of radial
    frequency (an analytic model), or a raw 2-D array whose ``layout`` must be
    stated (``"centered"`` or ``"fft"``) rather than guessed — an NPS silently
    off by an ``fftshift`` still yields a plausible-looking d'.
    """
    fr = _frequency_grid(shape, spacing)

    if isinstance(nps, NPSResult):
        if nps.roi_shape != shape:
            raise ValueError(
                f"the NPS was measured on {nps.roi_shape} ROIs but the signal is {shape}; "
                "they must lie on the same grid for the frequency axes to line up"
            )
        if not np.isclose(nps.spacing, spacing):
            raise ValueError(
                f"the NPS was measured at spacing {nps.spacing} mm but the signal is at "
                f"{spacing} mm"
            )
        grid = np.fft.ifftshift(np.asarray(nps.nps, dtype=np.float64))
    elif callable(nps):
        grid = np.asarray(nps(fr), dtype=np.float64)
        if grid.shape != shape:
            raise ValueError(
                f"the nps callable returned shape {grid.shape}, expected {shape}: it must be "
                "a function of the radial-frequency grid it is handed"
            )
    elif np.isscalar(nps):
        level = float(nps)  # type: ignore[arg-type]
        if not np.isfinite(level) or level <= 0.0:
            raise ValueError(f"a scalar (white) NPS must be finite and > 0, got {nps!r}")
        grid = np.full(shape, level, dtype=np.float64)
    else:
        grid = np.asarray(nps, dtype=np.float64)
        if grid.shape != shape:
            raise ValueError(f"the nps array has shape {grid.shape}, expected {shape}")
        if layout == "centered":
            grid = np.fft.ifftshift(grid)
        elif layout != "fft":
            raise ValueError(f"nps_layout must be 'centered' or 'fft', got {layout!r}")

    if not np.all(np.isfinite(grid)):
        raise ValueError("the NPS contains non-finite values")
    if np.any(grid < 0.0):
        raise ValueError("the NPS contains negative values, but it is a power spectrum")
    if require_positive and np.any(grid <= 0.0):
        n_zero = int(np.count_nonzero(grid <= 0.0))
        hint = (
            " The DC bin is one of them, which is exactly what nps_2d leaves behind after "
            "detrending. A prewhitening observer divides by the NPS, so it cannot use a "
            "measured NPS unmodified: pass an analytic NPS model (a callable or a scalar), "
            "or fill the DC bin with whatever noise power at DC you are prepared to assume."
            if grid[0, 0] <= 0.0
            else ""
        )
        raise ValueError(
            f"a prewhitening observer needs a strictly positive NPS, but {n_zero} frequency "
            f"bin(s) are zero or negative.{hint}"
        )
    return grid


def burgess_eye_filter(
    peak_cycles_per_mm: float = 1.0, exponent: float = 1.3
) -> Callable[[np.ndarray], np.ndarray]:
    r"""Human visual-response ("eye") filter, ``E(f) proportional to f^n e^(-c f^2)``.

    Normalised to a peak of 1 at ``peak_cycles_per_mm`` (``c = n / (2 f_p^2)``).
    ``E(0) = 0`` is intended: it discounts the very low frequencies a plain
    matched filter would happily integrate over, and it makes NPWE immune to
    the zeroed DC bin of a measured (detrended) NPS.
    """
    f_peak = float(peak_cycles_per_mm)
    n = float(exponent)
    if not np.isfinite(f_peak) or f_peak <= 0.0:
        raise ValueError(f"peak_cycles_per_mm must be finite and > 0, got {peak_cycles_per_mm!r}")
    if not np.isfinite(n) or n <= 0.0:
        raise ValueError(f"exponent must be finite and > 0, got {exponent!r}")

    def eye(fr: np.ndarray) -> np.ndarray:
        rho = np.asarray(fr, dtype=np.float64) / f_peak
        return rho**n * np.exp(-0.5 * n * (rho**2 - 1.0))  # exactly 1 at f = f_p

    return eye


def _gaussian_auc(d_prime: float) -> float:
    """AUC implied by d' for an equal-variance Gaussian statistic: Phi(d'/sqrt(2))."""
    return float(ndtr(d_prime / np.sqrt(2.0)))


_MIN_NPS_FRACTION = 1e-8


def _dynamic_range(nps_grid: np.ndarray) -> float:
    """``max/min`` of the NPS, reported as ``inf`` when a bin is zero."""
    lo = float(nps_grid.min())
    hi = float(nps_grid.max())
    if lo <= 0.0:
        return float("inf")
    return hi / lo


def _linear_observer(
    name: str,
    signal: np.ndarray,
    nps: NPSResult | np.ndarray | Callable[[np.ndarray], np.ndarray] | float,
    spacing_mm: float,
    *,
    eye_filter: Callable[[np.ndarray], np.ndarray] | None,
    prewhiten: bool,
    nps_layout: str,
    zero_nps_tolerance: float,
    noise_floor: float | None,
) -> ObserverResult:
    """Shared machinery for the closed-form linear observers.

    The sums approximate the continuous integrals with ``S = A * fft2(s)``
    (``A`` the pixel area) and bin width ``du dv = 1/(N A)``; the factors of
    ``A`` cancel exactly in the ratio forming d', which is what makes the
    pixel-domain identity ``d' = ||s||/sigma`` exact rather than approximate.

    The two guards below exist because both failure modes return a plausible
    number rather than an error.
    """
    sig = _as_signal(signal)
    spacing = _check_spacing(spacing_mm)
    ny, nx = sig.shape
    area = spacing * spacing
    du_dv = 1.0 / (ny * nx * area)

    nps_grid = _nps_grid(nps, (ny, nx), spacing, layout=nps_layout, require_positive=prewhiten)
    fr = _frequency_grid((ny, nx), spacing)

    if eye_filter is None:
        eye = np.ones((ny, nx), dtype=np.float64)
    else:
        eye = np.asarray(eye_filter(fr), dtype=np.float64)
        if eye.shape != (ny, nx):
            raise ValueError(f"eye_filter returned shape {eye.shape}, expected {(ny, nx)}")
        if not np.all(np.isfinite(eye)) or np.any(eye < 0.0):
            raise ValueError("eye_filter must return finite, non-negative values")

    spectrum = area * np.fft.fft2(sig)
    power = np.abs(spectrum) ** 2

    nps_max = float(nps_grid.max())
    if nps_max <= 0.0:
        raise ValueError("the NPS is zero everywhere: there is no noise, so d' is infinite")

    if prewhiten:
        # A prewhitening observer weights by 1/NPS, so a noise model whose
        # power decays to (numerically) nothing produces an enormous d' built
        # entirely of bins where the noise power has underflowed and the
        # "signal power" is floating-point rounding. Real noise has a floor.
        floor_applied = None
        if noise_floor is not None:
            floor = float(noise_floor)
            if not (0.0 < floor < 1.0):
                raise ValueError(
                    f"noise_floor is a fraction of the peak NPS and must be in (0, 1), "
                    f"got {noise_floor!r}"
                )
            nps_grid = np.maximum(nps_grid, floor * nps_max)
            floor_applied = floor
        elif float(nps_grid.min()) < _MIN_NPS_FRACTION * nps_max:
            raise ValueError(
                f"the NPS spans a dynamic range of {_dynamic_range(nps_grid):.3g} (min = "
                f"{float(nps_grid.min()):.3g}, max = {nps_max:.3g}), which a prewhitening "
                "observer cannot use: it weights by 1/NPS, so d' would be dominated by "
                "high frequencies where the noise power has decayed to nothing and the "
                "signal power is numerical rounding. Model a noise floor: add a white "
                "component to the NPS, or pass noise_floor=<fraction of peak NPS>."
            )

        # W = S / NPS, so numerator and denominator coincide.
        transfer = 1.0 / nps_grid
        signal_power = float(np.sum(power * transfer) * du_dv)
        noise_power = signal_power
    else:
        floor_applied = None
        # W = S E^2. A measured NPS has a zeroed DC bin (nps_2d detrends),
        # and zeroed bins contribute no noise variance, biasing d' high
        # silently (~3% for a disk signal scored without an eye filter). An
        # eye filter has E(0) = 0 and is immune; raise if the lost weight
        # exceeds the tolerance instead of letting it pass unnoticed.
        transfer = eye**2
        weight = power * eye**4

        zero_bins = nps_grid <= 0.0
        if np.any(zero_bins):
            total = float(weight.sum())
            lost = float(weight[zero_bins].sum()) / total if total > 0.0 else 0.0
            if lost > zero_nps_tolerance:
                dc_note = " (the DC bin is among them)" if zero_bins[0, 0] else ""
                raise ValueError(
                    f"the NPS is zero at frequency bins carrying {lost:.1%} of this "
                    f"observer's noise weight{dc_note}. Those bins would contribute no "
                    f"noise variance, so d' would be biased high by about "
                    f"{1 / np.sqrt(1 - lost) - 1:.1%}. Use an eye filter (E(0) = 0), an "
                    "analytic NPS model, or fill the zeroed bins. Raise "
                    "zero_nps_tolerance only if the scored images are detrended the "
                    "same way the NPS was."
                )

        signal_power = float(np.sum(power * eye**2) * du_dv)
        noise_power = float(np.sum(weight * nps_grid) * du_dv)

    if signal_power <= 0.0:
        raise ValueError(
            "the observer sees no signal power: the eye filter suppresses every "
            "frequency at which the signal has content"
        )
    if noise_power <= 0.0:
        raise ValueError(
            "the observer's noise variance is zero, so d' is undefined: the NPS "
            "vanishes at every frequency where the observer's template has weight"
        )

    d_prime = float(signal_power / np.sqrt(noise_power))
    template = np.real(np.fft.ifft2(np.fft.fft2(sig) * transfer))

    return ObserverResult(
        name=name,
        d_prime=d_prime,
        auc=_gaussian_auc(d_prime),
        template=template,
        signal_power=signal_power,
        noise_power=noise_power,
        spacing=spacing,
        meta={
            "eye_filter": eye_filter is not None,
            "prewhiten": prewhiten,
            "shape": (ny, nx),
            "noise_floor": floor_applied,
            "nps_dynamic_range": _dynamic_range(nps_grid),
        },
    )


def npwe(
    signal: np.ndarray,
    nps: NPSResult | np.ndarray | Callable[[np.ndarray], np.ndarray] | float,
    spacing_mm: float,
    *,
    eye_filter: Callable[[np.ndarray], np.ndarray] | None = None,
    nps_layout: str = "centered",
    zero_nps_tolerance: float = 1e-3,
) -> ObserverResult:
    r"""Non-prewhitening observer with an eye filter (NPWE); ``eye_filter=None``
    gives the plain NPW observer.

    It does **not** invert the noise covariance, which is why it tracks human
    performance where the ideal observer does not. In white noise of SD
    ``sigma`` the plain NPW reduces exactly to ``d' = ||s||_2 / sigma``.

    An eye filter is immune to the zeroed DC bin of a measured NPS (E(0) = 0),
    so NPWE proper can take a measured NPS directly; plain NPW cannot, and
    raises when more than ``zero_nps_tolerance`` of the observer's noise weight
    sits on zeroed bins.
    """
    name = "npwe" if eye_filter is not None else "npw"
    return _linear_observer(
        name,
        signal,
        nps,
        spacing_mm,
        eye_filter=eye_filter,
        prewhiten=False,
        nps_layout=nps_layout,
        zero_nps_tolerance=zero_nps_tolerance,
        noise_floor=None,
    )


def ideal_linear(
    signal: np.ndarray,
    nps: NPSResult | np.ndarray | Callable[[np.ndarray], np.ndarray] | float,
    spacing_mm: float,
    *,
    nps_layout: str = "centered",
    noise_floor: float | None = None,
) -> ObserverResult:
    r"""Prewhitening matched filter — the ideal linear (Hotelling) observer,
    ``d'^2 = int |S|^2 / NPS df``: the upper bound on every linear observer.

    Weighting by 1/NPS means the answer is dominated by whatever frequencies
    have the least noise, so a noise model whose power decays to nothing
    (e.g. a Gaussian-correlated NPS with no white floor) yields a meaningless
    enormous d'. This raises when the NPS dynamic range exceeds 1e8 unless a
    ``noise_floor`` (a fraction of the peak NPS, in (0, 1)) is given, and
    raises on any zero NPS bin.
    """
    return _linear_observer(
        "ideal_linear",
        signal,
        nps,
        spacing_mm,
        eye_filter=None,
        prewhiten=True,
        nps_layout=nps_layout,
        zero_nps_tolerance=0.0,
        noise_floor=noise_floor,
    )


# --------------------------------------------------------------------------------------
# scoring and figures of merit
# --------------------------------------------------------------------------------------


def score_images(images: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Apply a spatial template: ``lambda_n = sum_i w_i g_{n,i}``.

    ``images`` is one image ``(ny, nx)`` or a stack ``(n, ny, nx)``; the
    template must match the image shape. Returns scores of shape ``(n,)``.
    """
    imgs = np.asarray(images, dtype=np.float64)
    tmpl = np.asarray(template, dtype=np.float64)
    if imgs.ndim == 2:
        imgs = imgs[None, ...]
    if imgs.ndim != 3:
        raise ValueError(f"images must have shape (ny, nx) or (n, ny, nx), got {imgs.shape}")
    if tmpl.shape != imgs.shape[1:]:
        raise ValueError(
            f"template shape {tmpl.shape} does not match the image shape {imgs.shape[1:]}"
        )
    if not np.all(np.isfinite(imgs)) or not np.all(np.isfinite(tmpl)):
        raise ValueError("images and template must be finite")
    return imgs.reshape(imgs.shape[0], -1) @ tmpl.reshape(-1)


def d_prime_from_scores(present: np.ndarray, absent: np.ndarray) -> float:
    r"""Empirical detectability from two score samples with pooled variance.

    ``d' = (mean1 - mean0) / sqrt(0.5 (s1^2 + s0^2))`` with unbiased sample
    variances. For the linear observers this must agree with the closed form —
    the Monte-Carlo tests hold it to that.
    """
    p = np.asarray(present, dtype=np.float64).ravel()
    a = np.asarray(absent, dtype=np.float64).ravel()
    if p.size < 2 or a.size < 2:
        raise ValueError(
            f"need at least 2 scores per class to estimate a variance, got {p.size} "
            f"present and {a.size} absent"
        )
    if not np.all(np.isfinite(p)) or not np.all(np.isfinite(a)):
        raise ValueError("scores contain non-finite values")
    pooled = 0.5 * (p.var(ddof=1) + a.var(ddof=1))
    if pooled <= 0.0:
        raise ValueError(
            "both score distributions have zero variance, so d' is undefined (noise-free images?)"
        )
    return float((p.mean() - a.mean()) / np.sqrt(pooled))


def auc_from_scores(present: np.ndarray, absent: np.ndarray) -> float:
    """Area under the ROC curve, exactly, via the Mann-Whitney U statistic —
    the proportion of present/absent pairs ordered correctly, ties counting
    half. No threshold sweep, no equal-variance Gaussian assumption."""
    p = np.asarray(present, dtype=np.float64).ravel()
    a = np.asarray(absent, dtype=np.float64).ravel()
    if p.size == 0 or a.size == 0:
        raise ValueError("need at least one score in each class")
    if not np.all(np.isfinite(p)) or not np.all(np.isfinite(a)):
        raise ValueError("scores contain non-finite values")

    ranks = _average_ranks(np.concatenate([p, a]))
    u = ranks[: p.size].sum() - p.size * (p.size + 1) / 2.0
    return float(u / (p.size * a.size))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """1-based ranks, with tied values sharing their average rank."""
    order = np.argsort(values, kind="stable")
    sorted_vals = values[order]
    ranks = np.empty(values.size, dtype=np.float64)
    i = 0
    while i < values.size:
        j = i
        while j + 1 < values.size and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        ranks[order[i : j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


# --------------------------------------------------------------------------------------
# channelized Hotelling observer (Sprint-5 freeze, PROTOCOL_FREEZE.md S5-2)
# --------------------------------------------------------------------------------------


def gabor_channel_bank(
    roi_shape: tuple[int, int],
    spacing_mm: float,
    frequencies_cyc_mm: tuple[float, ...] = (0.25, 0.5, 0.75),
    orientations_deg: tuple[float, ...] = (0.0, 60.0, 120.0),
) -> np.ndarray:
    """Gabor channel bank for the CHO, centred on the ROI.

    Each channel is ``exp(-r^2 / (2 sigma^2)) * cos(2 pi f u)`` with the
    one-wavelength envelope ``sigma = 1 / f`` (frozen S5-2) and
    ``u = x cos(theta) + y sin(theta)`` the on-frequency coordinate in mm.
    Channel scale is arbitrary: scaling a channel scales its response and
    its covariance row/column together, leaving d' invariant.

    Frequencies must stay below the pixel Nyquist (``f < 1 / (2 spacing)``);
    at exactly one cycle per pixel the carrier degenerates to a constant
    and same-frequency channels become linearly dependent (found by the
    covariance singularity guard — a 1 cy/px carrier samples cos(2 pi k) = 1
    at every pixel, erasing the orientation dependence).
    """
    ny, nx = (int(v) for v in roi_shape)
    if ny < 4 or nx < 4:
        raise ValueError(f"roi_shape must be at least 4x4, got {roi_shape}")
    spacing = _check_spacing(spacing_mm)
    nyquist = 1.0 / (2.0 * spacing)
    y, x = np.mgrid[0:ny, 0:nx]
    xm = (x - (nx - 1) / 2.0) * spacing
    ym = (y - (nx - 1) / 2.0) * spacing
    r2 = xm**2 + ym**2
    chans: list[np.ndarray] = []
    for f in frequencies_cyc_mm:
        f = float(f)
        if not np.isfinite(f) or f <= 0.0:
            raise ValueError(f"frequencies must be positive, got {f!r}")
        if f >= nyquist:
            raise ValueError(
                f"channel frequency {f} cy/mm is at or above the pixel Nyquist "
                f"({nyquist} cy/mm): the carrier is not representable on this grid"
            )
        env = np.exp(-r2 / (2.0 * (1.0 / f) ** 2))
        for th in orientations_deg:
            u = xm * np.cos(np.radians(th)) + ym * np.sin(np.radians(th))
            chans.append(env * np.cos(2.0 * np.pi * f * u))
    return np.stack(chans)


def cho(
    signal: np.ndarray,
    rois: np.ndarray,
    spacing_mm: float,
    channels: np.ndarray,
) -> ObserverResult:
    r"""Channelized Hotelling observer d' for an SKE/BKE task.

    Channel responses are Riemann-sum inner products over the ROI
    (``spacing^2`` factor included on both signal and noise sides, so it
    cancels in d' but keeps the units of the covariance consistent).
    Noise ROIs are mean-detrended exactly as in :func:`nps_2d` (the frozen
    background model is a uniform field); the channel covariance uses the
    unbiased ``ddof=1`` estimate across the ensemble. With
    ``d'^2 = s^T C^{-1} s`` the template in image space is
    ``sum_c w_c channel_c`` with ``w = C^{-1} s_channels``.

    Guards: raises if the signal is identically zero, if a channel is
    identically zero, or if the covariance is not positive definite
    (e.g. fewer independent ROIs than channels) — a pseudo-d' from a
    regularised inverse is not reported.
    """
    sig = _as_signal(signal)
    spacing = _check_spacing(spacing_mm)
    ch = np.asarray(channels, dtype=np.float64)
    if ch.ndim != 3 or ch.shape[1:] != sig.shape:
        raise ValueError(
            f"channels must have shape (n_channels, {sig.shape[0]}, {sig.shape[1]}), got {ch.shape}"
        )
    if not np.all(np.isfinite(ch)):
        raise ValueError("channels contain non-finite values")
    if not np.all(np.any(ch != 0.0, axis=(-2, -1))):
        raise ValueError("every channel must be non-zero somewhere")

    arr = np.asarray(rois, dtype=np.float64)
    if arr.ndim == 2:
        arr = arr[None, ...]
    if arr.ndim != 3 or arr.shape[1:] != sig.shape:
        raise ValueError(
            f"rois must have shape (n, {sig.shape[0]}, {sig.shape[1]}), got {arr.shape}"
        )
    if arr.shape[0] < ch.shape[0] + 1:
        raise ValueError(
            f"need at least n_channels+1 ROIs to estimate the covariance, "
            f"got {arr.shape[0]} ROIs for {ch.shape[0]} channels"
        )

    resid = arr - arr.mean(axis=(-2, -1), keepdims=True)
    a2 = spacing * spacing
    t = np.einsum("rxy,cxy->rc", resid, ch) * a2
    s_ch = np.einsum("xy,cxy->c", sig, ch) * a2

    # np.cov returns a scalar for a single channel — normalise to 2-D.
    cov = np.atleast_2d(np.cov(t, rowvar=False, ddof=1))
    try:
        w = np.linalg.solve(cov, s_ch)
    except np.linalg.LinAlgError as exc:
        raise ValueError(
            "channel covariance is not positive definite; the ensemble cannot "
            "support the CHO (more ROIs or fewer channels)"
        ) from exc
    d2 = float(s_ch @ w)
    if d2 < 0.0:
        raise ValueError(f"CHO signal power is negative ({d2}); covariance not PD")
    d_prime = float(np.sqrt(d2))
    template = np.einsum("c,cxy->xy", w, ch)

    return ObserverResult(
        name="cho",
        d_prime=d_prime,
        auc=float(ndtr(d_prime / np.sqrt(2.0))),
        template=template,
        signal_power=d2,
        noise_power=1.0,  # absorbed: d'^2 = s^T C^{-1} s is already normalised
        spacing=spacing,
        meta={
            "n_channels": int(ch.shape[0]),
            "n_rois": int(arr.shape[0]),
            "channel_responses": s_ch.tolist(),
        },
    )
