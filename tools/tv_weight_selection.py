"""Select the frozen TV weight constant c for the S5-3 control arm.

The TV weight per stack is ``weight = c * sigma_hat^2`` with ``sigma_hat``
from :func:`pcctvmi.tv.laplacian_noise_sd` (robust per-stack noise SD, no
knowledge of the dose condition). This script picks c by minimising the L2
error to the noiseless teacher on *validation* crops of the Sprint-3
training pool (indices 160-191) — the frozen evaluation conditions are
never touched, per PROTOCOL_FREEZE.md S5-3.

    python tools/tv_weight_selection.py [--samples 6] [--candidates 0.5 1 2 4 8 16]

Prints the MSE table and the selected c; the value is then frozen in
docs/PROTOCOL_FREEZE.md and hard-coded in tools/tv_eval.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pcctvmi.materials import mu_rho  # noqa: E402
from pcctvmi.tv import chambolle_tv_3d, laplacian_noise_sd  # noqa: E402
from pcctvmi.vmi import VMI_GRID_KEV  # noqa: E402

DATA = ROOT / "data" / "training"
CROP = 128
VAL = list(range(160, 192))  # S3-6 frozen validation split
# Frozen keV-grid iodine/water attenuation ratios (same construction as
# tools/train_denoiser.py).
_R = np.asarray(
    [float(mu_rho("iodine", float(e)) / mu_rho("water", float(e))) for e in VMI_GRID_KEV]
)


def _crop_pair(idx: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    path = DATA / f"sample_{idx:04d}.npz"
    with np.load(path) as npz:
        a_n = np.asarray(npz["a_noisy"], dtype=np.float64)
        b_n = np.asarray(npz["b_noisy"], dtype=np.float64)
        a_c = np.asarray(npz["a_clean"], dtype=np.float64)
        b_c = np.asarray(npz["b_clean"], dtype=np.float64)
    off = int(rng.integers(0, a_n.shape[0] - CROP))
    sl = (slice(off, off + CROP), slice(off, off + CROP))
    noisy = 1000.0 * (a_n[sl][None] + b_n[sl][None] * _R[:, None, None] - 1.0)
    clean = 1000.0 * (a_c[sl][None] + b_c[sl][None] * _R[:, None, None] - 1.0)
    return noisy, clean


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--crops", type=int, default=2, help="random crops per sample")
    ap.add_argument("--candidates", type=float, nargs="+", default=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0])
    ap.add_argument("--n-iter", type=int, default=300)
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "tv_weight_selection.json")
    args = ap.parse_args()

    rng = np.random.default_rng(20261019)  # frozen selection seed, disjoint from eval seeds
    pairs = [_crop_pair(idx, rng) for idx in VAL[: args.samples] for _ in range(args.crops)]

    table: dict[float, list[float]] = {float(c): [] for c in args.candidates}
    for noisy, clean in pairs:
        sigma_hat = laplacian_noise_sd(noisy)
        base = float(np.mean((noisy - clean) ** 2))
        for c in args.candidates:
            out = chambolle_tv_3d(noisy, float(c) * sigma_hat**2, n_iter=args.n_iter)
            table[float(c)].append(float(np.mean((out - clean) ** 2)) / base)

    means = {c: float(np.mean(v)) for c, v in table.items()}
    for c, m in means.items():
        print(f"c={c:>5}: relative MSE = {m:.4f}")
    best = min(means.items(), key=lambda kv: kv[1])[0]
    print(f"selected c = {best} (relative MSE {means[best]:.4f})")
    args.out.write_text(
        json.dumps(
            {
                "config": {
                    "samples": VAL[: args.samples],
                    "crops": args.crops,
                    "n_iter": args.n_iter,
                    "selection_seed": 20261019,
                    "baseline_relative_mse": 1.0,
                },
                "relative_mse": {str(c): m for c, m in means.items()},
                "selected_c": best,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
