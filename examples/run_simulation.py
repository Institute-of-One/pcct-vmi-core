"""End-to-end demonstration of the Sprint-1 spectral pipeline.

Builds the frozen-configuration phantom (25 cm water cylinder with 8/5/3 mm
iodine inserts at 5 mgI/mL), simulates two-bin PCD projections at 120 kVp,
reconstructs, decomposes, synthesises the VMI stack, and writes a montage
plus a machine-readable summary under ``outputs/``.

Run:  python examples/run_simulation.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pcctvmi.forward import simulate
from pcctvmi.phantom import Insert, make_water_cylinder_phantom
from pcctvmi.recon import reconstruct_bins
from pcctvmi.spectrum import Spectrum
from pcctvmi.vmi import VMI_GRID_KEV, decompose, vmi_stack

OUT = Path(__file__).resolve().parent.parent / "outputs"
SEED = 20261009  # frozen simulation seed
N0 = 2.0e5


def _roi_mean(img: np.ndarray, cy: int, cx: int, radius: int) -> float:
    n = img.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2
    return float(np.mean(img[mask]))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    n = 512
    px = 0.05  # cm / pixel
    inserts = (
        Insert(x_cm=-6.0, y_cm=0.0, diameter_cm=0.8, iodine_g_cm3=0.005),
        Insert(x_cm=0.0, y_cm=0.0, diameter_cm=0.5, iodine_g_cm3=0.005),
        Insert(x_cm=6.0, y_cm=0.0, diameter_cm=0.3, iodine_g_cm3=0.005),
    )
    ph = make_water_cylinder_phantom(n=n, diameter_cm=25.0, pixel_size_cm=px, inserts=inserts)
    spec = Spectrum.from_csv()
    theta = np.linspace(0.0, 360.0, 720, endpoint=False)
    res = simulate(spec, ph, theta_deg=theta, thresholds_kev=(30.0,), n0=N0, seed=SEED)
    mus = reconstruct_bins(res)
    a, b = decompose(mus, res.mu_eff)
    stack = vmi_stack(a, b)

    ci = n // 2
    # 0.05 cm/px: 6 cm => 120 px
    rois = {
        "insert_8mm": _roi_mean(b, ci, ci - 120, 6),
        "insert_5mm": _roi_mean(b, ci, ci, 4),
        "insert_3mm": _roi_mean(b, ci, ci + 120, 2),
        "water_bg": _roi_mean(b, ci, ci - 240, 8),
    }
    summary = {
        "seed": SEED,
        "n0": N0,
        "cond_decomposition_matrix": float(
            np.linalg.cond(
                np.array(
                    [
                        [res.mu_eff[0]["water"], res.mu_eff[0]["iodine"]],
                        [res.mu_eff[1]["water"], res.mu_eff[1]["iodine"]],
                    ]
                )
            )
        ),
        "iodine_density_g_cm3_roi": rois,
        "nominal_iodine_g_cm3": 0.005,
        "vmi_grid_kev": list(VMI_GRID_KEV),
        "vmi_hu_insert_8mm": [
            float(_roi_mean(stack[k], ci, ci - 120, 6)) for k in range(len(VMI_GRID_KEV))
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    np.savez_compressed(
        OUT / "vmi_stack.npz",
        stack=stack.astype(np.float32),
        water_density=a.astype(np.float32),
        iodine_density=b.astype(np.float32),
    )

    fig, axes = plt.subplots(2, 3, figsize=(13, 8.5))
    axes[0, 0].imshow(ph.water_density + ph.iodine_density * 20, cmap="gray")
    axes[0, 0].set_title("phantom (water + 20x iodine)")
    axes[0, 1].imshow(mus[0], cmap="gray")
    axes[0, 1].set_title("recon, Low bin (<30 keV), 1/cm")
    axes[0, 2].imshow(mus[1], cmap="gray")
    axes[0, 2].set_title("recon, High bin (>=30 keV), 1/cm")
    for ax, kev_idx, kev in ((axes[1, 0], 0, 40), (axes[1, 1], 3, 70), (axes[1, 2], 15, 190)):
        im = ax.imshow(stack[kev_idx], cmap="gray", vmin=-250, vmax=250)
        ax.set_title(f"VMI {kev} keV (HU)")
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(OUT / "pipeline_montage.png", dpi=150)
    print(json.dumps(summary["iodine_density_g_cm3_roi"], indent=2))
    print(f"cond(M) = {summary['cond_decomposition_matrix']:.1f}")
    print(f"wrote {OUT / 'pipeline_montage.png'} and summary.json / vmi_stack.npz")


if __name__ == "__main__":
    main()
