"""Evaluate the trained denoiser on the frozen Sprint-1/2 conditions (S3-8).

For each frozen condition (insert size x dose, seeds identical to Sprint 2,
so the Raw arm reproduces the detectability spectrum bit-for-bit):

- regenerate the noiseless reference and the 64 noise realisations
- denoise 128^2 crops centred on the insert and on the mirrored background
  (the model is fully convolutional; crops keep inference affordable)
- compare three arms — Raw / denoised / noiseless — on:
  (a) NPWE d'(E) and the ideal-linear upper bound (S2 procedure unchanged,
      NPS now also measured on the denoised ROIs). Sprint-4 revision
      (2026-10-19): in addition to the frozen noiseless-signal d', each arm
      gets a *processed-signal* d' whose template amplitude is the signal
      actually present in the processed images (ensemble mean of insert-ROI
      minus mirror-ROI means), so a denoiser that suppresses the insert
      contrast is penalised instead of passing the noiseless template
      through. Signal attenuation ratios are saved per keV.
  (b) iodine quantitation: per-pixel 2-basis fit of the VMI crop, insert
      mean over the interior disk mask (radius = 0.8 x insert radius, the
      Sprint-1 quantitation rule), deviation from the noiseless baseline
      (primary metric, S6.2)
  (c) 2-basis projection residual in HU (subsidiary metric, S6.1)

Consistency check built in: the Raw arm's frozen (noiseless-signal) d'(E)
must reproduce results/detectability_spectrum.json (same seeds); the run
refuses to write output if the maximum relative deviation exceeds 1%.

Chunked execution (one condition per chunk, ~3 minutes):

    python tools/denoised_eval.py --start 0 --stop 1
    ...
    python tools/denoised_eval.py --start 5 --stop 6
    python tools/denoised_eval.py --merge [--plot]

Alternate denoiser / output (e.g. the D2 spectral-loss arm, 2026-10-20)::

    python tools/denoised_eval.py --start 0 --stop 1 \
        --weights results/denoiser_d2_weights.pt --final denoised_eval_d2.json
    ...
    python tools/denoised_eval.py --merge --final denoised_eval_d2.json

Outputs ``results/denoised_eval.json`` and (with --plot)
``results/denoised_eval.png`` (or the ``--final``-derived names).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from detectability_spectrum import (  # noqa: E402
    CONC_G_CM3,
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

from pcctvmi.denoiser import VMIDenoiser, from_model_output, to_model_input  # noqa: E402
from pcctvmi.forward import REFERENCE_N0, areal_density_projections, simulate  # noqa: E402
from pcctvmi.observers import burgess_eye_filter, ideal_linear, nps_2d, npwe  # noqa: E402
from pcctvmi.projection import basis_residual, fit_basis  # noqa: E402
from pcctvmi.spectrum import Spectrum  # noqa: E402
from pcctvmi.vmi import VMI_GRID_KEV  # noqa: E402

OUT = ROOT / "results"
FINAL = OUT / "denoised_eval.json"
WEIGHTS = OUT / "denoiser_weights.pt"
SPRINT2 = OUT / "detectability_spectrum.json"
CROP = 128  # denoiser inference crop (fully convolutional model)
HALF_CROP = CROP // 2
ROI = 32
HALF = ROI // 2
N = 512
PX_CM = 0.05


def _crop(img: np.ndarray, x_cm: float, y_cm: float, half: int) -> np.ndarray:
    cx = x_cm / PX_CM + N / 2.0
    cy = y_cm / PX_CM + N / 2.0
    icx, icy = int(round(cx)), int(round(cy))
    return img[icy - half : icy + half, icx - half : icx + half]


def _center_roi(crop: np.ndarray) -> np.ndarray:
    """Central 32x32 ROI of a 128x128 crop (the S2 ROI, crop-local)."""
    return crop[HALF_CROP - HALF : HALF_CROP + HALF, HALF_CROP - HALF : HALF_CROP + HALF]


def _insert_disk_mask(size_cm: float) -> np.ndarray:
    """Interior disk mask for quantitation: radius 0.8 x insert radius (px).

    Same rule as tools/quantitation_baseline.py ``_roi`` (Sprint-1 frozen
    quantitation geometry); clamps to >= 2 px so the smallest insert stays
    measurable inside the 32x32 ROI.
    """
    rad = max(2, int(round((size_cm / 2.0) / PX_CM * 0.8)))
    yy, xx = np.mgrid[0:ROI, 0:ROI]
    c = HALF - 0.5  # 32x32 ROI centre (15.5, 15.5)
    return (yy - c) ** 2 + (xx - c) ** 2 <= rad**2


def _masked_mean(roi: np.ndarray, mask: np.ndarray) -> float:
    return float(np.mean(roi[mask]))


def _load_model(weights: Path | None = None) -> VMIDenoiser:
    """Load the denoiser; ``weights=None`` uses the module-level WEIGHTS.

    The default is resolved at call time (not as a default argument) so
    ``main()`` can override WEIGHTS via ``--weights``; importers calling
    ``_load_model()`` with no argument still get the default weights.
    """
    model = VMIDenoiser(n_channels=len(VMI_GRID_KEV))
    model.load_state_dict(torch.load(WEIGHTS if weights is None else weights, weights_only=True))
    model.eval()
    return model


def _observe(signal: np.ndarray, rois: np.ndarray, eye) -> dict:
    """NPWE + ideal d' for one keV level from an ROI ensemble."""
    nps = nps_2d(rois, SPACING_MM)
    res_npwe = npwe(signal, nps, SPACING_MM, eye_filter=eye)
    filled = np.array(nps.nps, dtype=np.float64)
    c = filled.shape[0] // 2
    filled[c, c] = float(np.mean(filled[c - 1 : c + 2, c - 1 : c + 2]))
    res_ideal = ideal_linear(signal, filled, SPACING_MM)
    return {
        "npwe": res_npwe.d_prime,
        "ideal": res_ideal.d_prime,
        "nps_variance": nps.variance,
        "nps": nps,
        "nps_filled": filled,
    }


def _observe_processed(template: np.ndarray, amp_ratio: float, observed: dict, eye) -> dict:
    """d' with the template amplitude replaced by the processed signal.

    Sprint-4 revision: the frozen d' feeds the *noiseless* difference image
    as the template; if the denoiser suppresses the insert contrast, that
    d' never sees it. Here the template keeps its spatial shape but its
    amplitude is scaled to the signal actually measured in the processed
    images (amp_ratio = s_eff / s_clean), and the arm's own NPS is used.
    """
    sig = template * amp_ratio
    res_npwe = npwe(sig, observed["nps"], SPACING_MM, eye_filter=eye)
    res_ideal = ideal_linear(sig, observed["nps_filled"], SPACING_MM)
    return {"npwe": res_npwe.d_prime, "ideal": res_ideal.d_prime}


def run_chunk(start: int, stop: int) -> list[dict]:
    spec = Spectrum.from_csv()
    eye = burgess_eye_filter()
    model = _load_model()
    sprint2 = json.loads(SPRINT2.read_text(encoding="utf-8"))
    part: list[dict] = []
    for s_idx, dose in GROUPS[start:stop]:
        t0 = time.time()
        size_cm = SIZES_CM[s_idx]
        ph = _phantom(size_cm)
        projections = areal_density_projections(ph, THETA)

        def _stacks(res):
            return _vmi_stack_from(res, noiseless=False)

        # Noiseless reference: signals and baselines (identical to Sprint 2).
        noiseless = simulate(
            spec,
            ph,
            theta_deg=THETA,
            thresholds_kev=(30.0,),
            n0=dose * REFERENCE_N0,
            seed=SEED_BASE + s_idx * 1_000_000,
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

        mirror_raw = np.zeros((REPLICATES, len(VMI_GRID_KEV), ROI, ROI))
        mirror_den = np.zeros((REPLICATES, len(VMI_GRID_KEV), ROI, ROI))
        ins_raw_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        ins_den_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        mir_raw_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        mir_den_mean = np.zeros((REPLICATES, len(VMI_GRID_KEV)))
        dev_raw: list[float] = []
        dev_den: list[float] = []
        residual_raw: list[float] = []
        residual_den: list[float] = []

        for rep in range(REPLICATES):
            res = simulate(
                spec,
                ph,
                theta_deg=THETA,
                thresholds_kev=(30.0,),
                n0=dose * REFERENCE_N0,
                seed=SEED_BASE + s_idx * 1_000_000 + int(dose * 100) * 1000 + rep,
                projections=projections,
            )
            stack = _stacks(res)
            # Insert crop: quantitation + residual. Mirror crop: NPS ROIs.
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
            # Quantitation: 2-basis fit on the crop, interior-disk mean of b
            # (Sprint-1 rule; Sprint-4 revision from the full 32x32 mean).
            b_raw = fit_basis(ins_raw)[1]
            b_den = fit_basis(ins_den)[1]
            dev_raw.append(_masked_mean(_center_roi(b_raw), disk) - baseline_b)
            dev_den.append(_masked_mean(_center_roi(b_den), disk) - baseline_b)
            residual_raw.append(float(np.mean(basis_residual(ins_raw))))
            residual_den.append(float(np.mean(basis_residual(ins_den))))

        per_kev = []
        for k, kev in enumerate(VMI_GRID_KEV):
            raw = _observe(signals[k], mirror_raw[:, k], eye)
            den = _observe(signals[k], mirror_den[:, k], eye)
            # Sprint-4 processed-signal d': amplitude actually present in the
            # processed images (ensemble means; noise averages out over reps).
            s_clean = float(np.mean(signals[k]))
            s_eff_raw = float(ins_raw_mean[:, k].mean() - mir_raw_mean[:, k].mean())
            s_eff_den = float(ins_den_mean[:, k].mean() - mir_den_mean[:, k].mean())
            att_raw = s_eff_raw / s_clean
            att_den = s_eff_den / s_clean
            proc_raw = _observe_processed(signals[k], att_raw, raw, eye)
            proc_den = _observe_processed(signals[k], att_den, den, eye)
            per_kev.append(
                {
                    "kev": kev,
                    "d_npwe_raw": raw["npwe"],
                    "d_npwe_denoised": den["npwe"],
                    "d_ideal_raw": raw["ideal"],
                    "d_ideal_denoised": den["ideal"],
                    "d_npwe_raw_processed": proc_raw["npwe"],
                    "d_npwe_denoised_processed": proc_den["npwe"],
                    "d_ideal_denoised_processed": proc_den["ideal"],
                    "signal_clean_mean_hu": s_clean,
                    "signal_eff_raw_hu": s_eff_raw,
                    "signal_eff_denoised_hu": s_eff_den,
                    "signal_attenuation_raw": att_raw,
                    "signal_attenuation_denoised": att_den,
                    "nps_var_raw": raw["nps_variance"],
                    "nps_var_denoised": den["nps_variance"],
                }
            )

        # Consistency: Raw arm must reproduce the Sprint-2 spectrum.
        s2 = next(
            c
            for c in sprint2["conditions"]
            if c["size_cm"] == size_cm and c["dose_fraction"] == dose
        )
        rel_diffs = [
            abs(p["d_npwe_raw"] - q["d_prime_npwe"]) / q["d_prime_npwe"]
            for p, q in zip(per_kev, s2["per_kev"], strict=True)
        ]
        max_rel = float(max(rel_diffs))
        if max_rel > 0.01:
            msg = f"Raw d'(E) deviates from Sprint 2 by {max_rel:.2%} (size={size_cm}, dose={dose})"
            if REPLICATES >= 64:
                raise SystemExit(msg + "; refusing to write output")
            # Reduced-replicate pilots (R < 64) cannot reproduce the R=64
            # NPS estimate; the gate only applies to full runs.
            print(f"WARNING: {msg}; R={REPLICATES} < 64 (pilot mode, gate not enforced)")

        def _msd(values: list[float]) -> dict:
            arr = np.asarray(values)
            return {"mean": float(arr.mean()), "sd": float(arr.std())}

        part.append(
            {
                "size_cm": size_cm,
                "dose_fraction": dose,
                "consistency_max_rel_diff_vs_sprint2": max_rel,
                "quantitation_mask_radius_px": int(max(2, round((size_cm / 2.0) / PX_CM * 0.8))),
                "per_kev": per_kev,
                "quantitation": {
                    "baseline_b_g_cm3": baseline_b,
                    "raw_dev": _msd(dev_raw),
                    "denoised_dev": _msd(dev_den),
                },
                "residual_hu": {
                    "noiseless": residual_noiseless,
                    "raw": _msd(residual_raw),
                    "denoised": _msd(residual_den),
                },
            }
        )
        print(
            f"[size={size_cm} dose={dose:g}] {time.time() - t0:.0f}s "
            f"consistency={max_rel:.2%} "
            f"|b_dev| raw={abs(np.mean(dev_raw)):.4f} den={abs(np.mean(dev_den)):.4f} "
            f"att_den={np.mean([p['signal_attenuation_denoised'] for p in per_kev]):.3f}"
        )
    return part


def merge(parts: list[list[dict]]) -> dict:
    conditions = sorted(
        (c for part in parts for c in part),
        key=lambda c: (c["size_cm"], -c["dose_fraction"]),
    )
    return {
        "config": {
            "weights": str(WEIGHTS),
            "crop_px": CROP,
            "roi_px": ROI,
            "concentration_g_cm3": CONC_G_CM3,
            "radius_cm": RADIUS_CM,
            "replicates": REPLICATES,
            "vmi_grid_kev": list(VMI_GRID_KEV),
            "seed_base": SEED_BASE,
            "note": (
                "Raw arm reproduces results/detectability_spectrum.json (same "
                "seeds); deviations below 1% enforced. Sprint-4 revision "
                "(2026-10-19): quantitation uses the interior disk mask "
                "(radius 0.8x insert radius, Sprint-1 rule); processed-signal "
                "d' fields use the signal actually present in the processed "
                "images as the template amplitude."
            ),
        },
        "conditions": conditions,
    }


def plot(results: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    styles = {1.0: ("-", "100%"), 0.25: ("--", "25%")}
    for cond in results["conditions"]:
        style, dose_label = styles[cond["dose_fraction"]]
        kev = [p["kev"] for p in cond["per_kev"]]
        axes[0].plot(kev, [p["d_npwe_raw"] for p in cond["per_kev"]], style, color="0.6", lw=1)
        axes[0].plot(
            kev,
            [p["d_npwe_denoised"] for p in cond["per_kev"]],
            style,
            marker="o",
            ms=3,
            label=f"{cond['size_cm']} cm, {dose_label}",
        )
    axes[0].set_title("NPWE d'(E): grey = Raw, colour = denoised")
    labels, raw_dev, den_dev = [], [], []
    for cond in results["conditions"]:
        style, dose_label = styles[cond["dose_fraction"]]
        labels.append(f"{cond['size_cm']} cm\n{dose_label}")
        raw_dev.append(cond["quantitation"]["raw_dev"]["mean"] * 1000)  # mgI/mL
        den_dev.append(cond["quantitation"]["denoised_dev"]["mean"] * 1000)
    xpos = np.arange(len(labels))
    axes[1].bar(xpos - 0.2, raw_dev, 0.4, label="Raw", color="0.6")
    axes[1].bar(xpos + 0.2, den_dev, 0.4, label="denoised")
    axes[1].axhline(0.0, color="k", lw=0.8)
    axes[1].set_xticks(xpos)
    axes[1].set_xticklabels(labels, fontsize=7)
    axes[1].set_ylabel("iodine bias vs noiseless (mgI/mL)")
    axes[1].set_title("Quantitation deviation (H2)")
    axes[1].legend(fontsize=8)
    for cond in results["conditions"]:
        style, dose_label = styles[cond["dose_fraction"]]
        kev = [p["kev"] for p in cond["per_kev"]]
        axes[2].plot(
            kev, [p["d_ideal_denoised"] for p in cond["per_kev"]], style, lw=1, color="0.6"
        )
        axes[2].plot(
            kev,
            [p["d_npwe_denoised"] for p in cond["per_kev"]],
            style,
            marker="o",
            ms=3,
            label=f"{cond['size_cm']} cm, {dose_label}",
        )
    axes[2].set_title("Denoised: NPWE (colour) vs ideal (grey)")
    for ax in axes:
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"wrote {path}")


def main() -> None:
    # D2 (2026-10-20): allow evaluating alternate denoisers (e.g. the
    # spectral-loss D2 arm) without touching the frozen D1 artifacts.
    # Chunked runs are separate processes, so overriding the module globals
    # here is sufficient; both must be passed identically to every chunk.
    global WEIGHTS, FINAL
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--plot", action="store_true")
    ap.add_argument(
        "--weights",
        type=Path,
        default=WEIGHTS,
        help="denoiser weights to evaluate (default: results/denoiser_weights.pt, the D1 arm)",
    )
    ap.add_argument(
        "--final",
        type=Path,
        default=FINAL,
        help="output JSON path (default: results/denoised_eval.json)",
    )
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    WEIGHTS = args.weights
    FINAL = args.final
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
            plot(results, OUT / f"{FINAL.stem}.png")
        return
    if args.start is None or args.stop is None:
        raise SystemExit("chunk mode requires --start and --stop (or use --merge)")
    part = run_chunk(args.start, args.stop)
    (OUT / f"{FINAL.stem}_part{args.start:04d}_{args.stop:04d}.json").write_text(
        json.dumps(part, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
