"""Sprint-5 sensitivity analysis (PROTOCOL_FREEZE.md §10).

Three analyses in one pass over the noise ensembles:

- **Eye-filter sweep (S5-1):** NPWE d'(E) with Burgess peaks
  {0.8, 1.0, 1.5} cy/mm (exponent 1.3 unchanged) for Raw and denoised
  arms, frozen-template and processed-signal versions. d' is linear in the
  template amplitude, so the processed version is att x the frozen one.
- **CHO (S5-2):** channelized Hotelling observer with the frozen Gabor
  bank (frequencies {0.25, 0.5, 0.75} cy/mm x orientations {0, 60, 120} deg,
  one-wavelength envelopes), same SKE/BKE signal and noise ROIs as NPWE.
- **12.5% dose extrapolation (S5-4):** the frozen 3 insert sizes at
  0.125 x REFERENCE_N0 — below the denoiser's training range (25-100%) —
  with the identical procedure. Seeds use dose_code 12 (distinct from
  25/100); no Sprint-2 reference exists at this dose, so no consistency
  gate.

Runs the 6 frozen conditions (same seeds as Sprint 2/4, so Raw arms
reproduce) plus 3 extrapolation conditions:

    python tools/sensitivity_eval.py --start 0 --stop 1   # ... 9 chunks
    python tools/sensitivity_eval.py --merge

Outputs ``results/sensitivity_eval.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from denoised_eval import _center_roi, _crop, _load_model  # noqa: E402
from detectability_spectrum import (  # noqa: E402
    GROUPS,
    RADIUS_CM,
    REPLICATES,
    SEED_BASE,
    SIZES_CM,
    SPACING_MM,
    THETA,
    _phantom,
    _vmi_stack_from,
)

from pcctvmi.denoiser import from_model_output, to_model_input  # noqa: E402
from pcctvmi.forward import REFERENCE_N0, areal_density_projections, simulate  # noqa: E402
from pcctvmi.observers import (  # noqa: E402
    burgess_eye_filter,
    cho,
    gabor_channel_bank,
    nps_2d,
    npwe,
)
from pcctvmi.spectrum import Spectrum  # noqa: E402
from pcctvmi.vmi import VMI_GRID_KEV  # noqa: E402

OUT = ROOT / "results"
FINAL = OUT / "sensitivity_eval.json"
CROP = 128
HALF_CROP = CROP // 2
ROI = 32
HALF = ROI // 2
N = 512
PX_CM = 0.05

EYE_PEAKS = (0.8, 1.0, 1.5)  # S5-1 frozen
EXTRAPOLATION_DOSE = 0.125  # S5-4 frozen

# 6 frozen conditions + 3 extrapolation conditions
ALL_GROUPS = list(GROUPS) + [(s_idx, EXTRAPOLATION_DOSE) for s_idx in range(len(SIZES_CM))]


def _seed(s_idx: int, dose: float, rep: int) -> int:
    dose_code = int(round(dose * 100))
    return SEED_BASE + s_idx * 1_000_000 + dose_code * 1000 + rep


def run_chunk(start: int, stop: int) -> list[dict]:
    spec = Spectrum.from_csv()
    model = _load_model()
    eyes = {p: burgess_eye_filter(peak_cycles_per_mm=p) for p in EYE_PEAKS}
    channels = gabor_channel_bank((ROI, ROI), SPACING_MM)
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

        mirror_raw = np.zeros((REPLICATES, len(VMI_GRID_KEV), ROI, ROI))
        mirror_den = np.zeros((REPLICATES, len(VMI_GRID_KEV), ROI, ROI))
        ins_raw_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        ins_den_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        mir_raw_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        mir_den_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))

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
            with torch.no_grad():
                batch = torch.cat([to_model_input(ins_raw), to_model_input(mir_raw)], dim=0)
                den = model(batch)
            ins_den = from_model_output(den[0:1])
            mir_den = from_model_output(den[1:2])
            for k in range(len(VMI_GRID_KEV)):
                mirror_raw[rep, k] = _center_roi(mir_raw[k])
                mirror_den[rep, k] = _center_roi(mir_den[k])
                ins_raw_mean[rep, k] = float(np.mean(_center_roi(ins_raw[k])))
                ins_den_mean[rep, k] = float(np.mean(_center_roi(ins_den[k])))
                mir_raw_mean[rep, k] = float(np.mean(mirror_raw[rep, k]))
                mir_den_mean[rep, k] = float(np.mean(mirror_den[rep, k]))

        per_kev = []
        for k, kev in enumerate(VMI_GRID_KEV):
            nps_raw = nps_2d(mirror_raw[:, k], SPACING_MM)
            nps_den = nps_2d(mirror_den[:, k], SPACING_MM)
            s_clean = float(np.mean(signals[k]))
            att_raw = float((ins_raw_mean[:, k].mean() - mir_raw_mean[:, k].mean()) / s_clean)
            att_den = float((ins_den_mean[:, k].mean() - mir_den_mean[:, k].mean()) / s_clean)
            eye_entry = {}
            for peak, eye in eyes.items():
                d_raw = npwe(signals[k], nps_raw, SPACING_MM, eye_filter=eye).d_prime
                d_den = npwe(signals[k], nps_den, SPACING_MM, eye_filter=eye).d_prime
                eye_entry[f"{peak:.1f}"] = {
                    "raw": d_raw,
                    "denoised": d_den,
                    "raw_processed": d_raw * att_raw,
                    "denoised_processed": d_den * att_den,
                }
            c_raw = cho(signals[k], mirror_raw[:, k], SPACING_MM, channels).d_prime
            c_den = cho(signals[k], mirror_den[:, k], SPACING_MM, channels).d_prime
            per_kev.append(
                {
                    "kev": kev,
                    "signal_attenuation_raw": att_raw,
                    "signal_attenuation_denoised": att_den,
                    "eye_sweep": eye_entry,
                    "cho": {
                        "raw": c_raw,
                        "denoised": c_den,
                        "raw_processed": c_raw * att_raw,
                        "denoised_processed": c_den * att_den,
                    },
                }
            )
        part.append(
            {
                "size_cm": size_cm,
                "dose_fraction": dose,
                "extrapolated": bool(abs(dose - EXTRAPOLATION_DOSE) < 1e-12),
                "per_kev": per_kev,
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
            "eye_peaks_cyc_mm": list(EYE_PEAKS),
            "cho_channels": {
                "frequencies_cyc_mm": [0.25, 0.5, 0.75],
                "orientations_deg": [0.0, 60.0, 120.0],
                "envelope": "sigma = 1/f (one wavelength)",
            },
            "replicates": REPLICATES,
            "extrapolation_dose": EXTRAPOLATION_DOSE,
            "seed_base": SEED_BASE,
            "note": (
                "Frozen conditions reuse the Sprint-2 seeds (Raw arms "
                "reproduce); processed d' = att x frozen d' (d' is linear "
                "in the template amplitude). 12.5% dose is outside the "
                "denoiser training range (25-100%)."
            ),
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
