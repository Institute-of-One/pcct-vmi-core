"""Train the D1w denoiser for the H4 walnut arm (S12-5, PROTOCOL_FREEZE.md).

Data: the 192 walnut-config phantoms in ``data/training_walnut/``
(tools/make_training_data_walnut.py), split 160 train / 32 val by index
(S3-6 isomorphic). Random 128^2 crops are drawn on the fly from the stored
1024^2 (Low, High) bin pairs; the model input is the 2-channel bin stack and
the teacher is the noiseless bin stack of the same phantom — no VMI
synthesis, no decomposition (D1w operates on bins, §12.5).

A per-channel DC offset (FLESH_OFFSET_HU, measured on the real walnut eval
slices: flesh mean Low -228 / High -130 HU) is added to BOTH input and
teacher so the training signal distribution sits at the walnut flesh level
instead of the water-disk 0 HU. The S3-4 loss is offset-invariant (L2 and
gradient-L1 differences cancel an identical additive constant), so this
changes only the input distribution, not the objective.

Loss (S3-4, unchanged): L2 to the noiseless teacher + 0.1 * L1 on first
differences. No spectral term (D1 arm).

Resumable: ``--steps-per-run`` limits each invocation; the checkpoint
carries model, optimiser, step count and the crop-sampling generator state.

    python tools/train_denoiser_walnut.py --steps-per-run 250

Final weights land in ``results/denoiser_d1w_weights.pt`` at 4000 steps
(S3-7); metrics append to ``results/denoiser_d1w_log.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from pcctvmi.denoiser import VMIDenoiser, n_parameters

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "training_walnut"
RESULTS = ROOT / "results"
N_SAMPLES = 192
N_TRAIN = 160  # S3-6 isomorphic: first 160 train, last 32 val
CROP = 128
BATCH = 16
LR = 1e-3  # S3-7
GRAD_L1_WEIGHT = 0.1  # S3-4
SEED = 20261022  # S12-5; data and training share one base (S3-5 isomorphic);
# eval seeds (20261020) stay separate
TOTAL_STEPS_DEFAULT = 4000  # S3-7
# Measured on Walnut_1 slices 500-559 (flesh = pixels > -900 HU):
# Low -228.4 +- 3.9, High -130.0 +- 2.7 (2026-10-21). Aligns the training
# signal distribution with the walnut flesh level; loss-invariant.
FLESH_OFFSET_HU = (-228.0, -130.0)


def _load_split(indices: list[int]) -> dict[int, dict[str, np.ndarray]]:
    """Load (Low, High) bin pairs, cached as float16 to bound RAM
    (~2.6 GB float32 for 160 samples of (2,1024,1024); float16 halves it)."""
    offset = np.asarray(FLESH_OFFSET_HU, dtype=np.float32)[:, None, None]
    cache: dict[int, dict[str, np.ndarray]] = {}
    for idx in indices:
        path = DATA / f"sample_{idx:04d}.npz"
        with np.load(path) as npz:
            cache[idx] = {
                "bins_noisy": np.asarray(npz["bins_noisy"], dtype=np.float16) + offset,
                "bins_clean": np.asarray(npz["bins_clean"], dtype=np.float16) + offset,
            }
    return cache


def _crop_pair(
    cache: dict[int, dict[str, np.ndarray]], idx: int, y: int, x: int
) -> tuple[torch.Tensor, torch.Tensor]:
    s = cache[idx]
    sl = (slice(y, y + CROP), slice(x, x + CROP))
    noisy = torch.from_numpy(s["bins_noisy"][:, sl[0], sl[1]].astype(np.float32))
    clean = torch.from_numpy(s["bins_clean"][:, sl[0], sl[1]].astype(np.float32))
    return noisy, clean


def _draw_batch(
    cache: dict[int, dict[str, np.ndarray]],
    indices: list[int],
    generator: torch.Generator,
) -> tuple[torch.Tensor, torch.Tensor]:
    noisy = torch.empty(len(indices), 2, CROP, CROP)
    clean = torch.empty(len(indices), 2, CROP, CROP)
    limit = 1024 - CROP
    for i, idx in enumerate(indices):
        y = int(torch.randint(0, limit + 1, (1,), generator=generator))
        x = int(torch.randint(0, limit + 1, (1,), generator=generator))
        noisy[i], clean[i] = _crop_pair(cache, idx, y, x)
    return noisy, clean


def _loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    l2 = torch.mean((pred - target) ** 2)
    dp = pred[:, :, :, 1:] - pred[:, :, :, :-1]
    dt = target[:, :, :, 1:] - target[:, :, :, :-1]
    dy_p = pred[:, :, 1:, :] - pred[:, :, :-1, :]
    dy_t = target[:, :, 1:, :] - target[:, :, :-1, :]
    grad_l1 = torch.mean(torch.abs(dp - dt)) + torch.mean(torch.abs(dy_p - dy_t))
    return l2 + GRAD_L1_WEIGHT * grad_l1


def _val_metrics(
    model: VMIDenoiser,
    cache: dict[int, dict[str, np.ndarray]],
    idxs: list[int],
) -> dict:
    model.eval()
    total = 0.0
    with torch.no_grad():
        for start in range(0, len(idxs), 8):
            batch = idxs[start : start + 8]
            noisy = torch.empty(len(batch), 2, CROP, CROP)
            clean = torch.empty(len(batch), 2, CROP, CROP)
            for i, idx in enumerate(batch):
                # deterministic centre crop for validation
                off = (1024 - CROP) // 2
                noisy[i], clean[i] = _crop_pair(cache, idx, off, off)
            pred = model(noisy)
            total += float(torch.mean((pred - clean) ** 2)) * len(batch)
    model.train()
    return {"val_l2": total / len(idxs)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps-per-run", type=int, default=250)
    ap.add_argument("--total-steps", type=int, default=TOTAL_STEPS_DEFAULT)
    args = ap.parse_args()
    ckpt = RESULTS / "denoiser_d1w_checkpoint.pt"
    weights = RESULTS / "denoiser_d1w_weights.pt"
    log = RESULTS / "denoiser_d1w_log.jsonl"

    train_cache = _load_split(list(range(N_TRAIN)))
    val_cache = _load_split(list(range(N_TRAIN, N_SAMPLES)))
    val_idxs = list(range(N_TRAIN, N_SAMPLES))
    train_idxs = list(range(N_TRAIN))

    model = VMIDenoiser(n_channels=2)
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

    print(f"train samples={N_TRAIN} val={len(val_idxs)} params={n_parameters(model)}")
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
        loss = _loss(model(noisy), clean)
        loss.backward()
        opt.step()
        step += 1
        if step % 25 == 0:
            print(f"step {step} loss {float(loss.detach()):.1f} ({time.time() - t0:.0f}s)")
        if step % 250 == 0 or step == target:
            metrics = _val_metrics(model, val_cache, val_idxs)
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
