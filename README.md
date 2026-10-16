# pcct-vmi-core

Spectral simulation testbed for studying how AI denoising of photon-counting-detector
CT (PCD-CT) virtual monoenergetic image (VMI) stacks shifts task detectability
across energy and affects iodine quantitation.

**Scope.** This is a methodological software contribution using synthetic digital
phantoms only. It involves no human subjects, no patient data, and makes no
clinical performance claims; institutional review, informed consent, and clinical
validation are therefore not applicable.

Real public data (Zenodo walnut PCD-CT dataset, CC BY 4.0; TCIA EID CT, CC BY
3.0) are **planned** as external validation inputs only (not yet used in the
current code) and are never redistributed. See `docs/PROTOCOL_FREEZE.md` §4
and `docs/DATA.md` for conditions and the planned scope.

## What it does

- Polyenergetic forward projection of a digital phantom (water background +
  iodine inserts of known concentration) with an energy-resolved X-ray spectrum.
- Two-bin photon-counting detection (ideal threshold model) with Poisson noise
  and exposure (mAs) scaling.
- Filtered back-projection per bin; water/iodine basis decomposition using
  transmission-weighted effective bin coefficients.
- Virtual monoenergetic image synthesis on an arbitrary keV grid.

## Layout

```
pcctvmi/            package (materials, spectrum, phantom, forward, recon, vmi)
tools/              reference-data generators (xraylib / spekpy -> CSV)
examples/           runnable end-to-end demonstrations
tests/              closed-form, contract, and determinism tests
docs/               protocol freeze, data provenance, assumptions
data/               downloaded public data (gitignored)
```

## Install and test

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/pytest
```

## Reproducing reference data

The committed CSVs under `pcctvmi/data/` are generated, not hand-written:

```bash
.venv/Scripts/python tools/make_material_table.py
.venv/Scripts/python tools/make_spectrum.py
```

## Citation

See `CITATION.cff`. DOI is minted on release (Zenodo).

## License

Code: MIT. Manuscript figures and text: CC BY 4.0.
