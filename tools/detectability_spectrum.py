"""Detectability spectrum d'(E) of iodine inserts on the frozen VMI grid (H1).

For each insert size (0.3/0.5/0.8 cm at 5 mgI/mL, r = 3 cm), dose level
(100% / 25%), and keV level of the frozen 40-190 keV grid:

- signal: noiseless-VMI difference, insert ROI minus the 180-degree mirrored
  background ROI (SKE/BKE; mirror position shares the water path-length
  distribution by rotational symmetry — see PROTOCOL_FREEZE.md S2-3)
- noise: ensemble NPS (R = 64 noise realisations) of the mirrored ROI
- observers: NPWE (primary) and the ideal linear observer (upper bound)

Concentration is measured at 5 mgI/mL only: VMI HU is linear in iodine
density and the background NPS is independent of the insert concentration, so
d'(conc) = d'(0.005 g/cm^3) * conc / 0.005 exactly. The scaling law is
recorded in the output rather than re-measured.

Chunked execution (each chunk is one size x dose group, ~2 minutes; groups
are never split, so every part file is a complete condition):

    python tools/detectability_spectrum.py --start 0 --stop 2
    python tools/detectability_spectrum.py --start 2 --stop 4
    python tools/detectability_spectrum.py --start 4 --stop 6
    python tools/detectability_spectrum.py --merge [--plot]

Outputs ``results/detectability_spectrum.json`` and (with --plot)
``results/detectability_spectrum.png``.
"""

from __future__ import annotations

import argparse
import json
import time
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pcctvmi.forward import REFERENCE_N0, areal_density_projections, simulate
from pcctvmi.observers import burgess_eye_filter, ideal_linear, nps_2d, npwe
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum
from pcctvmi.vmi import VMI_GRID_KEV, decompose, vmi_stack

OUT = Path(__file__).resolve().parent.parent / "results"
FINAL = OUT / "detectability_spectrum.json"
SIZES_CM = (0.3, 0.5, 0.8)  # frozen lesion sizes
CONC_G_CM3 = 0.005  # 5 mgI/mL; other concentrations follow by linear scaling
RADIUS_CM = 3.0  # central ring, same as quantitation baseline
DOSE_LEVELS = (1.0, 0.25)
REPLICATES = 64  # S2-7
N = 512
PX_CM = 0.05
SPACING_MM = PX_CM * 10.0  # 0.5 mm (S2-1 conversion at the module boundary)
ROI = 32  # 32x32 px = 1.6 cm square (S2-4)
THETA = np.linspace(0.0, 360.0, 180, endpoint=False)
SEED_BASE = 20261017  # S2-7
HALF = ROI // 2

# Chunk unit: one (size, dose) group, complete. Groups are never split.
GROUPS = list(product(range(len(SIZES_CM)), DOSE_LEVELS))


def _phantom(size_cm: float):
    return make_water_cylinder_phantom(
        n=N,
        diameter_cm=25.0,
        pixel_size_cm=PX_CM,
        inserts=(Insert(x_cm=RADIUS_CM, y_cm=0.0, diameter_cm=size_cm, iodine_g_cm3=CONC_G_CM3),),
    )


def _roi(img: np.ndarray, x_cm: float, y_cm: float) -> np.ndarray:
    """32x32 ROI centred on the (x, y) cm position relative to the FOV centre."""
    cx = x_cm / PX_CM + N / 2.0
    cy = y_cm / PX_CM + N / 2.0
    icx, icy = int(round(cx)), int(round(cy))
    return img[icy - HALF : icy + HALF, icx - HALF : icx + HALF]


def _vmi_stack_from(result, *, noiseless: bool) -> np.ndarray:
    mus = reconstruct_bins(result, use_expected=noiseless)
    a, b = decompose(mus, result.mu_eff)
    return vmi_stack(a, b)


def run_chunk(start: int, stop: int) -> list[dict]:
    spec = Spectrum.from_csv()
    eye = burgess_eye_filter()
    part: list[dict] = []
    # Chunks are whole (size, dose) groups: one noiseless reference plus the
    # full replicate ensemble of mirror ROIs, then observe once per keV.
    for s_idx, dose in GROUPS[start:stop]:
        t0 = time.time()
        size_cm = SIZES_CM[s_idx]
        ph = _phantom(size_cm)
        # The projections are deterministic in the phantom: compute once and
        # reuse across all realisations of this group.
        projections = areal_density_projections(ph, THETA)
        noiseless = simulate(
            spec,
            ph,
            theta_deg=THETA,
            thresholds_kev=(30.0,),
            n0=dose * REFERENCE_N0,
            seed=SEED_BASE + s_idx * 1000000,
            projections=projections,
        )
        stack0 = _vmi_stack_from(noiseless, noiseless=True)
        # SKE signal: insert ROI minus mirrored background ROI, per keV.
        signals = np.stack(
            [
                _roi(stack0[k], RADIUS_CM, 0.0) - _roi(stack0[k], -RADIUS_CM, 0.0)
                for k in range(len(VMI_GRID_KEV))
            ]
        )
        mirror_rois = np.zeros((REPLICATES, len(VMI_GRID_KEV), ROI, ROI))
        for rep in range(REPLICATES):
            res = simulate(
                spec,
                ph,
                theta_deg=THETA,
                thresholds_kev=(30.0,),
                n0=dose * REFERENCE_N0,
                seed=SEED_BASE + s_idx * 1000000 + int(dose * 100) * 1000 + rep,
                projections=projections,
            )
            stack = _vmi_stack_from(res, noiseless=False)
            for k in range(len(VMI_GRID_KEV)):
                mirror_rois[rep, k] = _roi(stack[k], -RADIUS_CM, 0.0)
        per_kev = []
        for k, kev in enumerate(VMI_GRID_KEV):
            nps = nps_2d(mirror_rois[:, k], SPACING_MM)
            res_npwe = npwe(signals[k], nps, SPACING_MM, eye_filter=eye)
            # The ideal observer needs a strictly positive NPS: fill the
            # zeroed DC bin with the mean of its 3x3 neighbourhood (the
            # assumption: DC carries the local average noise power).
            filled = np.array(nps.nps, dtype=np.float64)
            c = filled.shape[0] // 2
            filled[c, c] = float(np.mean(filled[c - 1 : c + 2, c - 1 : c + 2]))
            res_ideal = ideal_linear(signals[k], filled, SPACING_MM)
            per_kev.append(
                {
                    "kev": kev,
                    "d_prime_npwe": res_npwe.d_prime,
                    "d_prime_ideal": res_ideal.d_prime,
                    "efficiency": (res_npwe.d_prime / res_ideal.d_prime) ** 2,
                    "auc_npwe": res_npwe.auc,
                    "nps_variance_hu2": nps.variance,
                    "signal_mean_hu": float(np.mean(signals[k])),
                    "signal_power": res_npwe.signal_power,
                    "noise_power": res_npwe.noise_power,
                }
            )
        part.append(
            {
                "size_cm": size_cm,
                "dose_fraction": dose,
                "n_replicates": REPLICATES,
                "per_kev": per_kev,
            }
        )
        print(f"[size={size_cm} cm, dose={dose:g}] {time.time() - t0:.1f} s")
    return part


def merge(parts: list[list[dict]]) -> dict:
    conditions = sorted(
        (c for part in parts for c in part),
        key=lambda c: (c["size_cm"], -c["dose_fraction"]),
    )
    return {
        "config": {
            "sizes_cm": list(SIZES_CM),
            "concentration_g_cm3": CONC_G_CM3,
            "radius_cm": RADIUS_CM,
            "dose_fractions": list(DOSE_LEVELS),
            "replicates": REPLICATES,
            "roi_px": ROI,
            "spacing_mm": SPACING_MM,
            "theta": [float(t) for t in THETA[:3]] + ["...180 views over 360 deg"],
            "vmi_grid_kev": list(VMI_GRID_KEV),
            "seed_base": SEED_BASE,
            "eye_filter": "burgess peak=1.0 cy/mm exponent=1.3",
            "scaling_law": (
                "d'(conc) = d'(0.005 g/cm^3) * conc / 0.005 (VMI linear in iodine; "
                "background NPS independent of insert concentration)"
            ),
        },
        "conditions": conditions,
    }


def plot(results: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharex=True)
    styles = {1.0: ("-", "100%"), 0.25: ("--", "25%")}
    for cond in results["conditions"]:
        style, dose_label = styles[cond["dose_fraction"]]
        kev = [p["kev"] for p in cond["per_kev"]]
        d_npwe = [p["d_prime_npwe"] for p in cond["per_kev"]]
        d_ideal = [p["d_prime_ideal"] for p in cond["per_kev"]]
        label = f"{cond['size_cm']} cm, {dose_label}"
        axes[0].plot(kev, d_npwe, style, marker="o", ms=3, label=label)
        axes[1].plot(kev, d_ideal, style, marker="s", ms=3, label=label)
    axes[0].set_title("NPWE d'(E) — primary (H1)")
    axes[1].set_title("Ideal linear observer d'(E) — upper bound")
    for ax in axes:
        ax.set_xlabel("VMI energy (keV)")
        ax.set_ylabel("d'")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    if args.merge:
        parts = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(OUT.glob(FINAL.stem + "_part*.json"))
        ]
        if not parts:
            raise SystemExit("no part files found")
        results = merge(parts)
        FINAL.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {FINAL}")
        if args.plot:
            plot(results, OUT / "detectability_spectrum.png")
        return
    if args.start is None or args.stop is None:
        raise SystemExit("chunk mode requires --start and --stop (or use --merge)")
    part = run_chunk(args.start, args.stop)
    (OUT / f"{FINAL.stem}_part{args.start:04d}_{args.stop:04d}.json").write_text(
        json.dumps(part, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
