"""How much of the D2 arm's result is the training seed? (2026-11-23)

The manuscript's sharpest single number is the D2 arm's quarter-count
two-basis residual, about 5.6 times the D1 arm's. It was measured on one
trained network. Re-executing the pipeline on 2026-11-04 established that
nothing downstream of training reproduces, and the cause -- the global torch
RNG was never seeded -- has since been repaired (``seeded_model``). What that
repair does not supply is the size of the run-to-run spread: a result from a
single draw of a stochastic process cannot say whether a 5.6-fold increase is
the loss term or the draw.

This script trains the D2 arm again, from scratch, under three seeds fixed
here before any outcome was seen, and runs the frozen evaluation on each:

    SEEDS = (20261019, 20261020, 20261021)

20261019 is the protocol seed. The other two are it plus one and plus two; no
candidate was tried and discarded, and no seed is dropped after the fact.
Everything else is the frozen D2 configuration: spectral beta 3.0, 4000 steps,
the same 160/32 split, the same training data, the same evaluation conditions
and the same six-chunk evaluation code.

What this does NOT do:

- It does not replace the manuscript's numbers. Those come from the weights
  archived in release v0.2.0, which predate the seeding repair and cannot be
  regenerated; every figure and table stays sourced from them.
- It does not retrain D1. The ratio's denominator is the D1 residual and its
  reference is the Raw arm, which does not depend on a trained network; this
  measures the spread of the numerator.
- It does not change any frozen result file. Outputs carry a ``_s<seed>`` tag.

Each stage is skipped when its output already exists, so the run is
resumable:

    python tools/seed_replication_d2.py            # train + evaluate + summarise
    python tools/seed_replication_d2.py --summary-only

Writes ``results/seed_replication_d2.json``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

SEEDS: tuple[int, ...] = (20261019, 20261020, 20261021)
SPECTRAL_BETA = "3.0"  # the selected D2 weight (PROTOCOL_FREEZE.md section 11)
TOTAL_STEPS = 4000  # S3-7
N_CONDITIONS = 6  # the frozen primary conditions
QUARTER = 0.25


def _tag(seed: int) -> str:
    return f"_d2_s{seed}"


def _weights(seed: int) -> Path:
    return RESULTS / f"denoiser{_tag(seed)}_weights.pt"


def _eval_final(seed: int) -> Path:
    return RESULTS / f"denoised_eval{_tag(seed)}.json"


def _run(argv: list[str]) -> None:
    printable = " ".join(argv[1:])
    print(f"--> {printable}", flush=True)
    t0 = time.time()
    proc = subprocess.run([sys.executable, *argv], cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"failed ({proc.returncode}): {printable}")
    print(f"    done in {time.time() - t0:.0f}s", flush=True)


def _train(seed: int) -> None:
    if _weights(seed).exists():
        print(f"seed {seed}: weights present, training skipped", flush=True)
        return
    _run(
        [
            "tools/train_denoiser.py",
            "--spectral-beta",
            SPECTRAL_BETA,
            "--suffix",
            _tag(seed),
            "--seed",
            str(seed),
            "--total-steps",
            str(TOTAL_STEPS),
            "--steps-per-run",
            str(TOTAL_STEPS),
        ]
    )
    if not _weights(seed).exists():
        raise SystemExit(f"seed {seed}: training wrote no weights")


def _evaluate(seed: int) -> None:
    final = _eval_final(seed)
    if final.exists():
        print(f"seed {seed}: evaluation present, skipped", flush=True)
        return
    common = ["--weights", str(_weights(seed).relative_to(ROOT)), "--final", final.name]
    for start in range(N_CONDITIONS):
        part = RESULTS / f"{final.stem}_part{start:04d}_{start + 1:04d}.json"
        if part.exists():
            print(f"seed {seed}: condition {start} present, skipped", flush=True)
            continue
        _run(
            [
                "tools/denoised_eval.py",
                "--start",
                str(start),
                "--stop",
                str(start + 1),
                *common,
            ]
        )
    _run(["tools/denoised_eval.py", "--merge", *common])
    if not final.exists():
        raise SystemExit(f"seed {seed}: merge wrote no {final.name}")


def _conditions(path: Path) -> dict[tuple[float, float], dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {(float(c["size_cm"]), float(c["dose_fraction"])): c for c in doc["conditions"]}


def _d40(cond: dict, key: str) -> float:
    for p in cond["per_kev"]:
        if int(p["kev"]) == 40:
            return float(p[key])
    raise KeyError(key)


def _spread(values: list[float]) -> dict:
    out = {
        "n": len(values),
        "values": values,
        "mean": statistics.fmean(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
    }
    out["sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
    return out


def _summarise() -> dict:
    d1 = _conditions(RESULTS / "denoised_eval.json")
    shipped = _conditions(RESULTS / "denoised_eval_d2.json")
    per_seed = {}
    for seed in SEEDS:
        path = _eval_final(seed)
        if not path.exists():
            raise SystemExit(f"missing {path.name}; run without --summary-only first")
        per_seed[seed] = _conditions(path)

    conditions = []
    for key in sorted(d1, key=lambda k: (k[0], -k[1])):
        size, dose = key
        residuals = [float(per_seed[s][key]["residual_hu"]["denoised"]["mean"]) for s in SEEDS]
        biases = [
            float(per_seed[s][key]["quantitation"]["denoised_dev"]["mean"]) * 1000.0
            for s in SEEDS
        ]
        d40_proc = [
            _d40(per_seed[s][key], "d_npwe_denoised_processed") for s in SEEDS
        ]
        d1_resid = float(d1[key]["residual_hu"]["denoised"]["mean"])
        conditions.append(
            {
                "size_cm": size,
                "dose_fraction": dose,
                "d1_residual_hu": d1_resid,
                "shipped_d2_residual_hu": float(
                    shipped[key]["residual_hu"]["denoised"]["mean"]
                ),
                "shipped_d2_over_d1": float(
                    shipped[key]["residual_hu"]["denoised"]["mean"]
                )
                / d1_resid,
                "residual_hu": _spread(residuals),
                "residual_ratio_over_d1": _spread([r / d1_resid for r in residuals]),
                "iodine_deviation_mgi_ml": _spread(biases),
                "d40_processed": _spread(d40_proc),
            }
        )

    quarter = [c for c in conditions if c["dose_fraction"] == QUARTER]
    ratios = [r for c in quarter for r in c["residual_ratio_over_d1"]["values"]]
    verdict = {
        "quarter_count_ratio_over_d1": _spread(ratios),
        "shipped_quarter_count_ratio_over_d1": _spread(
            [c["shipped_d2_over_d1"] for c in quarter]
        ),
    }
    verdict["lowest_single_run_ratio"] = min(ratios)
    verdict["survives_every_seed"] = min(ratios) > 1.0
    return {
        "written": time.strftime("%Y-%m-%d"),
        "what": (
            "The D2 arm trained from three prespecified seeds and evaluated by the "
            "frozen six-condition evaluation. Measures how much of the quarter-count "
            "two-basis residual increase is the draw rather than the loss term. The "
            "manuscript's own numbers remain those of the archived v0.2.0 weights, "
            "which predate the seeding repair and are reported here as 'shipped'."
        ),
        "seeds": list(SEEDS),
        "spectral_beta": float(SPECTRAL_BETA),
        "total_steps": TOTAL_STEPS,
        "d1_arm": "not retrained; the ratio's denominator is the shipped D1 arm",
        "conditions": conditions,
        "verdict": verdict,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--summary-only",
        action="store_true",
        help="summarise existing per-seed evaluations without training",
    )
    args = ap.parse_args()

    if not args.summary_only:
        for seed in SEEDS:
            print(f"=== seed {seed} ===", flush=True)
            _train(seed)
            _evaluate(seed)

    out = RESULTS / "seed_replication_d2.json"
    summary = _summarise()
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")
    v = summary["verdict"]
    q = v["quarter_count_ratio_over_d1"]
    print(
        f"quarter-count D2/D1 residual ratio over {q['n']} runs: "
        f"{q['min']:.2f} to {q['max']:.2f} (mean {q['mean']:.2f}); "
        f"shipped weights gave "
        f"{v['shipped_quarter_count_ratio_over_d1']['min']:.2f} to "
        f"{v['shipped_quarter_count_ratio_over_d1']['max']:.2f}"
    )


if __name__ == "__main__":
    main()
