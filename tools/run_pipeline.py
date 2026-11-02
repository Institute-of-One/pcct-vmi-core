"""Run the whole research pipeline, in dependency order, from the physics tables up.

Every number in the manuscript comes from a file in ``results/``, and until this
script existed each of those files was produced by a command typed by hand. A
pipeline nobody can re-execute in one step is a pipeline nobody re-executes, so
the order, the chunk boundaries and the arguments live here instead of in a
transcript.

Each stage declares the files it produces. A stage whose outputs all exist is
skipped, so an interrupted run continues where it stopped; ``--force`` re-runs it
anyway. A failing stage does not stop the others unless they depend on it: the
run records the failure, skips the dependents, and the ledger says which.

The chunk boundaries are the ones the sprints used (visible in the ``_part*``
file names of the committed results), so the merged output is assembled from the
same pieces.

Usage::

    python tools/run_pipeline.py --list
    python tools/run_pipeline.py                      # everything that is missing
    python tools/run_pipeline.py --only train_d1 denoised_eval_d1
    python tools/run_pipeline.py --from walnut_noise_model_d025
    python tools/run_pipeline.py --dry-run

The ledger is written to ``results/pipeline_run.json`` after every stage, and the
combined child output to ``results/pipeline_run.log``.

This does not re-download the walnut reconstructions: ``tools/fetch_reconstructions.py``
needs 19 GB from Zenodo and ``docs/DATA.md`` describes it. Stages that read
``data/walnut`` fail with a clear message when it is absent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LEDGER = RESULTS / "pipeline_run.json"
LOG = RESULTS / "pipeline_run.log"

TRAINING_SAMPLES = 192
TRAINING_CHUNK = 16
TOTAL_STEPS = 4000
BETA_SELECTION_STEPS = 1200


def _chunks(start: int, stop: int, step: int) -> list[tuple[int, int]]:
    return [(i, min(i + step, stop)) for i in range(start, stop, step)]


def _training_data_steps(script: str, out_dir: str) -> list[dict]:
    steps = []
    for a, b in _chunks(0, TRAINING_SAMPLES, TRAINING_CHUNK):
        steps.append(
            {
                "outputs": [f"{out_dir}/sample_{i:04d}.npz" for i in range(a, b)],
                "argv": [script, "--start", str(a), "--stop", str(b)],
            }
        )
    return steps


def _eval_steps(
    script: str,
    stem: str,
    bounds: list[tuple[int, int]],
    width: int = 4,
    extra: list[str] | None = None,
    merge_extra: list[str] | None = None,
    part_suffix: str = "json",
) -> list[dict]:
    """Chunk steps plus the merge, for the --start/--stop/--merge tools."""
    extra = extra or []
    steps = []
    for a, b in bounds:
        part = f"results/{stem}_part{a:0{width}d}_{b:0{width}d}.{part_suffix}"
        steps.append(
            {
                "outputs": [part],
                "argv": [script, *extra, "--start", str(a), "--stop", str(b)],
            }
        )
    steps.append(
        {
            "outputs": [f"results/{stem}.json"],
            "argv": [script, *extra, "--merge", *(merge_extra or [])],
        }
    )
    return steps


# Stages run in this order. ``needs`` names stages whose failure makes this one
# meaningless; the run skips a stage whose dependency failed rather than letting
# it read a stale or missing input.
STAGES: list[dict] = [
    {
        "name": "reference_tables",
        "what": "XCOM mass attenuation (xraylib) and the 120 kVp spectrum (SpekPy)",
        "steps": [
            {"outputs": [], "argv": ["tools/make_material_table.py"]},
            {"outputs": [], "argv": ["tools/make_spectrum.py"]},
        ],
    },
    {
        "name": "quantitation_baseline",
        "what": "noiseless decomposition baseline, 8 size/concentration rows",
        "needs": ["reference_tables"],
        "steps": _eval_steps(
            "tools/quantitation_baseline.py",
            "quantitation_baseline",
            _chunks(0, 8, 2),
            width=2,
        ),
    },
    {
        "name": "detectability_spectrum",
        "what": "NPWE and ideal-observer d'(E), 6 frozen conditions",
        "needs": ["reference_tables"],
        "steps": _eval_steps(
            "tools/detectability_spectrum.py",
            "detectability_spectrum",
            _chunks(0, 6, 1),
            merge_extra=["--plot"],
        ),
    },
    {
        "name": "training_data_d1",
        "what": "192 simulation-arm training phantoms",
        "needs": ["reference_tables"],
        "steps": _training_data_steps("tools/make_training_data.py", "data/training"),
    },
    {
        "name": "train_d1",
        "what": f"D1 denoiser, {TOTAL_STEPS} steps",
        "needs": ["training_data_d1"],
        "steps": [
            {
                "outputs": ["results/denoiser_weights.pt"],
                "argv": [
                    "tools/train_denoiser.py",
                    "--steps-per-run",
                    str(TOTAL_STEPS),
                ],
            }
        ],
    },
    {
        "name": "denoised_eval_d1",
        "what": "Raw / D1 / noiseless detectability and quantitation",
        "needs": ["train_d1", "detectability_spectrum"],
        "steps": _eval_steps(
            "tools/denoised_eval.py",
            "denoised_eval",
            _chunks(0, 6, 1),
            merge_extra=["--plot"],
        ),
    },
    {
        "name": "tv_weight_selection",
        "what": "3-D TV weight chosen on the frozen criterion",
        "needs": ["training_data_d1"],
        "steps": [
            {
                "outputs": ["results/tv_weight_selection.json"],
                "argv": ["tools/tv_weight_selection.py"],
            }
        ],
    },
    {
        "name": "tv_eval",
        "what": "3-D TV control arm on the 9 sensitivity conditions",
        "needs": ["train_d1", "tv_weight_selection"],
        "steps": _eval_steps("tools/tv_eval.py", "tv_eval", _chunks(0, 9, 1)),
    },
    {
        "name": "sensitivity_eval",
        "what": "eye-filter sweep, CHO, and the 12.5 % extrapolation",
        "needs": ["train_d1"],
        "steps": _eval_steps(
            "tools/sensitivity_eval.py", "sensitivity_eval", _chunks(0, 9, 1)
        ),
    },
    {
        "name": "train_d2_beta_selection",
        "what": f"spectral-loss beta candidates, {BETA_SELECTION_STEPS} steps each",
        "needs": ["training_data_d1"],
        "steps": [
            {
                "outputs": [f"results/denoiser_{tag}_weights.pt"],
                "argv": [
                    "tools/train_denoiser.py",
                    "--spectral-beta",
                    beta,
                    "--suffix",
                    f"_{tag}",
                    "--total-steps",
                    str(BETA_SELECTION_STEPS),
                    "--steps-per-run",
                    str(BETA_SELECTION_STEPS),
                ],
            }
            for tag, beta in (("d2b03", "0.3"), ("d2b10", "1.0"), ("d2b30", "3.0"))
        ],
    },
    {
        "name": "train_d2",
        "what": f"D2 arm at the selected beta = 3.0, {TOTAL_STEPS} steps",
        "needs": ["train_d2_beta_selection"],
        "steps": [
            {
                "outputs": ["results/denoiser_d2_weights.pt"],
                "argv": [
                    "tools/train_denoiser.py",
                    "--spectral-beta",
                    "3.0",
                    "--suffix",
                    "_d2",
                    "--steps-per-run",
                    str(TOTAL_STEPS),
                ],
            }
        ],
    },
    {
        "name": "denoised_eval_d2",
        "what": "the same evaluation for the D2 arm (H3)",
        "needs": ["train_d2"],
        "steps": _eval_steps(
            "tools/denoised_eval.py",
            "denoised_eval_d2",
            _chunks(0, 6, 1),
            extra=[
                "--weights",
                "results/denoiser_d2_weights.pt",
                "--final",
                "denoised_eval_d2.json",
            ],
            merge_extra=["--plot"],
        ),
    },
    {
        "name": "compare_d1_d2",
        "what": "the D1/D2 table the H3 verdict rests on (prints, writes nothing)",
        "needs": ["denoised_eval_d1", "denoised_eval_d2"],
        "steps": [{"outputs": [], "argv": ["tools/compare_d1_d2.py"]}],
    },
    {
        "name": "walnut_noise_model_d025",
        "what": "photon statistics and NPS for the 25 % walnut arm",
        "needs": ["reference_tables"],
        "steps": _eval_steps(
            "tools/walnut_noise_model.py",
            "walnut_noise_model_d0.25",
            _chunks(0, 32, 8),
            extra=["--dose", "0.25"],
            part_suffix="npz",
        ),
    },
    {
        "name": "walnut_noise_model_d0125",
        "what": "the same at 12.5 % (outside the training dose range)",
        "needs": ["reference_tables"],
        "steps": _eval_steps(
            "tools/walnut_noise_model.py",
            "walnut_noise_model_d0.125",
            _chunks(0, 32, 8),
            extra=["--dose", "0.125"],
            part_suffix="npz",
        ),
    },
    {
        "name": "training_data_d1w",
        "what": "192 walnut-configuration training phantoms",
        "needs": ["reference_tables"],
        "steps": _training_data_steps(
            "tools/make_training_data_walnut.py", "data/training_walnut"
        ),
    },
    {
        "name": "train_d1w",
        "what": f"D1w denoiser, 2 channels, {TOTAL_STEPS} steps",
        "needs": ["training_data_d1w"],
        "steps": [
            {
                "outputs": ["results/denoiser_d1w_weights.pt"],
                "argv": [
                    "tools/train_denoiser_walnut.py",
                    "--steps-per-run",
                    str(TOTAL_STEPS),
                ],
            }
        ],
    },
    {
        "name": "walnut_eval_d025",
        "what": "60 real slices, Raw / D1w / TV, at 25 % dose",
        "needs": ["train_d1w", "walnut_noise_model_d025"],
        "steps": _eval_steps(
            "tools/walnut_eval.py",
            "walnut_eval_d0.25",
            _chunks(500, 560, 12),
            extra=["--dose", "0.25"],
        ),
    },
    {
        "name": "walnut_eval_d0125",
        "what": "the same 60 slices at 12.5 %",
        "needs": ["train_d1w", "walnut_noise_model_d0125"],
        "steps": _eval_steps(
            "tools/walnut_eval.py",
            "walnut_eval_d0.125",
            _chunks(500, 560, 12),
            extra=["--dose", "0.125"],
        ),
    },
    {
        "name": "walnut_summary",
        "what": "per-arm means over slices, both doses",
        "needs": ["walnut_eval_d025", "walnut_eval_d0125"],
        "steps": [
            {
                "outputs": ["results/walnut_eval_summary.json"],
                "argv": ["tools/walnut_summary.py"],
            }
        ],
    },
    {
        "name": "walnut_preview",
        "what": "the 40 keV preview image of each arm",
        "needs": ["train_d1w", "walnut_noise_model_d025"],
        "steps": [
            {
                "outputs": ["results/walnut_preview_d0.25.png"],
                "argv": ["tools/walnut_preview.py"],
            }
        ],
    },
    {
        "name": "tests",
        "what": "the unit suite, in the environment that just produced the results",
        "steps": [{"outputs": [], "argv": ["-m", "pytest", "-q"]}],
    },
]


def _have(outputs: list[str]) -> bool:
    return bool(outputs) and all((ROOT / o).exists() for o in outputs)


def _run(argv: list[str], log) -> tuple[int, float]:
    cmd = [sys.executable, *argv]
    t0 = time.time()
    log.write("\n$ " + " ".join(cmd) + "\n")
    log.flush()
    env = dict(os.environ)
    # The children print em dashes and micro signs; this run is about the numbers,
    # and a console codepage is not one of them. CI covers the cp932 path
    # separately (.github/workflows/tests.yml).
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log.write(proc.stdout or "")
    log.flush()
    return proc.returncode, time.time() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print the stages and exit")
    ap.add_argument("--only", nargs="+", metavar="STAGE")
    ap.add_argument("--from", dest="from_stage", metavar="STAGE")
    ap.add_argument("--force", action="store_true", help="re-run stages already done")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    names = [s["name"] for s in STAGES]
    if args.list:
        for s in STAGES:
            print(f"{s['name']:28s} {s['what']}")
        return
    for given in list(args.only or []) + ([args.from_stage] if args.from_stage else []):
        if given not in names:
            raise SystemExit(f"unknown stage {given!r}; --list shows them")

    selected = names
    if args.from_stage:
        selected = names[names.index(args.from_stage) :]
    if args.only:
        selected = [n for n in selected if n in args.only]

    RESULTS.mkdir(exist_ok=True)
    ledger: dict[str, dict] = {}
    if LEDGER.exists():
        ledger = json.loads(LEDGER.read_text(encoding="utf-8")).get("stages", {})
    failed: set[str] = {n for n, v in ledger.items() if v.get("status") == "failed"}
    t_all = time.time()

    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n==== run_pipeline {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n")
        for stage in STAGES:
            name = stage["name"]
            if name not in selected:
                continue
            blocked = [d for d in stage.get("needs", []) if d in failed]
            if blocked:
                print(f"[{name}] SKIPPED, depends on failed {', '.join(blocked)}")
                ledger[name] = {"status": "skipped", "blocked_by": blocked}
                failed.add(name)
                continue
            todo = [
                st
                for st in stage["steps"]
                if args.force or not _have(st["outputs"])
            ]
            if not todo:
                print(f"[{name}] done already ({len(stage['steps'])} steps)")
                ledger.setdefault(name, {"status": "present"})
                continue
            if args.dry_run:
                print(f"[{name}] would run {len(todo)}/{len(stage['steps'])} steps")
                for st in todo:
                    print("    " + " ".join(st["argv"]))
                continue
            print(
                f"[{name}] {len(todo)}/{len(stage['steps'])} steps - {stage['what']}",
                flush=True,
            )
            t0 = time.time()
            status, error = "ok", None
            for st in todo:
                code, secs = _run(st["argv"], log)
                print(f"    {' '.join(st['argv'][:3])} ... {secs:.0f}s", flush=True)
                if code != 0:
                    status, error = "failed", f"exit {code}: {' '.join(st['argv'])}"
                    print(f"    FAILED {error} (see {LOG})", flush=True)
                    failed.add(name)
                    break
            missing = [
                o
                for st in stage["steps"]
                for o in st["outputs"]
                if not (ROOT / o).exists()
            ]
            if status == "ok" and missing:
                status = "failed"
                error = f"finished but did not write: {', '.join(missing)}"
                print(f"    FAILED {error}", flush=True)
                failed.add(name)
            ledger[name] = {
                "status": status,
                "seconds": round(time.time() - t0, 1),
                "steps_run": len(todo),
                "steps_total": len(stage["steps"]),
                "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            if error:
                ledger[name]["error"] = error
            LEDGER.write_text(
                json.dumps(
                    {
                        "python": sys.version.split()[0],
                        "root": str(ROOT),
                        "stages": ledger,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    if args.dry_run:
        return
    print(f"\ntotal {(time.time() - t_all) / 60:.1f} min")
    bad = [n for n, v in ledger.items() if v.get("status") in ("failed", "skipped")]
    if bad:
        print("not ok: " + ", ".join(bad))
        raise SystemExit(1)
    print("every stage ok")


if __name__ == "__main__":
    main()
