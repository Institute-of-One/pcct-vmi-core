# IORN-016 manuscript status — 2026-10-29

An English research-article draft now exists at `paper/manuscript.md`.
Generated Word/PDF files are in `submission/jxst/output/`.
The reproducible build is `paper/build_all.py`; usage and current journal sources
are documented in `paper/README.md`. No commit, push, submission, or release was made.

## Content

- Approximately 4,670 body words and a structured abstract of exactly 200 words.
- Five regenerated figures, three JSON-derived tables, ten DOI-resolved references.
- Separate title page, including unresolved author declarations/contact details.
- H1 is conditional: frozen-template peaks move 60 → 40 keV throughout, but
  amplitude-scaled D1 peaks do so in only five of six conditions (8 mm / 25% → 190 keV).
- H2 is not supported: D1 reduces variability and deviation RMS while retaining bias.
- H3 is not supported as a consistent recovery strategy; partial improvements in
  quarter-count bias are reported alongside full-count positive bias and larger residuals.
- H4 is described as a reconstruction stress test. Retraining, input offsets from
  evaluation slices, and regressed VMI coefficients preclude fully independent validation.

## Verification performed in this session

- Existing pytest suite: **96 passed**, 54.49 seconds.
- Submission structural tests with known-defect injection: **5 passed**.
- All **10 DOIs resolved** via doi.org; registered titles and years retained in
  `paper/references.json`. An initially incorrect TV DOI was rejected and replaced
  using the publisher's record; it was never used in the manuscript bibliography.
- Both walnut summary datasets reaggregated: **328 numeric values, zero difference**.
- Walnut slice 530 at nominal 25% replayed with original weights/noise model:
  all saved numeric metrics agreed at rtol=1e-5 / atol=1e-5.
- All five standalone figures and rendered manuscript/title-page pages inspected;
  exact reviewed output hashes are recorded in `paper/visual_review.json`.

## Important corrections to inherited descriptions

The executable D1 is a joint 16-channel network, not independent per-energy networks.
Primary processed d′ is a nonnegative magnitude; TV/sensitivity tools retain signed
linear scaling. Plotted comparisons use magnitudes consistently, with sign reversals
discussed using the separately retained signal-transfer ratios.

The walnut RMSE uses a central masked region, whereas SSIM is whole-image.
Walnut material values are calibration-table-scale differences rather than verified
chemical concentration. Stored radial profiles use custom discrete normalization;
the manuscript does not label them as calibrated physical NPS measurements.

## Remaining gates — not submission-ready

See `paper/readiness.json`. Funding/conflicts/authorship/ethics/contact details need
author confirmation. Public code availability, version DOI, affiliation comparison,
and a clean snapshot/new environment figure build remain unverified. This checkout
has no configured Git remote. The entire training and evaluation pipeline has not
been rerun in this session; the result replay above is deliberately narrower.

AI-Check's 2026-10-26 fixed-prompt doctor record shows both services failed.
No retries, API-billing fallback, or project-file transmission were performed.
Independent Codex–Claude review is **BLOCKED**, not PASS. pytest, images, and Word
rendering are outside the standard AI-Check v1 unittest path.

Scientific limits to address during author review include stationary background NPS
after nonlinear processing, scalar rather than full-shape signal correction,
input-extent sensitivity from GroupNorm, and walnut adaptation using test-slice means.
The current manuscript discloses these limits; disclosure is not a claim that they
have been experimentally eliminated.

## Update — 2026-11-02

Everything above is the record of 2026-10-29 and some of it has been overtaken.
`paper/readiness.json` is the current state; the differences that matter:

- The body is 5,193 words and carries 36 references, not 4,670 and ten. The journal's
  recent research articles cite 26 at the thinnest and 40 at the median
  (`paper/venue_reference_benchmark.json`, measured from Europe PMC), and JXST has no
  Note category to be reclassified into, so the old list was a rejection risk.
- The affiliation now resolves against the three Crossref records under the author's
  ORCID, and the author supplied his telephone and approved the contact block on
  2026-11-02, so contact details are no longer unresolved.
- Ethics, conflicting interest, funding, contributions and acknowledgement are final
  wording on the author's instruction of 2026-11-02: no conflicting interests and no
  funding. The generative-AI declaration still carries two to-do sentences.
- Every page of the manuscript and title page has been opened at 150 dpi and the review
  is pinned to the page rasters, which a rebuild leaves byte-identical when the content
  is unchanged. Four reference-list defects visible only on the page were fixed.
- Structural injection tests are 14, not 5; pytest is still 96.
## Published — 2026-11-02

At the author's instruction the repository was made public, tagged and archived.

- `https://github.com/Institute-of-One/pcct-vmi-core`, public, default branch `main`.
- Release **v0.2.0**, archived on Zenodo: version DOI **10.5281/zenodo.23875047**,
  concept DOI **10.5281/zenodo.23875046**. The manuscript cites the version DOI; the
  README badge carries the concept DOI. Both are held once in `paper/release.json`.
- The version was raised from 0.1.0 because that number already names the 2026-10-09
  physics core in `CHANGELOG.md`, and Zenodo cannot correct the version of a published
  record.
- The corresponding author's telephone and street address are **not** in the repository.
  They live in `paper/author_contact.local.json`, which `.gitignore` excludes, and the
  author gate fails if either reaches a tracked file or any commit. The history was
  rewritten before the first push, because both had been committed.
- `.github/workflows/tests.yml` runs on every push and weekly. Its first run failed:
  the documented install never installed the package, so no test could import
  `pcctvmi`. Both the workflow and the README now do an editable install.
- `docs/DATA.md` was English-only in the manuscript's reach; it is now English first,
  Japanese after, and its third section - an internal plan naming a third party - is no
  longer in the public file. `docs/MANUSCRIPT_HANDOFF.md` is untracked for the same
  reason, though it was in the first push and so is in the public history.

- Still open and still the author's: the generative-AI declaration's two to-do
  sentences, independent review, the full pipeline rerun, and his own inspection.
