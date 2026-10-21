"""Estimate the image-domain noise model for the H4 walnut arm (S12-4).

Simulates the walnut-matched configuration (80 kVp, 0.5 mm Al,
thresholds 15/30 keV, 35 mm water disk, 0.05 mm pixels, 1024^2 grid,
180 views, hann FBP) at low-count doses, and estimates the (Low, High)
cross-channel noise power spectrum on a 256-pixel central ROI. The result
feeds pcctvmi.noise_inject.synthesize for image-domain noise injection
into the real walnut bin images (PROTOCOL_FREEZE.md §12.3/§12.4).

Bin convention (simulate with thresholds (15, 30) yields THREE bins):
index 0 = [E_min, 15) keV (hardware-rejected in the real scanner; not a
walnut bin), index 1 = Low = [15, 30) keV, index 2 = High = [30, E_max).
Only bins 1 and 2 are reconstructed into the walnut (Low, High) images.

n0 selection follows the S1-6 criterion: the smallest fluence such that
the Low-bin mean photon count at the centre path (3.5 cm) is >= 5 at the
25% dose level. In this geometry the raw criterion gives n0 ~ 410, but
the frozen S1 degeneracy floor (mean air counts >= 100 in every bin,
including the rejected sub-15 keV bin; forward.py simulate) is binding
at the lowest dose (12.5%): n0 >= 100 / (0.125 * f_air_min). The chosen
value is the larger of the two, rounded up to one significant figure, and
is recorded in the run JSON and in PROTOCOL_FREEZE.md §12.4.

Chunked execution (one chunk per call, ~1.5 minutes for 8 reps):

    python tools/walnut_noise_model.py --dose 0.25 --start 0 --stop 8
    ...
    python tools/walnut_noise_model.py --dose 0.25 --merge
    python tools/walnut_noise_model.py --dose 0.125 --start 0 --stop 8
    ...
    python tools/walnut_noise_model.py --dose 0.125 --merge

Outputs ``results/walnut_noise_model_d{ dose }.npz`` (a NoiseModel archive)
and ``results/walnut_noise_model_d{ dose }.json`` (photon statistics,
realised SDs, and the frozen configuration).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pcctvmi.forward import REFERENCE_N0, areal_density_projections, simulate  # noqa: E402
from pcctvmi.noise_inject import NoiseModel  # noqa: E402
from pcctvmi.phantom import make_water_cylinder_phantom  # noqa: E402
from pcctvmi.recon import reconstruct_bins  # noqa: E402
from pcctvmi.spectrum import Spectrum  # noqa: E402

RESULTS = ROOT / "results"
SPECTRUM_CSV = "spectrum_80kvp.csv"
THRESHOLDS_KEV = (15.0, 30.0)
N = 1024
PX_CM = 0.005  # 0.05 mm, walnut-matched
WATER_DIAMETER_CM = 3.5
THETA = np.linspace(0.0, 360.0, 180, endpoint=False)
DOSES = (0.25, 0.125)
REPS = 32
ROI = 256
SEED_BASE = 20261021  # S12-4; no overlap with training (S3-5) or eval seeds
CENTER_PATH_CM = WATER_DIAMETER_CM
MIN_LOW_PHOTONS = 5.0  # S1-6 criterion at 25% dose
MIN_AIR_COUNTS = 100.0  # frozen S1 degeneracy floor (forward.py simulate)
LOW_BIN = 1  # [15, 30) keV — the walnut Low bin
HIGH_BIN = 2  # [30, E_max) keV — the walnut High bin
N_BINS = 3  # thresholds (15, 30) -> [E_min,15), [15,30), [30,E_max)


def _paths(dose: float) -> tuple[Path, Path, Path]:
    tag = f"d{dose:g}"
    return (
        RESULTS / f"walnut_noise_model_{tag}.npz",
        RESULTS / f"walnut_noise_model_{tag}.json",
        RESULTS / f"walnut_noise_model_{tag}_meta.json",
    )


def _config() -> dict:
    return {
        "spectrum_csv": SPECTRUM_CSV,
        "thresholds_kev": list(THRESHOLDS_KEV),
        "bin_convention": "3 bins: 0=[E_min,15) rejected, 1=Low [15,30), 2=High [30,E_max)",
        "low_bin_index": LOW_BIN,
        "high_bin_index": HIGH_BIN,
        "n": N,
        "pixel_size_cm": PX_CM,
        "water_diameter_cm": WATER_DIAMETER_CM,
        "theta": "180 views over 360 deg",
        "roi": ROI,
        "seed_base": SEED_BASE,
        "reps": REPS,
        "min_low_photons_at_25pct": MIN_LOW_PHOTONS,
        "min_air_counts_per_bin": MIN_AIR_COUNTS,
    }


def _phantom_and_spec():
    spec = Spectrum.from_csv(SPECTRUM_CSV)
    ph = make_water_cylinder_phantom(n=N, diameter_cm=WATER_DIAMETER_CM, pixel_size_cm=PX_CM)
    projections = areal_density_projections(ph, THETA)
    return spec, ph, projections


def choose_n0(spec, ph, projections) -> dict:
    """Apply the S1-6 photon criterion plus the frozen S1 air-count floor.

    Returns a dict with the chosen n0 (one significant figure, rounded up),
    the two candidate bounds, and which one binds.
    """
    res = simulate(
        spec,
        ph,
        theta_deg=THETA,
        thresholds_kev=THRESHOLDS_KEV,
        n0=REFERENCE_N0,
        seed=SEED_BASE,
        projections=projections,
    )
    if len(res.expected_counts) != N_BINS:
        raise SystemExit(f"expected {N_BINS} bins, got {len(res.expected_counts)}")
    centre = N // 2
    low_per_n0 = float(np.mean(res.expected_counts[LOW_BIN][centre, :]) / REFERENCE_N0)
    # S1-6 photon criterion: >= MIN_LOW_PHOTONS at the centre path, 25% dose.
    n0_photon = MIN_LOW_PHOTONS / (0.25 * low_per_n0)
    # Frozen S1 degeneracy floor: mean air counts >= MIN_AIR_COUNTS in EVERY
    # bin (including the hardware-rejected sub-15 keV bin) at the LOWEST dose.
    air_per_n0 = res.air_counts / REFERENCE_N0
    n0_air = MIN_AIR_COUNTS / (min(DOSES) * float(air_per_n0.min()))
    n0_raw = max(n0_photon, n0_air)
    # Round up to one significant figure (S1-6 "smallest order" convention).
    n0 = float(
        np.ceil(n0_raw / 10.0 ** np.floor(np.log10(n0_raw))) * 10.0 ** np.floor(np.log10(n0_raw))
    )
    return {
        "n0": n0,
        "n0_photon_criterion": n0_photon,
        "n0_air_floor": n0_air,
        "binding": "air_floor" if n0_air > n0_photon else "photon_criterion",
        "low_bin_photons_per_n0_centre": low_per_n0,
        "air_photons_per_n0_min_bin": float(air_per_n0.min()),
    }


def run_chunk(dose: float, start: int, stop: int) -> None:
    spec, ph, projections = _phantom_and_spec()
    npz_path, _, meta_path = _paths(dose)
    if meta_path.exists():
        n0 = float(json.loads(meta_path.read_text(encoding="utf-8"))["n0"])
    else:
        selection = choose_n0(spec, ph, projections)
        n0 = float(selection["n0"])
        meta_path.write_text(
            json.dumps({"n0": n0, **selection, **_config(), "dose": dose}, indent=2),
            encoding="utf-8",
        )
    res0 = simulate(
        spec,
        ph,
        theta_deg=THETA,
        thresholds_kev=THRESHOLDS_KEV,
        n0=dose * n0,
        seed=SEED_BASE + 777,
        projections=projections,
    )
    recon0 = reconstruct_bins(res0, use_expected=True)
    c = N // 2
    half = ROI // 2
    ref = np.stack(
        [recon0[ch][c - half : c + half, c - half : c + half] for ch in (LOW_BIN, HIGH_BIN)]
    )
    crops = np.zeros((stop - start, 2, ROI, ROI), dtype=np.float32)
    for i, rep in enumerate(range(start, stop)):
        t0 = time.time()
        res = simulate(
            spec,
            ph,
            theta_deg=THETA,
            thresholds_kev=THRESHOLDS_KEV,
            n0=dose * n0,
            seed=SEED_BASE + rep,
            projections=projections,
        )
        recon = reconstruct_bins(res, use_expected=False)
        for out_ch, src_ch in enumerate((LOW_BIN, HIGH_BIN)):
            crops[i, out_ch] = (
                recon[src_ch][c - half : c + half, c - half : c + half] - ref[out_ch]
            ).astype(np.float32)
        print(f"[dose={dose:g} rep={rep}] {time.time() - t0:.1f}s")
    out = RESULTS / f"walnut_noise_model_d{dose:g}_part{start:04d}_{stop:04d}.npz"
    np.savez_compressed(out, crops=crops, ref=ref.astype(np.float32), dose=dose)
    print(f"wrote {out}")


def merge(dose: float) -> None:
    npz_path, json_path, meta_path = _paths(dose)
    parts = sorted(RESULTS.glob(f"walnut_noise_model_d{dose:g}_part*.npz"))
    if not parts:
        raise SystemExit("no part files found")
    crops = np.concatenate([np.load(p)["crops"] for p in parts])
    ref = np.load(parts[0])["ref"]
    n_rep, _, ny, nx = crops.shape
    spacing_mm = PX_CM * 10.0
    resid = crops - crops.mean(axis=(-2, -1), keepdims=True)
    wl = np.fft.fft2(resid[:, 0], axes=(-2, -1))
    wh = np.fft.fft2(resid[:, 1], axes=(-2, -1))
    norm = spacing_mm * spacing_mm / (ny * nx)
    s_ll = norm * np.mean(np.abs(wl) ** 2, axis=0)
    s_hh = norm * np.mean(np.abs(wh) ** 2, axis=0)
    s_lh = norm * np.mean(wl * np.conj(wh), axis=0)
    model = NoiseModel(s_ll=s_ll, s_hh=s_hh, s_lh=s_lh, spacing_mm=spacing_mm)
    model.save(npz_path)
    sd = resid.std(axis=(-2, -1))
    # Parseval: spatial variance = sum over the 2D frequency grid of
    # NPS * dfy * dfx with df = 1 / (spacing * n) per axis.
    dfy = 1.0 / (spacing_mm * ny)
    dfx = 1.0 / (spacing_mm * nx)
    var_from_nps = np.array([s_ll.sum() * dfy * dfx, s_hh.sum() * dfy * dfx])
    # Units: crops are linear-attenuation residuals (1/cm). The walnut DICOM
    # bin images are HU with the per-bin water calibration (mu_water_eff -> 0
    # HU), so 1/cm of noise converts to HU via 1000 / mu_water_eff(bin). The
    # reference ROI sits inside the water disk, so its mean is mu_water_eff.
    mu_eff = ref.mean(axis=(1, 2))
    hu_scale = 1000.0 / mu_eff
    stats = {
        **_config(),
        "dose": dose,
        "n0": json.loads(meta_path.read_text(encoding="utf-8"))["n0"],
        "n_reps": int(n_rep),
        "units": "model noise in 1/cm; hu_scale converts to HU (1000/mu_eff)",
        "mu_water_eff_per_bin_1_per_cm": [float(x) for x in mu_eff],
        "hu_scale_per_bin": [float(x) for x in hu_scale],
        "realised_sd_low_1_per_cm": [float(x) for x in sd[:, 0]],
        "realised_sd_high_1_per_cm": [float(x) for x in sd[:, 1]],
        "sd_low_mean_1_per_cm": float(sd[:, 0].mean()),
        "sd_high_mean_1_per_cm": float(sd[:, 1].mean()),
        "sd_low_mean_hu": float(sd[:, 0].mean() * hu_scale[0]),
        "sd_high_mean_hu": float(sd[:, 1].mean() * hu_scale[1]),
        "sd_from_nps_1_per_cm": [float(np.sqrt(var_from_nps[0])), float(np.sqrt(var_from_nps[1]))],
    }
    json_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(
        f"merged {n_rep} reps -> {npz_path}; sd_low={sd[:, 0].mean():.3f} "
        f"sd_high={sd[:, 1].mean():.3f} 1/cm "
        f"(HU: {sd[:, 0].mean() * hu_scale[0]:.0f} / {sd[:, 1].mean() * hu_scale[1]:.0f})"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dose", type=float, required=True, choices=DOSES)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    if args.merge:
        merge(args.dose)
        return
    if args.start is None or args.stop is None:
        raise SystemExit("chunk mode requires --start and --stop (or use --merge)")
    run_chunk(args.dose, args.start, args.stop)


if __name__ == "__main__":
    main()
