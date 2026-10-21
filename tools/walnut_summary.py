"""Aggregate the walnut_eval per-slice records into arm-level summaries.

Reads ``results/walnut_eval_d{ dose }.json`` (merged) and writes
``results/walnut_eval_summary.json`` with per-arm means over slices:
VMI RMSE/SSIM per keV (and grid means), MD pulp/shell ROI bias/SD,
radial NPS profiles, and the H4 headline numbers (MD total error =
sqrt(bias^2 + sd^2) per ROI/material).

    python tools/walnut_summary.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
ARMS = ("raw", "d1w", "tv")
DOSES = (0.25, 0.125)


def _mean_over_slices(records: list[dict], key_path: list[str]) -> np.ndarray:
    vals = []
    for rec in records:
        cur = rec
        for k in key_path:
            cur = cur[k]
        vals.append(cur)
    return np.mean(np.asarray(vals, dtype=np.float64), axis=0)


def summarize(dose: float) -> dict:
    data = json.loads((RESULTS / f"walnut_eval_d{dose:g}.json").read_text(encoding="utf-8"))
    records = data["slices"]
    out: dict = {"dose": dose, "n_slices": len(records)}
    for arm in ARMS:
        rmse = _mean_over_slices(records, [arm, "vmi_rmse_per_kev"])
        ssim = _mean_over_slices(records, [arm, "vmi_ssim_per_kev"])
        entry: dict = {
            "vmi_rmse_mean_hu": float(rmse.mean()),
            "vmi_rmse_per_kev_hu": rmse.tolist(),
            "vmi_ssim_mean": float(ssim.mean()),
            "vmi_ssim_per_kev": ssim.tolist(),
        }
        for roi in ("pulp", "shell"):
            for mat in ("pulp", "shell"):
                bias = _mean_over_slices(records, [arm, f"md_{roi}_roi_{mat}_bias"])
                sd = _mean_over_slices(records, [arm, f"md_{roi}_roi_{mat}_sd"])
                entry[f"md_{roi}_roi_{mat}"] = {
                    "bias": float(bias),
                    "sd": float(sd),
                    "total_err": float(np.sqrt(bias**2 + sd**2)),
                }
        entry["nps_low_radial"] = _mean_over_slices(records, [arm, "nps_low_radial"]).tolist()
        entry["nps_high_radial"] = _mean_over_slices(records, [arm, "nps_high_radial"]).tolist()
        out[arm] = entry
    return out


def main() -> None:
    summary = {f"d{d:g}": summarize(d) for d in DOSES}
    (RESULTS / "walnut_eval_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8"
    )
    for tag, res in summary.items():
        print(f"== dose {tag} ({res['n_slices']} slices) ==")
        print(
            f"{'arm':5s} {'VMI_RMSE':>9s} {'SSIM':>6s} "
            f"{'pulpBias':>9s} {'pulpSD':>8s} {'pulpTot':>8s} "
            f"{'shellBias':>9s} {'shellSD':>8s} {'shellTot':>8s}"
        )
        for arm in ARMS:
            e = res[arm]
            p = e["md_pulp_roi_pulp"]
            s = e["md_shell_roi_shell"]
            print(
                f"{arm:5s} {e['vmi_rmse_mean_hu']:9.1f} {e['vmi_ssim_mean']:6.4f} "
                f"{p['bias']:9.1f} {p['sd']:8.1f} {p['total_err']:8.1f} "
                f"{s['bias']:9.1f} {s['sd']:8.1f} {s['total_err']:8.1f}"
            )


if __name__ == "__main__":
    main()
