"""Generate the committed X-ray spectrum CSVs with SpekPy.

Default run reproduces pcctvmi/data/spectrum_120kvp.csv (frozen S1-3):
120 kVp tungsten-anode spectrum, 12 degree anode angle, 8 mm Al total
(equivalent) filtration — a documented assumption for a CT-like beam.

Other spectra (e.g. the 80 kVp walnut-matched arm, PROTOCOL_FREEZE.md §12.4)::

    python tools/make_spectrum.py --kvp 80 --filtration-al-mm 0.5 \
        --out pcctvmi/data/spectrum_80kvp.csv

The CSVs are committed; do not hand-edit them.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import spekpy

KVP = 120
ANODE_ANGLE_DEG = 12.0
FILTRATION_AL_MM = 8.0
OUT = Path(__file__).resolve().parent.parent / "pcctvmi" / "data" / "spectrum_120kvp.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kvp", type=float, default=KVP)
    ap.add_argument("--anode-angle-deg", type=float, default=ANODE_ANGLE_DEG)
    ap.add_argument("--filtration-al-mm", type=float, default=FILTRATION_AL_MM)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    out: Path = args.out

    spek = spekpy.Spek(kvp=args.kvp, th=args.anode_angle_deg)
    spek.filter("Al", [args.filtration_al_mm])
    energies_kev, photons = spek.get_spectrum()
    energies_kev = np.asarray(energies_kev, dtype=np.float64)
    photons = np.asarray(photons, dtype=np.float64)
    if np.any(photons < 0):
        raise ValueError("spekpy returned negative fluence")
    # The mass-attenuation table covers 10-150 keV; truncate the spectrum to
    # the shared grid. For heavily filtered beams (8 mm Al) sub-10 keV
    # fluence is negligible; for lightly filtered beams (0.5 mm Al, walnut
    # arm) sub-10 keV photons sit below the 15 keV detector threshold and
    # never enter any bin, so the truncation is exact for bin statistics.
    keep = energies_kev >= 10.0
    energies_kev, photons = energies_kev[keep], photons[keep]
    if energies_kev.size == 0:
        raise ValueError("spectrum empty after truncation")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        fh.write("energy_keV,photons\n")
        for e, f in zip(energies_kev, photons, strict=True):
            fh.write(f"{e:.1f},{f:.8e}\n")
    print(
        f"wrote {out} ({energies_kev.size} bins, "
        f"{energies_kev.min():.1f}-{energies_kev.max():.1f} keV, "
        f"peak at {energies_kev[np.argmax(photons)]:.1f} keV)"
    )


if __name__ == "__main__":
    main()
