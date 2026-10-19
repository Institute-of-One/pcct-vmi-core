"""Generate the frozen training set for the VMI denoiser (S3-5).

192 phantoms, each a 25 cm water cylinder on the frozen 512^2 grid with 0 to
5 random iodine inserts (diameter 0.2-1.0 cm, concentration 0.5-5 mgI/mL,
non-overlapping, kept away from the water edge). Each phantom contributes one
noise realisation at a dose sampled uniformly from 25-100% (eval conditions
100%/25% are inside the range). Both the noisy decomposition (a, b) and the
noiseless teacher (same simulation's expected-count path) are stored.

Seed base 20261019 — fully separated from the evaluation seeds (20261016 /
20261017) per the Sprint-3 freeze (PROTOCOL_FREEZE.md S3-5, §5).

One simulate() call serves both teacher and input: the noisy decomposition
comes from the Poisson counts, the teacher from the expected counts of the
same result.

Chunked execution (~32 samples per chunk, ~2 minutes each):

    python tools/make_training_data.py --start 0 --stop 32
    python tools/make_training_data.py --start 32 --stop 64
    ...
    python tools/make_training_data.py --start 160 --stop 192

Outputs ``data/training/sample_{idx:04d}.npz`` (gitignored; regenerable).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from pcctvmi.forward import REFERENCE_N0, areal_density_projections, simulate
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum
from pcctvmi.vmi import decompose

OUT = Path(__file__).resolve().parent.parent / "data" / "training"
N_SAMPLES = 192
N = 512
PX = 0.05
WATER_DIAMETER_CM = 25.0
WATER_RADIUS_CM = WATER_DIAMETER_CM / 2.0
# Inserts stay this far from the water edge and from each other (cm).
EDGE_MARGIN_CM = 1.5
INSERT_MARGIN_CM = 0.2
MAX_INSERTS = 5
DIAMETER_RANGE_CM = (0.2, 1.0)
CONC_RANGE_G_CM3 = (0.0005, 0.005)  # 0.5-5 mgI/mL
DOSE_RANGE = (0.25, 1.0)
THETA = np.linspace(0.0, 360.0, 180, endpoint=False)
SEED_BASE = 20261019  # S3-5; evaluation uses 20261016/20261017 — no overlap.


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


def run_chunk(start: int, stop: int) -> None:
    spec = Spectrum.from_csv()
    OUT.mkdir(parents=True, exist_ok=True)
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
            thresholds_kev=(30.0,),
            n0=dose * REFERENCE_N0,
            seed=SEED_BASE + idx,
            projections=projections,
        )
        a_clean, b_clean = decompose(reconstruct_bins(res, use_expected=True), res.mu_eff)
        a_noisy, b_noisy = decompose(reconstruct_bins(res, use_expected=False), res.mu_eff)
        path = OUT / f"sample_{idx:04d}.npz"
        np.savez_compressed(
            path,
            a_noisy=a_noisy.astype(np.float16),
            b_noisy=b_noisy.astype(np.float16),
            a_clean=a_clean.astype(np.float32),
            b_clean=b_clean.astype(np.float32),
        )
        meta = {
            "index": idx,
            "seed": SEED_BASE + idx,
            "dose_fraction": dose,
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
