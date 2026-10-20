"""Train the frozen VMI denoiser (S3-2..S3-7; D2 spectral term: §11).

Data: the 192 generated phantoms in ``data/training/`` (S3-5), split into
160 train / 32 val by index (S3-6). Random 128^2 crops are drawn on the fly
from the stored 512^2 decomposition pairs; both the model input (noisy VMI
stack) and the teacher (noiseless VMI stack) are synthesized from (a, b) with
the frozen keV grid, so the energy axis is never resampled.

Loss (S3-4): L2 to the noiseless teacher + 0.1 * L1 on first differences
(high-frequency preservation). The Raw image enters neither the teacher nor
the loss. With ``--spectral-beta B`` the D2 arm (PROTOCOL_FREEZE.md §11)
adds B * mean((1000*da)^2 + (1000*db)^2) against the *noiseless teacher's*
decomposition — a reweighting of the keV-domain L2 toward the spectral
subspace, NOT a Raw-referenced term (§6.1 forbids that; see §11 for the
revision rationale).

Resumable: ``--steps-per-run`` limits each invocation; the checkpoint
carries model, optimiser, step count and the crop-sampling generator state,
so consecutive invocations continue the identical training trajectory.
``--suffix`` keeps runs separate (D1: none, D2: "_d2", selection: "_d2_b*" ).

    python tools/train_denoiser.py --steps-per-run 150   # repeat until done

Final weights are written to ``results/denoiser<suffix>_weights.pt`` when
``--total-steps`` (default 4000) is reached. Training/val metrics are
appended to ``results/denoiser<suffix>_log.jsonl``: val_loss (at the run's
training beta), val_l2 (keV MSE), val_b2 (mean (1000*db)^2 mgI-scale MSE)
and val_criterion (the beta=1 selection criterion used for the D2 weight
search — frozen so candidates are compared on an identical metric).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from pcctvmi.denoiser import VMIDenoiser, n_parameters
from pcctvmi.materials import mu_rho
from pcctvmi.projection import fit_basis_torch, gram_matrix
from pcctvmi.vmi import VMI_GRID_KEV

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "training"
RESULTS = ROOT / "results"
N_SAMPLES = 192
N_TRAIN = 160  # S3-6: first 160 train, last 32 val
CROP = 128
BATCH = 16
LR = 1e-3  # S3-7
GRAD_L1_WEIGHT = 0.1  # S3-4
SEED = 20261019  # S3-5 training seed base
TOTAL_STEPS_DEFAULT = 4000  # S3-7

# Frozen keV-grid iodine/water attenuation ratios (VMI synthesis in torch).
_R = torch.tensor(
    [float(mu_rho("iodine", float(e)) / mu_rho("water", float(e))) for e in VMI_GRID_KEV],
    dtype=torch.float32,
)
_GRAM = gram_matrix()


def _load_split(indices: list[int]) -> dict[int, dict[str, np.ndarray]]:
    """Load (a, b) pairs for the given sample indices into memory (float32)."""
    cache: dict[int, dict[str, np.ndarray]] = {}
    for idx in indices:
        path = DATA / f"sample_{idx:04d}.npz"
        with np.load(path) as npz:
            cache[idx] = {
                "a_noisy": np.asarray(npz["a_noisy"], dtype=np.float32),
                "b_noisy": np.asarray(npz["b_noisy"], dtype=np.float32),
                "a_clean": np.asarray(npz["a_clean"], dtype=np.float32),
                "b_clean": np.asarray(npz["b_clean"], dtype=np.float32),
            }
    return cache


def _crop_pair(
    cache: dict[int, dict[str, np.ndarray]], idx: int, y: int, x: int
) -> tuple[torch.Tensor, torch.Tensor]:
    s = cache[idx]
    sl = (slice(y, y + CROP), slice(x, x + CROP))
    a_n = torch.from_numpy(s["a_noisy"][sl])
    b_n = torch.from_numpy(s["b_noisy"][sl])
    a_c = torch.from_numpy(s["a_clean"][sl])
    b_c = torch.from_numpy(s["b_clean"][sl])
    noisy = 1000.0 * (a_n[None] + b_n[None] * _R[:, None, None] - 1.0)
    clean = 1000.0 * (a_c[None] + b_c[None] * _R[:, None, None] - 1.0)
    return noisy, clean


def _draw_batch(
    cache: dict[int, dict[str, np.ndarray]],
    indices: list[int],
    generator: torch.Generator,
) -> tuple[torch.Tensor, torch.Tensor]:
    n = int(_R.shape[0])
    noisy = torch.empty(len(indices), n, CROP, CROP)
    clean = torch.empty(len(indices), n, CROP, CROP)
    limit = 512 - CROP
    for i, idx in enumerate(indices):
        y = int(torch.randint(0, limit + 1, (1,), generator=generator))
        x = int(torch.randint(0, limit + 1, (1,), generator=generator))
        noisy[i], clean[i] = _crop_pair(cache, idx, y, x)
    return noisy, clean


def _spectral_mse(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """D2 term: MSE of the (a, b) decomposition coordinates (§11).

    Both stacks are decomposed per pixel with the frozen closed-form 2x2
    normal equations; densities are scaled by 1000 so the term lives on the
    same numerical scale as the keV-domain HU^2 L2.
    """
    a_p, b_p = fit_basis_torch(pred, _R, _GRAM)
    a_t, b_t = fit_basis_torch(target, _R, _GRAM)
    return torch.mean((1000.0 * (a_p - a_t)) ** 2 + (1000.0 * (b_p - b_t)) ** 2)


def _loss(pred: torch.Tensor, target: torch.Tensor, spectral_beta: float) -> torch.Tensor:
    l2 = torch.mean((pred - target) ** 2)
    dp = pred[:, :, :, 1:] - pred[:, :, :, :-1]
    dt = target[:, :, :, 1:] - target[:, :, :, :-1]
    dy_p = pred[:, :, 1:, :] - pred[:, :, :-1, :]
    dy_t = target[:, :, 1:, :] - target[:, :, :-1, :]
    grad_l1 = torch.mean(torch.abs(dp - dt)) + torch.mean(torch.abs(dy_p - dy_t))
    out = l2 + GRAD_L1_WEIGHT * grad_l1
    if spectral_beta > 0.0:
        out = out + spectral_beta * _spectral_mse(pred, target)
    return out


def _val_metrics(
    model: VMIDenoiser,
    cache: dict[int, dict[str, np.ndarray]],
    idxs: list[int],
    spectral_beta: float,
) -> dict:
    model.eval()
    totals = {"val_loss": 0.0, "val_l2": 0.0, "val_b2": 0.0, "val_criterion": 0.0}
    with torch.no_grad():
        for start in range(0, len(idxs), 8):
            batch = idxs[start : start + 8]
            noisy = torch.empty(len(batch), int(_R.shape[0]), CROP, CROP)
            clean = torch.empty(len(batch), int(_R.shape[0]), CROP, CROP)
            for i, idx in enumerate(batch):
                # deterministic centre crop for validation
                off = (512 - CROP) // 2
                noisy[i], clean[i] = _crop_pair(cache, idx, off, off)
            pred = model(noisy)
            # The selection criterion is always evaluated at beta = 1 so beta
            # candidates are compared on an identical metric (frozen §11).
            l2 = torch.mean((pred - clean) ** 2)
            b2 = _spectral_mse(pred, clean)
            totals["val_l2"] += float(l2) * len(batch)
            totals["val_b2"] += float(b2) * len(batch)
            totals["val_loss"] += float(_loss(pred, clean, spectral_beta)) * len(batch)
            totals["val_criterion"] += float(l2 + b2) * len(batch)
    model.train()
    return {k: v / len(idxs) for k, v in totals.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps-per-run", type=int, default=150)
    ap.add_argument("--total-steps", type=int, default=TOTAL_STEPS_DEFAULT)
    ap.add_argument(
        "--spectral-beta",
        type=float,
        default=0.0,
        help="D2 spectral-term weight (0 = D1 arm, S3-4 loss unchanged)",
    )
    ap.add_argument(
        "--suffix",
        type=str,
        default="",
        help="output name tag: results/denoiser<suffix>_{checkpoint,weights,log...}",
    )
    args = ap.parse_args()
    if args.spectral_beta < 0.0:
        raise SystemExit("--spectral-beta must be >= 0")
    ckpt = RESULTS / f"denoiser{args.suffix}_checkpoint.pt"
    weights = RESULTS / f"denoiser{args.suffix}_weights.pt"
    log = RESULTS / f"denoiser{args.suffix}_log.jsonl"

    train_cache = _load_split(list(range(N_TRAIN)))
    val_cache = _load_split(list(range(N_TRAIN, N_SAMPLES)))
    val_idxs = list(range(N_TRAIN, N_SAMPLES))
    train_idxs = list(range(N_TRAIN))

    model = VMIDenoiser(n_channels=int(_R.shape[0]))
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    generator = torch.Generator().manual_seed(SEED)

    step = 0
    if ckpt.exists():
        state = torch.load(ckpt, weights_only=False)
        model.load_state_dict(state["model"])
        opt.load_state_dict(state["optimizer"])
        generator.set_state(state["generator"])
        step = int(state["step"])
        print(f"resumed from step {step}")

    print(
        f"train samples={N_TRAIN} val={len(val_idxs)} params={n_parameters(model)} "
        f"spectral_beta={args.spectral_beta} suffix={args.suffix!r}"
    )
    perm = torch.randperm(N_TRAIN, generator=generator).tolist()
    pos = 0
    t0 = time.time()
    log_lines = []
    target = min(args.total_steps, step + args.steps_per_run)
    while step < target:
        if pos + BATCH > N_TRAIN:
            perm = torch.randperm(N_TRAIN, generator=generator).tolist()
            pos = 0
        batch_idxs = [train_idxs[perm[pos + i]] for i in range(BATCH)]
        pos += BATCH
        noisy, clean = _draw_batch(train_cache, batch_idxs, generator)
        opt.zero_grad()
        loss = _loss(model(noisy), clean, args.spectral_beta)
        loss.backward()
        opt.step()
        step += 1
        if step % 25 == 0:
            print(f"step {step} loss {float(loss.detach()):.1f} ({time.time() - t0:.0f}s)")
        if step % 250 == 0 or step == target:
            metrics = _val_metrics(model, val_cache, val_idxs, args.spectral_beta)
            entry = {"step": step, "train_loss": float(loss.detach()), **metrics}
            log_lines.append(entry)
            print(f"step {step} " + " ".join(f"{k} {v:.2f}" for k, v in metrics.items()))

    torch.save(
        {
            "model": model.state_dict(),
            "optimizer": opt.state_dict(),
            "generator": generator.get_state(),
            "step": step,
        },
        ckpt,
    )
    with log.open("a", encoding="utf-8") as fh:
        for entry in log_lines:
            fh.write(json.dumps(entry) + "\n")
    print(f"checkpoint saved at step {step} ({time.time() - t0:.0f}s)")
    if step >= args.total_steps and not weights.exists():
        torch.save(model.state_dict(), weights)
        print(f"final weights -> {weights}")


if __name__ == "__main__":
    main()
