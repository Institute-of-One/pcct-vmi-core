"""H4 walnut evaluation: noise injection + 4-arm comparison (S12-3/12-6).

Arms per slice (60 slices, 500-559, Walnut_1 FDK_Dose_1_hann_TV_100_20):
Reference (the dataset's own reconstructions), Raw (S12-4 noise injection),
D1w (2-channel walnut-trained denoiser, results/denoiser_d1w_weights.pt),
3D TV (chambolle_tv_3d, S5-3 weight 0.5*sigma^2 with laplacian_noise_sd on
the injected stack).

Noise: pcctvmi.noise_inject.synthesize with the frozen S12-4 model for the
dose, scaled from 1/cm to HU with the canonical calibration
1000/MU_WATER_EFF(100% dose). One noise realisation per slice
(seed = 20261020 + slice index) is generated and SHARED by Raw/D1w/TV so
all arms are compared on identical noise (§12.3).

Metrics (vs Reference, §12.6): per-keV VMI RMSE/SSIM on the flesh mask;
MD pulp/shell ROI bias/SD (ROIs from the reference MD maps over the flesh
central region); radial NPS of the (arm - reference) difference images
(secondary). Chunked, one chunk per call:

    python tools/walnut_eval.py --dose 0.25 --start 500 --stop 512
    ...
    python tools/walnut_eval.py --dose 0.25 --merge

Outputs ``results/walnut_eval_d{ dose }.json`` (merged) with per-slice
records; chunk intermediates are gitignored part files.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pydicom  # noqa: E402
import torch  # noqa: E402
from skimage.metrics import structural_similarity  # noqa: E402

from pcctvmi.denoiser import VMIDenoiser  # noqa: E402
from pcctvmi.noise_inject import NoiseModel, synthesize  # noqa: E402
from pcctvmi.tv import chambolle_tv_3d, laplacian_noise_sd  # noqa: E402
from pcctvmi.walnut import (  # noqa: E402
    flesh_mask,
    md_maps,
    md_rois,
    vmi_stack,
)

RESULTS = ROOT / "results"
ZIP_PATH = ROOT / "data" / "walnut" / "Reconstructions.zip"
SERIES = "Reconstructions/Walnut_1/FDK_Dose_1_hann_TV_100_20"
SLICES = range(500, 560)  # §12.3: 60 contiguous slices
DOSES = (0.25, 0.125)
SEED_BASE = 20261020  # §12.3; derived per slice, shared across arms
# Canonical 1/cm -> HU calibration (100%-dose water-only constants, the
# convention recorded in tools/make_training_data_walnut.py).
MU_WATER_EFF = (0.5575717876742355, 0.2553258904005463)
HU_SCALE = tuple(1000.0 / m for m in MU_WATER_EFF)
TV_WEIGHT_FACTOR = 0.5  # S5-3
CENTRE_RADIUS_PX = 250  # "slice central region" for the MD ROI search (§12.6)
NPS_HALF = 128  # central half-size for the difference-image NPS crop
NPS_BINS = 12  # radial bins for the NPS profile


def _load_dcm(zf: zipfile.ZipFile, name: str) -> np.ndarray:
    with zf.open(name) as fh:
        ds = pydicom.dcmread(fh)
    return ds.pixel_array.astype(np.float32) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)


def _radial_nps(diff: np.ndarray) -> list[float]:
    """Hann-windowed periodogram of a 2D difference crop, radial means."""
    ny, nx = diff.shape
    win = np.hanning(ny)[:, None] * np.hanning(nx)[None, :]
    u = diff * win
    f = np.fft.fftshift(np.fft.fft2(u))
    nps = np.abs(f) ** 2 / (np.sum(win**2) * ny * nx)  # HU^2*mm^2 normalised
    fy = np.fft.fftshift(np.fft.fftfreq(ny))[:, None]
    fx = np.fft.fftshift(np.fft.fftfreq(nx))[None, :]
    r = np.sqrt(fy**2 + fx**2)
    edges = np.linspace(0.0, 0.5, NPS_BINS + 1)
    return [
        float(nps[(r >= lo) & (r < hi)].mean())
        for lo, hi in zip(edges[:-1], edges[1:], strict=True)
    ]


def _central_mask(shape: tuple[int, int]) -> np.ndarray:
    ny, nx = shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    cy, cx = ny // 2, nx // 2
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= CENTRE_RADIUS_PX**2


def _vmi_metrics(ref_stack: np.ndarray, arm_stack: np.ndarray, search: np.ndarray) -> dict:
    rms, ss = [], []
    for i in range(ref_stack.shape[0]):
        r = ref_stack[i]
        a = arm_stack[i]
        dr = float(r.max() - r.min())
        rms.append(float(np.sqrt(np.mean((a[search] - r[search]) ** 2))))
        ss.append(float(structural_similarity(r, a, data_range=dr)))
    return {"vmi_rmse_per_kev": rms, "vmi_ssim_per_kev": ss}


def _md_metrics(
    ref_maps: tuple[np.ndarray, np.ndarray],
    arm_maps: tuple[np.ndarray, np.ndarray],
    pulp_roi: np.ndarray,
    shell_roi: np.ndarray,
) -> dict:
    out = {}
    for name, roi in (("pulp", pulp_roi), ("shell", shell_roi)):
        for mat, (r_m, a_m) in zip(
            ("pulp", "shell"), zip(ref_maps, arm_maps, strict=True), strict=True
        ):
            d = (a_m - r_m)[roi]
            out[f"md_{name}_roi_{mat}_bias"] = float(d.mean())
            out[f"md_{name}_roi_{mat}_sd"] = float(d.std())
    return out


def process_slice(
    zf: zipfile.ZipFile,
    model: NoiseModel,
    net: VMIDenoiser,
    dose: float,
    slice_idx: int,
) -> dict:
    t0 = time.time()
    low = _load_dcm(zf, f"{SERIES}/Low/{slice_idx:05d}.dcm")
    high = _load_dcm(zf, f"{SERIES}/High/{slice_idx:05d}.dcm")
    ref = np.stack([low, high])

    rng = np.random.default_rng(SEED_BASE + slice_idx)
    noise = synthesize(model, low.shape, rng)
    scale = np.asarray(HU_SCALE, dtype=np.float64)[:, None, None]
    raw = ref + noise * scale

    net.eval()
    with torch.no_grad():
        d1w = net(torch.from_numpy(raw.astype(np.float32))[None])[0].numpy()
    sigma = laplacian_noise_sd(raw)
    tv = chambolle_tv_3d(raw, TV_WEIGHT_FACTOR * sigma**2)

    search = flesh_mask(low) & _central_mask(low.shape)
    ref_vmi = vmi_stack(low, high)
    ref_md = md_maps(low, high)
    pulp_roi, shell_roi = md_rois(ref_md[0], ref_md[1], search)

    arms = {"raw": raw, "d1w": d1w, "tv": tv}
    rec: dict = {
        "slice": slice_idx,
        "dose": dose,
        "sigma_hat_hu": sigma,
        "search_px": int(search.sum()),
        "pulp_roi_px": int(pulp_roi.sum()),
        "shell_roi_px": int(shell_roi.sum()),
    }
    for name, stack in arms.items():
        vmi = vmi_stack(stack[0], stack[1])
        rec[name] = _vmi_metrics(ref_vmi, vmi, search)
        rec[name].update(_md_metrics(ref_md, md_maps(stack[0], stack[1]), pulp_roi, shell_roi))
        c = NPS_HALF
        cy, cx = low.shape[0] // 2, low.shape[1] // 2
        diffs = stack - ref
        rec[name]["nps_low_radial"] = _radial_nps(diffs[0][cy - c : cy + c, cx - c : cx + c])
        rec[name]["nps_high_radial"] = _radial_nps(diffs[1][cy - c : cy + c, cx - c : cx + c])
    rec["elapsed_s"] = round(time.time() - t0, 1)
    return rec


def run_chunk(dose: float, start: int, stop: int) -> None:
    model = NoiseModel.load(RESULTS / f"walnut_noise_model_d{dose:g}.npz")
    net = VMIDenoiser(n_channels=2)
    net.load_state_dict(torch.load(RESULTS / "denoiser_d1w_weights.pt", weights_only=True))
    out = RESULTS / f"walnut_eval_d{dose:g}_part{start:04d}_{stop:04d}.json"
    records = []
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for slice_idx in range(start, stop):
            rec = process_slice(zf, model, net, dose, slice_idx)
            records.append(rec)
            print(f"[dose={dose:g} slice={slice_idx}] {rec['elapsed_s']}s")
    out.write_text(json.dumps(records, indent=1), encoding="utf-8")
    print(f"wrote {out}")


def merge(dose: float) -> None:
    parts = sorted(RESULTS.glob(f"walnut_eval_d{dose:g}_part*.json"))
    if not parts:
        raise SystemExit("no part files found")
    records: list[dict] = []
    for p in parts:
        records.extend(json.loads(p.read_text(encoding="utf-8")))
    records.sort(key=lambda r: r["slice"])
    summary = {
        "dose": dose,
        "n_slices": len(records),
        "seed_base": SEED_BASE,
        "hu_scale_per_bin": list(HU_SCALE),
        "slices": records,
    }
    out = RESULTS / f"walnut_eval_d{dose:g}.json"
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"merged {len(records)} slices -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dose", type=float, required=True, choices=DOSES)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    if args.merge:
        merge(args.dose)
        return
    if args.start is None or args.stop is None:
        raise SystemExit("chunk mode requires --start/--stop (or --merge)")
    lo, hi = min(SLICES), max(SLICES) + 1
    run_chunk(args.dose, max(args.start, lo), min(args.stop, hi))


if __name__ == "__main__":
    main()
