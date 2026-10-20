"""Compare the D1 (frozen) and D2 (spectral-loss) denoiser eval results.

Reads results/denoised_eval.json (D1) and results/denoised_eval_d2.json (D2)
and prints, per frozen condition:

(a) iodine quantitation bias of the denoised arm (mean +/- SD, mgI/mL)
(b) NPWE d'(E) at 40 keV, frozen (noiseless-signal) and processed-signal
(c) denoised signal attenuation ratio (mean and min/max over keV)
(d) 2-basis projection residual of the denoised arm (mean +/- SD, HU)

H3 support requires D2 to shrink the |quantitation bias| of the denoised arm
relative to D1 (primary metric) while preserving the denoised arm's
processed-signal d' advantage over Raw.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def _d40(cond: dict, key: str) -> float:
    for p in cond["per_kev"]:
        if p["kev"] == 40:
            return float(p[key])
    raise KeyError(key)


def _atts(cond: dict) -> list[float]:
    return [float(p["signal_attenuation_denoised"]) for p in cond["per_kev"]]


def main() -> None:
    d1 = json.loads((RESULTS / "denoised_eval.json").read_text(encoding="utf-8"))
    d2 = json.loads((RESULTS / "denoised_eval_d2.json").read_text(encoding="utf-8"))
    conds1 = {(c["size_cm"], c["dose_fraction"]): c for c in d1["conditions"]}
    conds2 = {(c["size_cm"], c["dose_fraction"]): c for c in d2["conditions"]}

    header = (
        f"{'condition':<18} {'arm':<9} {'|bias| mgI/mL':>16} {'d40 frozen':>11} "
        f"{'d40 proc':>9} {'att mean':>9} {'att min-max':>14} {'resid HU':>10}"
    )
    print(header)
    for key in sorted(conds1, key=lambda k: (k[0], -k[1])):
        c1, c2 = conds1[key], conds2[key]
        label = f"{key[0]}cm/{key[1]:g}"
        for arm, c in (("D1", c1), ("D2", c2)):
            q = c["quantitation"]["denoised_dev"]
            atts = _atts(c)
            r = c["residual_hu"]["denoised"]
            print(
                f"{label:<18} {arm:<9} "
                f"{q['mean'] * 1000:>+8.2f} +/-{q['sd'] * 1000:<5.2f} "
                f"{_d40(c, 'd_npwe_denoised'):>11.1f} "
                f"{_d40(c, 'd_npwe_denoised_processed'):>9.1f} "
                f"{sum(atts) / len(atts):>9.3f} "
                f"{min(atts):>6.3f}-{max(atts):<6.3f} "
                f"{r['mean']:>10.2f}"
            )
        # Raw reference row for context (identical arms across D1/D2 runs)
        qr = c1["quantitation"]["raw_dev"]
        atts_raw = [float(p["signal_attenuation_raw"]) for p in c1["per_kev"]]
        print(
            f"{label:<18} {'Raw':<9} "
            f"{qr['mean'] * 1000:>+8.2f} +/-{qr['sd'] * 1000:<5.2f} "
            f"{_d40(c1, 'd_npwe_raw'):>11.1f} "
            f"{_d40(c1, 'd_npwe_raw_processed'):>9.1f} "
            f"{sum(atts_raw) / len(atts_raw):>9.3f} "
            f"{min(atts_raw):>6.3f}-{max(atts_raw):<6.3f} "
            f"{'':>10}"
        )
        print()


if __name__ == "__main__":
    main()
