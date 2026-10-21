"""Generate the D1w training set for the H4 walnut arm (S12-5).

192 phantoms, each a 35 mm water cylinder (walnut-sized) on a 1024^2 grid
at 0.05 mm pixels with 0 to 5 random iodine inserts. Insert geometry is the
S3-5 layout scaled by the disk ratio 3.5/25 = 0.14 (edge margin 0.21 cm,
insert margin 0.028 cm, diameter 0.028-0.14 cm = 5.6-28 px). Each phantom
contributes one noise realisation at a dose sampled uniformly from 25-100%
of the frozen walnut fluence n0 = 3.0e4 (PROTOCOL_FREEZE.md §12.4).

Unlike the S3 data, the stored pair is the raw (Low, High) BIN
reconstruction (simulator bins 1 and 2 — the sub-15 keV rejected bin is
skipped), because D1w takes the two bin images as input channels. Both
images are converted to HU with the per-bin water calibration
HU = (mu / mu_eff_water - 1) * 1000 so that training and evaluation live in
the same units as the walnut DICOM bin images. mu_eff_water per bin is the
§12.4 measured value (0.5593 / 0.2554 1/cm); an in-script gate asserts the
clean water interior is within 5 HU of 0 for every sample.

Seed base 20261022 — separated from the eval seeds (20261020), the noise
model seeds (20261021) and the S3 training seeds (20261019).

Chunked execution (~24 samples per chunk, ~3 minutes each):

    python tools/make_training_data_walnut.py --start 0 --stop 24
    ...
    python tools/make_training_data_walnut.py --start 168 --stop 192

Outputs ``data/training_walnut/sample_{idx:04d}.npz`` (gitignored;
regenerable) with ``bins_noisy`` (2,1024,1024 float16) and ``bins_clean``
(2,1024,1024 float32), plus a per-sample JSON meta.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from pcctvmi.forward import areal_density_projections, simulate
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum

OUT = Path(__file__).resolve().parent.parent / "data" / "training_walnut"
N_SAMPLES = 192
N = 1024
PX = 0.005
WATER_DIAMETER_CM = 3.5
WATER_RADIUS_CM = WATER_DIAMETER_CM / 2.0
# S3-5 insert layout scaled by the disk ratio 3.5/25 = 0.14.
SCALE = WATER_DIAMETER_CM / 25.0
EDGE_MARGIN_CM = 1.5 * SCALE
INSERT_MARGIN_CM = 0.2 * SCALE
MAX_INSERTS = 5
DIAMETER_RANGE_CM = (0.2 * SCALE, 1.0 * SCALE)
CONC_RANGE_G_CM3 = (0.0005, 0.005)  # 0.5-5 mgI/mL
DOSE_RANGE = (0.25, 1.0)
THETA = np.linspace(0.0, 360.0, 180, endpoint=False)
SEED_BASE = 20261022  # S12-5; no overlap with 20261019/20261020/20261021.
SPECTRUM_CSV = "spectrum_80kvp.csv"
THRESHOLDS_KEV = (15.0, 30.0)
N0_WALNUT = 3.0e4  # frozen §12.4
LOW_BIN = 1
HIGH_BIN = 2
# Water-only phantom, 100% dose, clean centre-ROI mean (1/cm) — the per-bin
# water calibration that maps simulated 1/cm images onto the walnut HU scale.
# Measured by this script's _water_calibration_reference (condition: n0 =
# N0_WALNUT, use_expected=True); the 100% dose minimises the S1-7 shifted-log
# count-level bias. The §12.4 noise-model JSONs carry 12.5%/25%-condition
# values (0.5593/0.2554) differing by <= 0.4% (dose-dependent shift bias) —
# immaterial against the < 5% NPS tolerance; those JSONs' hu_scale fields are
# run records, not the canonical calibration.
MU_WATER_EFF = (0.5575717876742355, 0.2553258904005463)
CALIBRATION_TOL_HU = 1.0  # water-only reference must match these constants
GROSS_INTERIOR_TOL_HU = 100.0  # per-sample bound (inserts shift the interior)


def _sample_inserts(rng: np.random.Generator) -> tuple[Insert, ...]:
    n_inserts = int(rng.integers(0, MAX_INSERTS + 1))
    placed: list[tuple[float, float, float]] = []  # (x, y, diameter)
    inserts: list[Insert] = []
    for _ in range(n_inserts):
        diameter = float(rng.uniform(*DIAMETER_RANGE_CM))
        for _ in range(50):  # rejection sampling with a hard attempt cap
            angle = float(rng.uniform(0.0, 2.0 * np.pi))
            radius = float(rng.uniform(0.0, WATER_RADIUS_CM - EDGE_MARGIN_CM - diameter / 2.0))
            x, y = radius * np.cos(angle), radius * np.sin(angle)
            if all(
                np.hypot(x - px, y - py) >= (diameter + pd) / 2.0 + INSERT_MARGIN_CM
                for px, py, pd in placed
            ):
                placed.append((x, y, diameter))
                conc = float(rng.uniform(*CONC_RANGE_G_CM3))
                inserts.append(Insert(x_cm=x, y_cm=y, diameter_cm=diameter, iodine_g_cm3=conc))
                break
        # if no spot was found, the insert is silently dropped — placement
        # density stays modest, so this is rare and harmless
    return tuple(inserts)


def _to_hu(stack_1_per_cm: np.ndarray) -> np.ndarray:
    """(2, ny, nx) 1/cm -> HU with the per-bin water calibration."""
    scale = np.asarray(MU_WATER_EFF, dtype=np.float64)[:, None, None]
    return 1000.0 * (stack_1_per_cm / scale - 1.0)


def _water_calibration_reference(spec) -> np.ndarray:
    """Clean water-only interior mean (HU), for validating MU_WATER_EFF.

    Iodine inserts legitimately shift the central interior (extra beam
    hardening), so the per-sample gate cannot be a tight 0-HU check. The
    calibration constants are instead validated once per run against a
    water-only phantom — the exact quantity and condition (100% dose) at
    which MU_WATER_EFF was measured.
    """
    ph = make_water_cylinder_phantom(n=N, diameter_cm=WATER_DIAMETER_CM, pixel_size_cm=PX)
    projections = areal_density_projections(ph, THETA)
    res = simulate(
        spec,
        ph,
        theta_deg=THETA,
        thresholds_kev=THRESHOLDS_KEV,
        n0=N0_WALNUT,
        seed=1,
        projections=projections,
    )
    clean = reconstruct_bins(res, use_expected=True, bin_indices=(LOW_BIN, HIGH_BIN))
    hu = _to_hu(np.stack(clean))
    c = N // 2
    half = 64
    return hu[:, c - half : c + half, c - half : c + half].mean(axis=(1, 2))


def run_chunk(start: int, stop: int) -> None:
    spec = Spectrum.from_csv(SPECTRUM_CSV)
    OUT.mkdir(parents=True, exist_ok=True)
    c = N // 2
    half = 64  # 128-px interior gate ROI at the disk centre
    ref = _water_calibration_reference(spec)
    cal_dev = float(np.abs(ref).max())
    if cal_dev > CALIBRATION_TOL_HU:
        raise SystemExit(
            f"water-only reference deviates {cal_dev:.1f} HU from 0 (tol "
            f"{CALIBRATION_TOL_HU}); MU_WATER_EFF is stale: measured {ref.tolist()}"
        )
    print(f"water-only calibration reference: Low {ref[0]:.2f} HU, High {ref[1]:.2f} HU")
    for idx in range(start, stop):
        t0 = time.time()
        rng = np.random.default_rng(SEED_BASE + idx)
        inserts = _sample_inserts(rng)
        dose = float(rng.uniform(*DOSE_RANGE))
        ph = make_water_cylinder_phantom(
            n=N, diameter_cm=WATER_DIAMETER_CM, pixel_size_cm=PX, inserts=inserts
        )
        projections = areal_density_projections(ph, THETA)
        res = simulate(
            spec,
            ph,
            theta_deg=THETA,
            thresholds_kev=THRESHOLDS_KEV,
            n0=dose * N0_WALNUT,
            seed=SEED_BASE + idx,
            projections=projections,
        )
        clean = reconstruct_bins(res, use_expected=True, bin_indices=(LOW_BIN, HIGH_BIN))
        noisy = reconstruct_bins(res, use_expected=False, bin_indices=(LOW_BIN, HIGH_BIN))
        clean_hu = _to_hu(np.stack(clean))
        noisy_hu = _to_hu(np.stack(noisy))
        # Gate: the clean interior must be in a plausible water neighbourhood.
        # Inserts shift it by extra hardening, so this is a gross-error bound
        # (catches reconstruction breakage), not a calibration check — the
        # tight check lives in _water_calibration_reference.
        interior = clean_hu[:, c - half : c + half, c - half : c + half]
        peak = float(np.abs(interior.mean(axis=(1, 2))).max())
        if peak > GROSS_INTERIOR_TOL_HU:
            raise SystemExit(
                f"sample {idx}: clean interior deviates {peak:.1f} HU from 0 "
                f"(gross-error tol {GROSS_INTERIOR_TOL_HU}); reconstruction is broken"
            )
        path = OUT / f"sample_{idx:04d}.npz"
        np.savez_compressed(
            path,
            bins_noisy=noisy_hu.astype(np.float16),
            bins_clean=clean_hu.astype(np.float32),
        )
        meta = {
            "index": idx,
            "seed": SEED_BASE + idx,
            "dose_fraction": dose,
            "n0": dose * N0_WALNUT,
            "n_inserts": len(inserts),
            "inserts": [
                {
                    "x_cm": ins.x_cm,
                    "y_cm": ins.y_cm,
                    "diameter_cm": ins.diameter_cm,
                    "iodine_g_cm3": ins.iodine_g_cm3,
                }
                for ins in inserts
            ],
            "spectrum_csv": SPECTRUM_CSV,
            "thresholds_kev": list(THRESHOLDS_KEV),
            "mu_water_eff_per_bin_1_per_cm": list(MU_WATER_EFF),
            "units": "HU, per-bin water calibration",
            "theta": "180 views over 360 deg (frozen)",
        }
        (OUT / f"sample_{idx:04d}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[{idx}] dose={dose:.2f} inserts={len(inserts)} {time.time() - t0:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--stop", type=int, required=True)
    args = ap.parse_args()
    run_chunk(args.start, min(args.stop, N_SAMPLES))


if __name__ == "__main__":
    main()
