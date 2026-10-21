"""Render a preview montage of the H4 walnut evaluation (not a paper figure).

Slice 530, dose 25%: the Low bin (reference / raw / d1w / tv) and the
40 keV VMI of each arm. Output ``results/walnut_preview_d{dose:g}.png``
(gitignored; for eyeballing only — paper figures stay frozen, Sprint 4).

    python tools/walnut_preview.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pcctvmi.denoiser import VMIDenoiser  # noqa: E402
from pcctvmi.noise_inject import NoiseModel, synthesize  # noqa: E402
from pcctvmi.tv import chambolle_tv_3d, laplacian_noise_sd  # noqa: E402
from pcctvmi.walnut import vmi_stack  # noqa: E402

# Shared with tools/walnut_eval.py (kept in sync by hand; the eval script is
# authoritative). tools/ is not a package, so no cross-import.
ZIP_PATH = ROOT / "data" / "walnut" / "Reconstructions.zip"
SERIES = "Reconstructions/Walnut_1/FDK_Dose_1_hann_TV_100_20"
SEED_BASE = 20261020
HU_SCALE = (1000.0 / 0.5575717876742355, 1000.0 / 0.2553258904005463)


def _load_dcm(zf, name: str):  # noqa: ANN001, ANN202
    import pydicom

    with zf.open(name) as fh:
        ds = pydicom.dcmread(fh)
    return ds.pixel_array.astype(np.float32) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)


SLICE = 530
DOSE = 0.25
KEV = 40


def main() -> None:
    model = NoiseModel.load(ROOT / "results" / f"walnut_noise_model_d{DOSE:g}.npz")
    net = VMIDenoiser(n_channels=2)
    net.load_state_dict(torch.load(ROOT / "results" / "denoiser_d1w_weights.pt", weights_only=True))
    with zipfile.ZipFile(ZIP_PATH) as zf:
        low = _load_dcm(zf, f"{SERIES}/Low/{SLICE:05d}.dcm")
        high = _load_dcm(zf, f"{SERIES}/High/{SLICE:05d}.dcm")
    ref = np.stack([low, high])
    rng = np.random.default_rng(SEED_BASE + SLICE)
    raw = ref + synthesize(model, low.shape, rng) * np.asarray(HU_SCALE)[:, None, None]
    net.eval()
    with torch.no_grad():
        d1w = net(torch.from_numpy(raw.astype(np.float32))[None])[0].numpy()
    tv = chambolle_tv_3d(raw, 0.5 * laplacian_noise_sd(raw) ** 2)

    arms = [("Reference", ref), ("Raw", raw), ("D1w", d1w), ("3D TV", tv)]
    fig, axes = plt.subplots(2, 4, figsize=(16, 8.6))
    for j, (name, stack) in enumerate(arms):
        ax = axes[0, j]
        ax.imshow(stack[0], cmap="gray", vmin=-1000, vmax=0)
        ax.set_title(f"{name} — Low bin (HU)")
        ax.axis("off")
        v = vmi_stack(stack[0], stack[1])
        kev_i = (40 - 10) // 10
        ax = axes[1, j]
        ax.imshow(v[kev_i], cmap="gray", vmin=-500, vmax=500)
        ax.set_title(f"{name} — VMI {KEV} keV (HU)")
        ax.axis("off")
    fig.suptitle(f"Walnut_1 slice {SLICE}, dose {DOSE:g} (n0=3.0e4) — H4 preview")
    fig.tight_layout()
    out = ROOT / "results" / f"walnut_preview_d{DOSE:g}.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
