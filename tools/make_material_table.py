"""Generate pcctvmi/data/mass_attenuation.csv from NIST XCOM via xraylib.

The CSV is committed; regenerate with::

    python tools/make_material_table.py

Do not hand-edit the CSV.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import xraylib

ENERGIES_KEV = np.arange(10, 201, 1)  # 10-200 keV: covers the frozen VMI grid up to 190 keV
IODINE_Z = 53  # xraylib element index for iodine
OUT = Path(__file__).resolve().parent.parent / "pcctvmi" / "data" / "mass_attenuation.csv"


def main() -> None:
    water = [xraylib.CS_Total_CP("H2O", float(e)) for e in ENERGIES_KEV]
    iodine = [xraylib.CS_Total(IODINE_Z, float(e)) for e in ENERGIES_KEV]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["energy_keV", "water_cm2_g", "iodine_cm2_g"])
        for e, mw, mi in zip(ENERGIES_KEV, water, iodine, strict=True):
            writer.writerow([int(e), f"{mw:.8e}", f"{mi:.8e}"])
    print(f"wrote {OUT} ({len(ENERGIES_KEV)} energies, 10-200 keV)")


if __name__ == "__main__":
    main()
