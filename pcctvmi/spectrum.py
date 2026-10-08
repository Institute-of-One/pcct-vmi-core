"""X-ray spectrum model for the polyenergetic forward simulation."""

from __future__ import annotations

import csv
import io
from importlib import resources

import numpy as np


class Spectrum:
    """Discrete X-ray spectrum: relative fluence per energy bin (keV)."""

    def __init__(self, energies_kev: np.ndarray, weights: np.ndarray) -> None:
        e = np.asarray(energies_kev, dtype=np.float64)
        w = np.asarray(weights, dtype=np.float64)
        if e.ndim != 1 or w.ndim != 1 or e.shape != w.shape or e.size == 0:
            raise ValueError("energies and weights must be non-empty 1-D arrays of equal length")
        if np.any(~np.isfinite(e)) or np.any(~np.isfinite(w)):
            raise ValueError("energies and weights must be finite")
        if np.any(e <= 0) or np.any(np.diff(e) <= 0):
            raise ValueError("energies must be positive and strictly increasing")
        if np.any(w < 0):
            raise ValueError("weights must be non-negative")
        total = float(w.sum())
        if total <= 0:
            raise ValueError("spectrum has zero total fluence")
        self.energies_kev = e.copy()
        self.fluence = w.copy()  # relative units; normalisation cancels in ratios
        self._norm = total

    @classmethod
    def mono(cls, energy_kev: float) -> Spectrum:
        """Degenerate single-energy spectrum (closed-form validation path)."""
        if energy_kev <= 0:
            raise ValueError("energy must be positive")
        return cls(np.array([float(energy_kev)]), np.array([1.0]))

    @classmethod
    def from_csv(cls, name: str = "spectrum_120kvp.csv") -> Spectrum:
        ref = resources.files("pcctvmi.data").joinpath(name)
        text = ref.read_text(encoding="utf-8")
        energies: list[float] = []
        fluence: list[float] = []
        for row in csv.DictReader(io.StringIO(text, newline="")):
            energies.append(float(row["energy_keV"]))
            fluence.append(float(row["photons"]))
        return cls(np.asarray(energies), np.asarray(fluence))

    @property
    def n_energies(self) -> int:
        return int(self.energies_kev.size)

    @property
    def max_energy_kev(self) -> float:
        return float(self.energies_kev.max())

    @property
    def min_energy_kev(self) -> float:
        return float(self.energies_kev.min())

    def normalized(self) -> np.ndarray:
        """Fluence normalised to sum to 1."""
        return self.fluence / self._norm

    def bin_masks(self, thresholds_kev: tuple[float, ...] = (30.0,)) -> list[np.ndarray]:
        """Boolean masks selecting each photon-counting bin.

        With thresholds (t1, t2, ...), bin k collects energies in
        [t_k, t_{k+1}) and the last bin collects [t_last, infinity).
        An empty threshold tuple yields a single bin over all energies (EID).
        """
        edges = [self.min_energy_kev - 1e-9, *thresholds_kev]
        for t in thresholds_kev:
            if not self.min_energy_kev < t < self.max_energy_kev:
                raise ValueError(
                    f"threshold {t} keV outside spectrum range "
                    f"({self.min_energy_kev}, {self.max_energy_kev})"
                )
        edges.append(self.max_energy_kev + 1e-9)
        masks = []
        for lo, hi in zip(edges[:-1], edges[1:], strict=True):
            masks.append((self.energies_kev >= lo) & (self.energies_kev < hi))
        return masks

    def effective_mu_rho(
        self,
        thresholds_kev: tuple[float, ...],
        reference_water_path_cm: float,
        materials: tuple[str, ...] = ("water", "iodine"),
    ) -> list[dict[str, float]]:
        """Transmission-weighted effective mass attenuation per bin.

        Weight per energy: fluence x exp(-mu/rho_water(E) x path). The linear
        forward model uses these effective coefficients for the basis
        decomposition; residual spectral non-linearity appears physically as
        beam-hardening bias.
        """
        from pcctvmi.materials import mu_rho

        if reference_water_path_cm < 0:
            raise ValueError("reference water path must be non-negative")
        trans = np.exp(-mu_rho("water", self.energies_kev) * reference_water_path_cm)
        out: list[dict[str, float]] = []
        for mask in self.bin_masks(thresholds_kev):
            w = self.fluence * trans * mask
            denom = float(w.sum())
            if denom <= 0:
                raise ValueError("bin has zero reference transmission weight")
            out.append(
                {m: float((w * mu_rho(m, self.energies_kev)).sum() / denom) for m in materials}
            )
        return out
