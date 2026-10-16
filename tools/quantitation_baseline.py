"""Iodine-quantitation baseline for the frozen study configuration.

Separates, per insert size x concentration x position:

- noise-free recovery (decomposition-approximation + partial-volume bias)
- repeated-noise total error (mean +/- SD over R replicates) at 100% / 25% dose

AI-induced changes in later sprints are measured AGAINST this baseline, so
denoiser effects are never confounded with the simulator's own systematic
error.

Chunked execution (each chunk stays within a few minutes):

    python tools/quantitation_baseline.py --start 0 --stop 4
    python tools/quantitation_baseline.py --start 4 --stop 8
    python tools/quantitation_baseline.py --merge

Outputs ``results/quantitation_baseline.json``.
"""

from __future__ import annotations

import argparse
import json
import time
from itertools import product
from pathlib import Path

import numpy as np

from pcctvmi.forward import REFERENCE_N0, simulate
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum
from pcctvmi.vmi import decompose

OUT = Path(__file__).resolve().parent.parent / "results"
FINAL = OUT / "quantitation_baseline.json"
SIZES_CM = (0.3, 0.5, 0.8)  # frozen lesion sizes
CONCENTRATIONS = (0.0005, 0.001, 0.002, 0.005)  # g/cm^3 (0.5-5 mgI/mL)
# Insert ring radii: "central" (r=3 cm) vs "peripheral" (r=8 cm). r=0 would
# stack all three inserts on top of each other; 3 cm keeps every insert far
# from both the centre line artefacts and the water edge.
RADII_CM = (3.0, 8.0)
REPLICATES = 6
DOSE_LEVELS = (1.0, 0.25)
N = 512
THETA = np.linspace(0.0, 360.0, 180, endpoint=False)
SEED_BASE = 20261016
ANGLES = (0.0, 120.0, 240.0)


def _configs() -> list[tuple[float, float]]:
    return [(r, c) for r, c in product(RADII_CM, CONCENTRATIONS)]


def _roi(img: np.ndarray, radius_cm: float, angle_deg: float, r_cm: float) -> float:
    cy = cx = N // 2
    px = 0.05
    py = int(round(cy + (r_cm * np.sin(np.deg2rad(angle_deg))) / px))
    px_i = int(round(cx + (r_cm * np.cos(np.deg2rad(angle_deg))) / px))
    rad = max(2, int(round((radius_cm / 2.0) / px * 0.8)))
    yy, xx = np.mgrid[0:N, 0:N]
    mask = (yy - py) ** 2 + (xx - px_i) ** 2 <= rad**2
    return float(np.mean(img[mask]))


def _phantom(r_cm: float, conc: float):
    inserts = tuple(
        Insert(
            x_cm=r_cm * np.cos(np.deg2rad(a)),
            y_cm=r_cm * np.sin(np.deg2rad(a)),
            diameter_cm=s,
            iodine_g_cm3=conc,
        )
        for a, s in zip(ANGLES, SIZES_CM, strict=True)
    )
    return make_water_cylinder_phantom(n=N, diameter_cm=25.0, pixel_size_cm=0.05, inserts=inserts)


def run_chunk(start: int, stop: int) -> list[dict]:
    spec = Spectrum.from_csv()
    rows = []
    for cfg_idx in range(start, stop):
        r_cm, conc = _configs()[cfg_idx]
        t0 = time.time()
        ph = _phantom(r_cm, conc)
        res = simulate(
            spec,
            ph,
            theta_deg=THETA,
            thresholds_kev=(30.0,),
            n0=REFERENCE_N0,
            seed=SEED_BASE + cfg_idx * 1000,
        )
        mus = reconstruct_bins(res, use_expected=True)
        _, b_clean = decompose(mus, res.mu_eff)
        row: dict = {
            "config_index": cfg_idx,
            "radius_cm": r_cm,
            "concentration_g_cm3": conc,
            "noise_free": {
                str(s): _roi(b_clean, s, a, r_cm) for s, a in zip(SIZES_CM, ANGLES, strict=True)
            },
            "noisy": {},
        }
        for dose in DOSE_LEVELS:
            per_size: dict[str, list[float]] = {str(s): [] for s in SIZES_CM}
            for rep in range(REPLICATES):
                res_n = simulate(
                    spec,
                    ph,
                    theta_deg=THETA,
                    thresholds_kev=(30.0,),
                    n0=dose * REFERENCE_N0,
                    seed=SEED_BASE + cfg_idx * 1000 + 1 + rep,
                )
                mus_n = reconstruct_bins(res_n)
                _, b_n = decompose(mus_n, res_n.mu_eff)
                for s, a in zip(SIZES_CM, ANGLES, strict=True):
                    per_size[str(s)].append(_roi(b_n, s, a, r_cm))
            row["noisy"][f"dose_{dose:g}"] = {
                s: {"mean": float(np.mean(v)), "sd": float(np.std(v))} for s, v in per_size.items()
            }
        rows.append(row)
        print(f"[{cfg_idx}] r={r_cm} cm, conc={conc:g}: {time.time() - t0:.1f} s")
    return rows


def merge(parts: list[list[dict]]) -> dict:
    rows = sorted((r for part in parts for r in part), key=lambda r: r["config_index"])
    return {
        "config": {
            "n": N,
            "angles": int(THETA.size),
            "reference_n0": REFERENCE_N0,
            "sizes_cm": list(SIZES_CM),
            "concentrations_g_cm3": list(CONCENTRATIONS),
            "radii_cm": list(RADII_CM),
            "replicates": REPLICATES,
            "dose_levels": list(DOSE_LEVELS),
            "seed_base": SEED_BASE,
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--stop", type=int, default=None)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    if args.merge:
        parts = []
        for path in sorted(OUT.glob("quantitation_baseline_part*.json")):
            parts.append(json.loads(path.read_text(encoding="utf-8")))
            print(f"loaded {path.name}")
        result = merge(parts)
        FINAL.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {FINAL}")
        return

    total = len(_configs())
    start = 0 if args.start is None else args.start
    stop = total if args.stop is None else args.stop
    rows = run_chunk(start, stop)
    part = OUT / f"quantitation_baseline_part{start:02d}_{stop:02d}.json"
    part.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"wrote {part}")


if __name__ == "__main__":
    main()
