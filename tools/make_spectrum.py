"""Generate pcctvmi/data/spectrum_120kvp.csv with SpekPy.

120 kVp tungsten-anode spectrum, 12 degree anode angle, 8 mm Al total
(equivalent) filtration — a documented assumption for a CT-like beam.

The CSV is committed; regenerate with::

    python tools/make_spectrum.py

Do not hand-edit the CSV.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import spekpy

KVP = 120
ANODE_ANGLE_DEG = 12.0
FILTRATION_AL_MM = 8.0
OUT = Path(__file__).resolve().parent.parent / "pcctvmi" / "data" / "spectrum_120kvp.csv"


def main() -> None:
    spek = spekpy.Spek(kvp=KVP, th=ANODE_ANGLE_DEG)
    spek.filter("Al", [FILTRATION_AL_MM])
    energies_kev, photons = spek.get_spectrum()
    energies_kev = np.asarray(energies_kev, dtype=np.float64)
    photons = np.asarray(photons, dtype=np.float64)
    if np.any(photons < 0):
        raise ValueError("spekpy returned negative fluence")
    # The mass-attenuation table covers 10-150 keV; truncate the spectrum to
    # the shared grid (sub-10 keV fluence after 8 mm Al is negligible).
    keep = energies_kev >= 10.0
    energies_kev, photons = energies_kev[keep], photons[keep]
    if energies_kev.size == 0:
        raise ValueError("spectrum empty after truncation")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        fh.write("energy_keV,photons\n")
        for e, f in zip(energies_kev, photons, strict=True):
            fh.write(f"{e:.1f},{f:.8e}\n")
    print(
        f"wrote {OUT} ({energies_kev.size} bins, "
        f"{energies_kev.min():.1f}-{energies_kev.max():.1f} keV, "
        f"peak at {energies_kev[np.argmax(photons)]:.1f} keV)"
    )


if __name__ == "__main__":
    main()
