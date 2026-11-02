"""Compare two ``results/`` trees value by value, and say where they part.

A re-execution that is only inspected by eye is a re-execution nobody can
check, so this reads both trees and reports the largest disagreement in every
file: JSON and JSONL numerically down to the leaf, ``.npz`` and ``.pt`` array by
array, and anything else by bytes.

It prints the measured deviation rather than a verdict word, because the
interesting answer is how far apart the two runs are, not whether they cleared a
threshold someone chose afterwards. The exit status is non-zero when any value
is outside the tolerance, when a file is missing from either side, or when the
two trees disagree in shape.

Arrays are summarised rather than hashed, so that a last-bit difference is
reported as a small number instead of as a wall of mismatches. A summary chosen
carelessly cannot fail: shape, sum, sum of squares and maximum magnitude are all
invariant under a permutation of the elements, so a stage that scrambled its
output would pass. Each array therefore also carries a position-weighted moment,
which no permutation leaves alone and which still degrades smoothly when the two
runs differ only in the last bits.

Usage::

    python tools/compare_results.py REFERENCE_DIR RERUN_DIR
    python tools/compare_results.py ../tag_results results --rtol 1e-6
    python tools/compare_results.py ../tag_results results --ignore config.weights
    python tools/compare_results.py --selftest

``--ignore`` takes dotted leaf paths and is printed in the report, so a tolerated
difference stays visible instead of disappearing into the code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np

SKIP_SUFFIXES = {".log"}


def _flatten(obj, prefix: str = "") -> dict[str, object]:
    """Leaf path -> value, so two files can be compared without assuming a shape."""
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def _deviation(a, b) -> tuple[float, bool]:
    """(relative deviation, comparable). Non-numbers compare equal or not."""
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)):
        return (0.0 if a == b else math.inf, False)
    if not isinstance(b, (int, float)):
        return (math.inf, False)
    if math.isnan(a) or math.isnan(b):
        return (0.0 if (math.isnan(a) and math.isnan(b)) else math.inf, True)
    if a == b:
        return (0.0, True)
    scale = max(abs(a), abs(b))
    return ((abs(a - b) / scale if scale else abs(a - b)), True)


def _array_summary(arr: np.ndarray, name: str) -> dict[str, object]:
    """Numbers that pin an array without printing it, permutations included."""
    out: dict[str, object] = {
        f"{name}.shape": str(tuple(arr.shape)),
        f"{name}.dtype": str(arr.dtype),
    }
    if not arr.size or not np.issubdtype(arr.dtype, np.number):
        return out
    flat = np.asarray(arr).ravel()
    if np.iscomplexobj(flat):
        flat = np.concatenate([flat.real, flat.imag])
    flat = flat.astype(np.float64)
    finite = flat[np.isfinite(flat)]
    out[f"{name}.sum"] = float(np.sum(finite))
    out[f"{name}.sq"] = float(np.sum(finite**2))
    out[f"{name}.absmax"] = float(np.max(np.abs(finite))) if finite.size else 0.0
    out[f"{name}.nonfinite"] = int(flat.size - finite.size)
    # Position-weighted moment: a permutation of the elements changes it, which
    # none of the statistics above do. Normalised so it stays the same order of
    # magnitude as the values themselves.
    ramp = np.arange(1, flat.size + 1, dtype=np.float64) / flat.size
    out[f"{name}.moment"] = float(np.sum(np.nan_to_num(flat, posinf=0.0, neginf=0.0) * ramp))
    return out


def _load_json(path: Path) -> dict:
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _load_jsonl(path: Path) -> dict:
    out: dict[str, object] = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            out.update(_flatten(json.loads(line), f"[{i}]"))
    return out


def _load_npz(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        out: dict[str, object] = {}
        for name in z.files:
            out.update(_array_summary(np.asarray(z[name]), name))
    return out


def _load_pt(path: Path) -> dict:
    import torch  # imported here so a JSON-only comparison needs no torch

    state = torch.load(path, map_location="cpu", weights_only=False)
    if hasattr(state, "state_dict"):
        state = state.state_dict()
    out: dict[str, object] = {}
    stack = [("", state)]
    while stack:
        prefix, obj = stack.pop()
        if isinstance(obj, dict):
            for k, v in obj.items():
                stack.append((f"{prefix}.{k}" if prefix else str(k), v))
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                stack.append((f"{prefix}[{i}]", v))
        elif hasattr(obj, "detach"):
            out.update(_array_summary(obj.detach().cpu().numpy(), prefix))
        elif isinstance(obj, (int, float, str)):
            out[prefix] = obj
    return out


LOADERS = {
    ".json": _load_json,
    ".jsonl": _load_jsonl,
    ".npz": _load_npz,
    ".pt": _load_pt,
}


def _compare_mapping(left: dict, right: dict, ignore: set[str]) -> dict:
    worst = (0.0, None, None, None)
    numeric = 0
    text_diffs = []
    for key in sorted(set(left) & set(right)):
        if key in ignore:
            continue
        dev, is_num = _deviation(left[key], right[key])
        if is_num:
            numeric += 1
            if dev > worst[0]:
                worst = (dev, key, left[key], right[key])
        elif dev:
            text_diffs.append((key, left[key], right[key]))
    return {
        "leaves": len(set(left) & set(right)),
        "numeric_leaves": numeric,
        "only_reference": sorted(set(left) - set(right) - ignore),
        "only_rerun": sorted(set(right) - set(left) - ignore),
        "worst": {
            "relative": worst[0],
            "path": worst[1],
            "reference": worst[2],
            "rerun": worst[3],
        },
        "text_differences": [
            {"path": k, "reference": a, "rerun": b} for k, a, b in text_diffs[:20]
        ],
        "text_difference_count": len(text_diffs),
    }


def compare_trees(
    reference: Path,
    rerun: Path,
    rtol: float = 1e-9,
    ignore: set[str] | None = None,
    include_parts: bool = False,
) -> tuple[dict, list[str], tuple[float, str | None, str | None], list[str]]:
    """(per-file report, problems, (worst relative, file, leaf), printable lines)."""
    ignore = set(ignore or ())
    names = sorted(
        {
            p.name
            for d in (reference, rerun)
            if d.is_dir()
            for p in d.iterdir()
            if p.is_file() and p.suffix not in SKIP_SUFFIXES
        }
    )
    if not include_parts:
        names = [n for n in names if "_part" not in n]
    report: dict[str, dict] = {}
    problems: list[str] = []
    lines: list[str] = [f"{'file':44s} {'leaves':>7s} {'max rel':>11s}  note"]
    worst_overall: tuple[float, str | None, str | None] = (0.0, None, None)
    for name in names:
        a, b = reference / name, rerun / name
        if not a.exists() or not b.exists():
            side = "reference" if not a.exists() else "rerun"
            report[name] = {"status": f"missing from {side}"}
            problems.append(f"{name}: missing from {side}")
            lines.append(f"{name:44s} {'-':>7s} {'-':>11s}  MISSING from {side}")
            continue
        loader = LOADERS.get(a.suffix)
        if loader is None:
            same = a.read_bytes() == b.read_bytes()
            report[name] = {"status": "identical bytes" if same else "bytes differ"}
            if not same:
                problems.append(f"{name}: bytes differ (no value reader for {a.suffix})")
            lines.append(
                f"{name:44s} {'-':>7s} {'-':>11s}  "
                + ("identical bytes" if same else "BYTES DIFFER")
            )
            continue
        try:
            res = _compare_mapping(loader(a), loader(b), ignore)
        except Exception as exc:  # a file that cannot be read is a finding
            report[name] = {"status": f"unreadable: {type(exc).__name__}: {exc}"}
            problems.append(f"{name}: unreadable ({type(exc).__name__}: {exc})")
            lines.append(f"{name:44s} {'-':>7s} {'-':>11s}  UNREADABLE {exc}")
            continue
        report[name] = res
        notes = []
        if res["only_reference"]:
            notes.append(f"{len(res['only_reference'])} leaves only in reference")
            problems.append(
                f"{name}: {len(res['only_reference'])} leaves missing from the rerun "
                f"({', '.join(res['only_reference'][:3])})"
            )
        if res["only_rerun"]:
            notes.append(f"{len(res['only_rerun'])} leaves only in rerun")
            problems.append(
                f"{name}: {len(res['only_rerun'])} leaves the reference does not have "
                f"({', '.join(res['only_rerun'][:3])})"
            )
        if res["text_difference_count"]:
            notes.append(f"{res['text_difference_count']} non-numeric differ")
            for d in res["text_differences"][:5]:
                problems.append(
                    f"{name}: {d['path']} is {d['reference']!r} -> {d['rerun']!r}"
                )
        rel = res["worst"]["relative"]
        if rel > rtol:
            notes.append(f"over rtol at {res['worst']['path']}")
            problems.append(
                f"{name}: {rel:.3e} at {res['worst']['path']} "
                f"({res['worst']['reference']} -> {res['worst']['rerun']})"
            )
        if rel > worst_overall[0]:
            worst_overall = (rel, name, res["worst"]["path"])
        lines.append(f"{name:44s} {res['leaves']:7d} {rel:11.3e}  " + "; ".join(notes))
    return report, problems, worst_overall, lines


# --------------------------------------------------------------------------
# self-test: plant a defect of each kind and require that it is reported


def _make_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "eval.json").write_text(
        json.dumps(
            {
                "config": {"replicates": 64, "note": "frozen", "seed_base": 20261017},
                "conditions": [
                    {"size_cm": 0.3, "d_prime": 2.5, "bias": -2.10},
                    {"size_cm": 0.5, "d_prime": 4.0, "bias": -2.59},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "train_log.jsonl").write_text(
        "\n".join(
            json.dumps({"step": s, "val_l2": 1000.0 / (s + 1)}) for s in (0, 150, 300)
        )
        + "\n",
        encoding="utf-8",
    )
    rng = np.random.default_rng(7)
    np.savez(
        root / "noise_model.npz",
        nps=rng.normal(size=(8, 8)),
        cross=rng.normal(size=(4, 4)),
    )
    (root / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixels" * 10)


def _edit_json(path: Path, mutate) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _permute_npz(path: Path) -> None:
    """Scramble one array in place, keeping sum, sum of squares and maximum."""
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: np.array(z[k]) for k in z.files}
    flat = arrays["nps"].ravel()
    arrays["nps"] = flat[::-1].reshape(arrays["nps"].shape)
    np.savez(path, **arrays)


CASES: list[tuple[str, object, str]] = [
    (
        "a result moves in the sixth digit",
        lambda d: _edit_json(
            d / "eval.json",
            lambda o: o["conditions"][0].__setitem__("d_prime", 2.5000025),
        ),
        "eval.json",
    ),
    (
        "a bias flips sign",
        lambda d: _edit_json(
            d / "eval.json", lambda o: o["conditions"][1].__setitem__("bias", 2.59)
        ),
        "eval.json",
    ),
    (
        "a number becomes null",
        lambda d: _edit_json(
            d / "eval.json", lambda o: o["conditions"][0].__setitem__("d_prime", None)
        ),
        "eval.json",
    ),
    (
        "a leaf disappears",
        lambda d: _edit_json(
            d / "eval.json", lambda o: o["config"].pop("replicates")
        ),
        "eval.json",
    ),
    (
        "a leaf appears",
        lambda d: _edit_json(
            d / "eval.json", lambda o: o["config"].__setitem__("replicates_2", 32)
        ),
        "eval.json",
    ),
    (
        "a configuration string changes",
        lambda d: _edit_json(
            d / "eval.json", lambda o: o["config"].__setitem__("note", "thawed")
        ),
        "eval.json",
    ),
    (
        "a training log line changes",
        lambda d: (d / "train_log.jsonl").write_text(
            (d / "train_log.jsonl")
            .read_text(encoding="utf-8")
            .replace('"val_l2": 1000.0', '"val_l2": 999.9'),
            encoding="utf-8",
        ),
        "train_log.jsonl",
    ),
    (
        "a training log is truncated",
        lambda d: (d / "train_log.jsonl").write_text(
            "\n".join(
                (d / "train_log.jsonl").read_text(encoding="utf-8").splitlines()[:2]
            )
            + "\n",
            encoding="utf-8",
        ),
        "train_log.jsonl",
    ),
    (
        "an array element shifts",
        lambda d: _scale_npz(d / "noise_model.npz", "cross", 1.000001),
        "noise_model.npz",
    ),
    (
        "an array is permuted, leaving sum and sum of squares intact",
        lambda d: _permute_npz(d / "noise_model.npz"),
        "noise_model.npz",
    ),
    (
        "an array changes shape",
        lambda d: _reshape_npz(d / "noise_model.npz"),
        "noise_model.npz",
    ),
    (
        "an array picks up a NaN",
        lambda d: _nan_npz(d / "noise_model.npz"),
        "noise_model.npz",
    ),
    (
        "a figure is not the same image",
        lambda d: (d / "preview.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"PIXELS" * 10
        ),
        "preview.png",
    ),
    (
        "a result file is missing",
        lambda d: (d / "eval.json").unlink(),
        "eval.json",
    ),
    (
        "a result file nobody asked for appears",
        lambda d: (d / "extra_eval.json").write_text("{}", encoding="utf-8"),
        "extra_eval.json",
    ),
]


def _scale_npz(path: Path, key: str, factor: float) -> None:
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: np.array(z[k]) for k in z.files}
    arrays[key] = arrays[key] * factor
    np.savez(path, **arrays)


def _reshape_npz(path: Path) -> None:
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: np.array(z[k]) for k in z.files}
    arrays["nps"] = arrays["nps"].reshape(4, 16)
    np.savez(path, **arrays)


def _nan_npz(path: Path) -> None:
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: np.array(z[k]) for k in z.files}
    arrays["cross"][0, 0] = np.nan
    np.savez(path, **arrays)


def selftest() -> int:
    """Every planted defect must be reported, and an untouched copy must not be."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        ref = base / "reference"
        _make_reference(ref)

        control = base / "control"
        shutil.copytree(ref, control)
        _, problems, worst, _ = compare_trees(ref, control, rtol=1e-9)
        quiet = not problems
        print(
            "  %-8s %s (largest deviation %.1e)"
            % (
                "SILENT" if quiet else "NOISY",
                "an untouched copy",
                worst[0],
            )
        )
        if not quiet:
            ok = False
            for p in problems:
                print("           unexpected: " + p)

        for i, (what, plant, expect_file) in enumerate(CASES):
            case = base / f"case{i:02d}"
            shutil.copytree(ref, case)
            before = _fingerprint(case)
            plant(case)
            if _fingerprint(case) == before:
                print("  NO-OP    %s (the injection changed nothing)" % what)
                ok = False
                continue
            _, problems, _, _ = compare_trees(ref, case, rtol=1e-9)
            hit = any(p.startswith(expect_file + ":") for p in problems)
            print(
                "  %-8s %s"
                % ("DETECTED" if hit else "MISSED", what)
            )
            if hit:
                print("           " + problems[0])
            else:
                ok = False
                print(
                    "           expected a finding about %s, got: %s"
                    % (expect_file, problems or "nothing")
                )
    print("selftest %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _fingerprint(root: Path) -> list[tuple[str, str]]:
    """Whole-file digests. A prefix or a size would call a changed array unchanged."""
    return sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.iterdir()
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reference", type=Path, nargs="?")
    ap.add_argument("rerun", type=Path, nargs="?")
    ap.add_argument("--rtol", type=float, default=1e-9)
    ap.add_argument("--ignore", nargs="*", default=[])
    ap.add_argument("--out", type=Path, default=None, help="write the report as JSON")
    ap.add_argument(
        "--include-parts",
        action="store_true",
        help="also compare the _part* chunk intermediates",
    )
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.reference or not args.rerun:
        ap.error("give REFERENCE_DIR and RERUN_DIR, or --selftest")

    ignore = set(args.ignore)
    report, problems, worst, lines = compare_trees(
        args.reference, args.rerun, args.rtol, ignore, args.include_parts
    )
    if not report:
        raise SystemExit("nothing to compare")
    for line in lines:
        print(line)
    print(
        f"\nlargest relative deviation {worst[0]:.3e}"
        + (f" in {worst[1]} at {worst[2]}" if worst[1] else "")
    )
    if ignore:
        print("ignored leaf paths: " + ", ".join(sorted(ignore)))
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "reference": str(args.reference),
                    "rerun": str(args.rerun),
                    "rtol": args.rtol,
                    "ignored": sorted(ignore),
                    "largest_relative_deviation": worst[0],
                    "files": report,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.out}")
    if problems:
        print(f"\n{len(problems)} disagreement(s):")
        for p in problems:
            print("  " + p)
        return 1
    print(f"every file agrees within rtol {args.rtol:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
