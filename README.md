# pcct-vmi-core

Spectral simulation testbed for studying how AI denoising of photon-counting-detector
CT (PCD-CT) virtual monoenergetic image (VMI) stacks shifts task detectability
across energy and affects iodine quantitation.

**Scope.** This is a methodological study using synthetic digital phantoms and
public walnut reconstructions with simulated added noise. It involves no human
subjects or patient data and makes no clinical performance claims. The walnut arm
is a reconstruction stress test, not independent patient validation.

The public Zenodo walnut PCD-CT reconstructions are now used in a reconstruction-based
noise-injection stress test (one specimen; no patient validation). The TCIA comparison
is not included in the present manuscript. Source images are never redistributed.
See `docs/PROTOCOL_FREEZE.md` §12 and `docs/DATA.md` for conditions and provenance.
The English manuscript source, figure/table build, and remaining submission gates
are documented in [paper/README.md](paper/README.md).

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
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pip install -e . --no-deps
.venv/Scripts/pytest
```

The editable install is not optional: without it the tests cannot import `pcctvmi`.
`requirements-dev.txt` adds the linters and the two libraries used only to regenerate the
committed tables below (`xraylib`, `spekpy`), which are not needed to run the tests.
`torch` installs its CUDA build by default; for a CPU-only machine take it from
`https://download.pytorch.org/whl/cpu` first. `.github/workflows/tests.yml` runs exactly
these steps on every push.

## Reproducing reference data

The committed CSVs under `pcctvmi/data/` are generated, not hand-written:

```bash
.venv/Scripts/python tools/make_material_table.py
.venv/Scripts/python tools/make_spectrum.py
```

## Citation

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23875046.svg)](https://doi.org/10.5281/zenodo.23875046)

The badge is the **concept DOI**: it resolves to whichever version is newest. A paper
citing the exact code it ran should cite the **version DOI** of that release instead,
which `CITATION.cff` lists and `paper/release.json` holds.

## License

Code: MIT. Manuscript figures and text: CC BY 4.0.
