"""Evaluate the 3-D TV control arm (D3, PROTOCOL_FREEZE.md S5-3) on the same
conditions as the main evaluation: the 6 frozen Sprint-1/2 conditions plus
the 3 12.5% extrapolation conditions.

Mirrors tools/denoised_eval.py with the UNet replaced by TV denoising
(``weight = 0.5 * sigma_hat^2`` per stack, 300 Chambolle iterations), so
the Raw / TV / (noiseless baseline) comparison covers:
(a) NPWE d'(E) at the frozen Burgess peak 1.0 cy/mm, frozen and processed
    template versions,
(b) iodine quantitation over the interior disk mask (S4-3),
(c) 2-basis projection residual in HU.

Chunked execution (one condition per chunk, ~4 minutes: TV denoising of
128 stacks at 300 iterations dominates):

    python tools/tv_eval.py --start 0 --stop 1   # ... 9 chunks
    python tools/tv_eval.py --merge

Outputs ``results/tv_eval.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from denoised_eval import (  # noqa: E402
    _center_roi,
    _crop,
    _insert_disk_mask,
    _masked_mean,
)
from detectability_spectrum import (  # noqa: E402
    RADIUS_CM,
    REPLICATES,
    SIZES_CM,
    SPACING_MM,
    THETA,
    _phantom,
    _vmi_stack_from,
)
from sensitivity_eval import ALL_GROUPS, _seed  # noqa: E402

from pcctvmi.forward import REFERENCE_N0, areal_density_projections, simulate  # noqa: E402
from pcctvmi.observers import burgess_eye_filter, nps_2d, npwe  # noqa: E402
from pcctvmi.projection import basis_residual, fit_basis  # noqa: E402
from pcctvmi.spectrum import Spectrum  # noqa: E402
from pcctvmi.tv import chambolle_tv_3d, laplacian_noise_sd  # noqa: E402
from pcctvmi.vmi import VMI_GRID_KEV  # noqa: E402

OUT = ROOT / "results"
FINAL = OUT / "tv_eval.json"
CROP = 128
HALF_CROP = CROP // 2
ROI = 32
HALF = ROI // 2
TV_C = 0.5  # S5-3 frozen: selected on validation data only
TV_ITER = 300


def _observe(signal: np.ndarray, rois: np.ndarray, eye) -> dict:
    nps = nps_2d(rois, SPACING_MM)
    res = npwe(signal, nps, SPACING_MM, eye_filter=eye)
    return {"npwe": res.d_prime, "nps": nps}


def run_chunk(start: int, stop: int) -> list[dict]:
    spec = Spectrum.from_csv()
    eye = burgess_eye_filter()
    part: list[dict] = []
    for s_idx, dose in ALL_GROUPS[start:stop]:
        t0 = time.time()
        size_cm = SIZES_CM[s_idx]
        ph = _phantom(size_cm)
        projections = areal_density_projections(ph, THETA)

        noiseless = simulate(
            spec,
            ph,
            theta_deg=THETA,
            thresholds_kev=(30.0,),
            n0=dose * REFERENCE_N0,
            seed=_seed(s_idx, dose, 0),
            projections=projections,
        )
        stack0 = _vmi_stack_from(noiseless, noiseless=True)
        signals = np.stack(
            [
                _crop(stack0[k], RADIUS_CM, 0.0, HALF) - _crop(stack0[k], -RADIUS_CM, 0.0, HALF)
                for k in range(len(VMI_GRID_KEV))
            ]
        )
        b0_crop = np.stack(
            [_crop(stack0[k], RADIUS_CM, 0.0, HALF_CROP) for k in range(len(VMI_GRID_KEV))]
        )
        disk = _insert_disk_mask(size_cm)
        baseline_b = _masked_mean(_center_roi(fit_basis(b0_crop)[1]), disk)
        residual_noiseless = float(np.mean(basis_residual(b0_crop)))

        mirror_tv = np.zeros((REPLICATES, len(VMI_GRID_KEV), ROI, ROI))
        ins_tv_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        mir_tv_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        dev_tv: list[float] = []
        residual_tv: list[float] = []

        for rep in range(REPLICATES):
            res = simulate(
                spec,
                ph,
                theta_deg=THETA,
                thresholds_kev=(30.0,),
                n0=dose * REFERENCE_N0,
                seed=_seed(s_idx, dose, rep),
                projections=projections,
            )
            stack = _vmi_stack_from(res, noiseless=False)
            ins_raw = np.stack(
                [_crop(stack[k], RADIUS_CM, 0.0, HALF_CROP) for k in range(len(VMI_GRID_KEV))]
            )
            mir_raw = np.stack(
                [_crop(stack[k], -RADIUS_CM, 0.0, HALF_CROP) for k in range(len(VMI_GRID_KEV))]
            )
            sigma_hat = laplacian_noise_sd(ins_raw)
            ins_tv = chambolle_tv_3d(ins_raw, TV_C * sigma_hat**2, n_iter=TV_ITER)
            sigma_hat_m = laplacian_noise_sd(mir_raw)
            mir_tv = chambolle_tv_3d(mir_raw, TV_C * sigma_hat_m**2, n_iter=TV_ITER)
            for k in range(len(VMI_GRID_KEV)):
                mirror_tv[rep, k] = _center_roi(mir_tv[k])
                ins_tv_mean[rep, k] = float(np.mean(_center_roi(ins_tv[k])))
                mir_tv_mean[rep, k] = float(np.mean(mirror_tv[rep, k]))
            b_tv = fit_basis(ins_tv)[1]
            dev_tv.append(_masked_mean(_center_roi(b_tv), disk) - baseline_b)
            residual_tv.append(float(np.mean(basis_residual(ins_tv))))

        per_kev = []
        for k, kev in enumerate(VMI_GRID_KEV):
            obs = _observe(signals[k], mirror_tv[:, k], eye)
            s_clean = float(np.mean(signals[k]))
            att_tv = float((ins_tv_mean[:, k].mean() - mir_tv_mean[:, k].mean()) / s_clean)
            per_kev.append(
                {
                    "kev": kev,
                    "d_npwe_tv": obs["npwe"],
                    "d_npwe_tv_processed": obs["npwe"] * att_tv,
                    "signal_attenuation_tv": att_tv,
                }
            )

        def _msd(values: list[float]) -> dict:
            arr = np.asarray(values)
            return {"mean": float(arr.mean()), "sd": float(arr.std())}

        part.append(
            {
                "size_cm": size_cm,
                "dose_fraction": dose,
                "extrapolated": bool(dose < 0.25),
                "quantitation_mask_radius_px": int(max(2, round((size_cm / 2.0) / 0.05 * 0.8))),
                "per_kev": per_kev,
                "quantitation": {
                    "baseline_b_g_cm3": baseline_b,
                    "tv_dev": _msd(dev_tv),
                },
                "residual_hu": {
                    "noiseless": residual_noiseless,
                    "tv": _msd(residual_tv),
                },
            }
        )
        print(f"[size={size_cm} dose={dose:g}] {time.time() - t0:.0f}s")
    return part


def merge(parts: list[list[dict]]) -> dict:
    conditions = sorted(
        (c for part in parts for c in part),
        key=lambda c: (c["size_cm"], -c["dose_fraction"]),
    )
    return {
        "config": {
            "tv_weight": f"{TV_C} * sigma_hat^2 (S5-3)",
            "tv_iterations": TV_ITER,
            "eye_peak_cyc_mm": 1.0,
            "note": "3-D TV control arm; same protocol as denoised_eval (S4 revisions).",
        },
        "conditions": conditions,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--merge", action="store_true")
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
        return
    if args.start is None or args.stop is None:
        raise SystemExit("chunk mode requires --start and --stop (or use --merge)")
    part = run_chunk(args.start, args.stop)
    (OUT / f"{FINAL.stem}_part{args.start:04d}_{args.stop:04d}.json").write_text(
        json.dumps(part, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
