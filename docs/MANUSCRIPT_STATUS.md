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

## 2026-11-03

- The generative-AI declaration is a declaration. The author confirmed that OpenAI
  Codex was the only generative-AI tool used during the October research and
  implementation work, which is what the two sentences above were asking for. The
  paragraph now names Codex for that stage and Claude from 1 November, says why the
  two are named separately, and ends on the author's responsibility for the content.
  `author_declarations` is PASS. This corrects the lines above that say the
  declaration still carries two to-do sentences, and the Content line that calls the
  title page's declarations unresolved.
- The AI-Check sentence above is also out of date. A live `ai_check.py doctor` run on
  2026-11-02 returned pass from Codex (codex-cli 0.165.0-alpha.1.2) and from Claude
  Code (2.1.302), so "both services failed" describes 26 October, not now. What blocks
  independent review is structural: AI-Check v1 accepts one test command,
  `python -m unittest discover`, and will not report PASS without a passing test inside
  the snapshot it copies, while every test file here is pytest and the submission gates
  need the repository layout, Word and network access. Its POLICY.md section 4 covers
  this case: run the project's own execution checks and an independent review, and
  record what the basis does not cover. No project files have been sent.
- The full pipeline is being re-executed rather than replayed. `tools/run_pipeline.py`
  runs it end to end in dependency order, from the physics tables through both training
  arms to the walnut evaluation, and `tools/compare_results.py` compares what it writes
  against the frozen results leaf by leaf. The run is in a separate working tree built
  from `git archive v0.2.0`, with its own environment from
  `paper/requirements-manuscript.txt`, so nothing it produces can overwrite a frozen
  result. The frozen results stay the manuscript's source either way; the question the
  run answers is whether they can be produced again.
- First comparisons from that run: `pcctvmi/data/spectrum_120kvp.csv` regenerates
  byte-identical, `mass_attenuation.csv` regenerates with identical values but CRLF line
  endings, because the generator writes in text mode and git stores the file with LF -
  a reader who regenerates it on Windows sees a modified file that holds the same
  numbers. `results/quantitation_baseline.json` regenerates with zero difference across
  all 160 leaves at a tolerance of exactly zero.
- `paper/record_visual_review.py` re-pins the visual review and refuses to re-pin a page
  that changed on disk and was not named as opened, because the repair used to be a hand
  edit of the JSON and a hand edit can pin bytes nobody has seen.

## 2026-11-23

- The special issue was re-read on its live call page, which had last been checked on
  2026-11-02. It is unchanged: submission deadline 31 December 2026, first decision
  28 February 2027, Online First roughly 40 days after acceptance, issue intended Q2
  2027, submission through ScholarOne with the manuscript type
  "Special Issue - AI in PCCT". The call welcomes original research articles, reviews
  and methodological papers, and two of its listed topics name what this manuscript
  measures: AI-based spectral information utilisation, material decomposition and
  quantitative imaging, and evaluation metrics, robustness and uncertainty analysis.
  The abstract and the cover letter should answer the call in its own words rather
  than leave the mapping to the reader.
- Three substantive changes to the manuscript were identified, none of them cosmetic.
  1. **The Conclusions state a strategy where the results support a rule.** "Noise
     suppression, signal preservation, and material fidelity require separate
     assessment" is an exhortation. The results carry three findings a reader can act
     on, each with its own number: a reduced iodine spread did not mean an unbiased
     estimate, since D1 kept a quarter-count deviation of roughly −1.94 to
     −2.59 mgI/mL while its variability improved; a penalty on the material
     coordinates did not protect what is orthogonal to them, the secondary spectral
     residual rising about 5.6-fold at quarter count; and a frozen-template
     detectability calculation credits noise suppression without accounting for
     signal loss, since amplitude scaling moved one condition's optimum from 40 keV
     to 190 keV. Both Conclusions sections should lead with those three and keep the
     scope limits after them, not instead of them.
  2. **The loss comparison is the manuscript's most transferable result and is
     currently introduced as an aside** ("a deliberately tested spectral-loss
     alternative", end of the Introduction's contribution sentence). D1 against D2 is
     a loss-function ablation in which the physics-motivated term made an orthogonal
     component measurably worse. It belongs in the contribution sentence and in the
     abstract's Results as such.
  3. **The seed spread of the trained arms is not measured.** The 2026-11-04
     re-execution established that nothing downstream of training reproduces and
     diagnosed why (the global RNG was never seeded; `seeded_model()` and
     `tests/test_training_seeding.py` fix it going forward), but the size of the
     run-to-run spread at the end of training is still unknown, and the only figure on
     record is a 0.26 % difference in training loss at step 150 of 4000. The claims
     that rest on a single draw should be replicated across seeds on the D2 arm, which
     carries the sharpest of them — the 5.6-fold increase. If it survives three seeds
     it is reported as surviving three seeds; the shipped v0.2.0 weights predate the
     seeding repair either way and stay the manuscript's archived source.
- Two gates remain as they were: `author_visual_approval` PENDING, and
  `independent_codex_claude_review` structurally unable to run under AI-Check v1,
  which POLICY.md section 4 covers by requiring the project's own execution checks and
  a record of what the basis does not cover. Nothing was sent.

## 2026-11-23, later — the three changes are made

All three changes identified above are in `paper/manuscript.md`, and the document was
rebuilt and reinspected.

- **The Conclusions lead with the three rules.** Both the abstract's Conclusions and
  Section 5 now state them in order — a narrower iodine distribution is not a more
  accurate one, a penalty on the material coordinates does not protect what is
  orthogonal to them, and a fixed-template calculation credits noise suppression but not
  signal loss — and keep the scope limits after them. Section 5 ends on what a reader
  should do, not on what was not done. The abstract is still exactly 200 words, which is
  an equality in `check_template_conformance.py`, not a maximum: the new clause was paid
  for word for word elsewhere in the abstract.
- **The loss ablation is named as one.** The Introduction's contribution sentence now
  says D1 and D2 differ in the loss alone, on identical data under an identical
  protocol, so the effect of the loss term is separable from the effect of denoising,
  and the abstract's Methods describes D2 as the same network with an added penalty.
- **The seed spread is measured, and the claim survives.** `tools/seed_replication_d2.py`
  retrained the D2 arm from three seeds fixed before any outcome was seen — 20261019,
  20261020, 20261021 — on the same pre-generated phantom files, the same 160/32 split,
  β = 3.0 and 4000 steps, and ran the frozen six-condition evaluation on each.
  `tools/train_denoiser.py` gained `--seed`, defaulting to the protocol seed so no
  reported arm changes, logged in every entry, written into the checkpoint, and guarded
  so a checkpoint cannot be resumed under a different seed.
  - Quarter count: the two-basis residual was 4.81–6.35 HU, a standard deviation over
    the three seeds of 0.67–0.71 HU within a condition, and 5.09–6.67 times the D1
    residual across the nine seed-and-condition combinations, mean 5.95. The lowest
    single training was still 5.1 times D1.
  - Full count: 1.07–1.63 HU, 2.78–4.18 times D1.
  - The archived v0.2.0 realization, 5.26–5.29 HU and 5.56–5.59 times D1, falls inside
    both ranges. It is not at the favourable edge of the spread; it is near the middle.
  - The iodine deviation does not behave that way. The penalty improved the absolute
    deviation in six of the nine combinations rather than in a fixed subset of
    conditions, and the spread across seeds within one condition, 0.81–0.98 mgI/mL, is
    as large as the D2 − D1 difference itself, 0.36–1.32 mgI/mL. So the orthogonal-residual
    increase is a property of the loss term, while the direction of the iodine change is
    not separable from the draw at three replicates. Section 5's second rule says that.
  - Results in `results/seed_replication_d2.json`. The manuscript's reported values are
    unchanged and still come from the archived weights, which predate the seeding repair
    and cannot be regenerated; Section 2.3 now says so in the article itself. D1 and TV
    were not retrained, so the spread is the ratio's numerator alone.

The rebuild went from 19 to 20 pages, and every page and both title pages were opened at
150 dpi. One defect was found: Table 3 came out with its caption and first two rows at
the foot of page 8 and its remaining four rows on page 9. The fix is in the builder, not
the document — `submission/jxst/build_submission_docs.py` now sets `w:cantSplit` on every
table row, `keep_with_next` on every caption, and `keep_with_next` on every row but the
last, so a table and its title move to the next page together. Table 3 is now whole on
page 9. `paper/record_visual_review.py` was also corrected: it re-pinned hashes but
carried the page counts forward unchanged, so a ledger saying 19 pages could not be
brought to 20 except by the hand edit that module exists to prevent; the counts are now
derived from the pinned artefacts.

Checks after the rebuild: `check_template_conformance.py` structural PASS,
`check_reference_density.py` OK at 36 references over 5,895 body words,
`check_author_identity.py` OK, `check_release_metadata.py` OK,
`check_visual_review_currency.py` OK, pytest 109 passed in 35.5 s.

The build needs two interpreters and says so when it is given one: the project `.venv`
carries numpy, scipy, scikit-image, matplotlib, torch and pydicom, and `DOCX_PYTHON` must
point at an interpreter with python-docx 1.2.0.

Three gates are unchanged and remain the reasons this is a draft:
`independent_codex_claude_review` BLOCKED, `research_end_to_end_reexecution` PARTIAL, and
`author_visual_approval` PENDING, which is the author's and was not recorded here.

## 2026-11-23, later still — v0.3.0, because v0.2.0 could not answer the paper

The manuscript cited release v0.2.0, archive DOI 10.5281/zenodo.23875047. That archive
does not contain `tools/seed_replication_d2.py`, `results/seed_replication_d2.json` or
`tests/test_training_seeding.py`, all written today. Section 2.3 states that the seeding
defect "is corrected in the released code and is covered by a test", and section 3.3
reports numbers from the replication. Against the cited archive a reader could check
neither. The runbook's rule is the same one in other words: a release has to contain
every result file the manuscript cites.

So v0.3.0 was cut. **No reported value changed**; the figures, tables and frozen result
files are the ones v0.2.0 carried, and the manuscript's numbers still come from the
archived weights of that state of the code.

- Version raised **before** the tag, in `pcctvmi/__init__.py`, `pyproject.toml`,
  `.zenodo.json`, `CITATION.cff` and `paper/release.json`, because Zenodo reads
  `.zenodo.json` from the commit the release points at and cannot correct a published
  record (runbook 5.8.1). `version_doi` was set to null in between, so the built
  data-availability sentence said in words that the DOI was not yet minted rather than
  carrying a token that reads as filled in.
- `tools/verify_archive.py` expanded the tag into an empty directory (135 files), built
  a new environment from the shipped pins, ran `paper/figures.py` there and compared
  bytes: **all ten figure files identical**. The check first reported a rotten archive
  for a reason of its own — it passed a work directory in the Windows 8.3 short form
  (`C:\Users\YAMAMO~1\...`) to a subprocess that resolves paths to the long form, and
  `figures.py` then failed `relative_to` on its own file. The fix is in the gate, and is
  in the tag.
- Tag and release pushed; Zenodo minted **10.5281/zenodo.24468454** at 14:34 UTC. That
  DOI, the `CITATION.cff` identifier and its description were written afterwards. The
  README badge stays the concept DOI, 10.5281/zenodo.23875046.
- The rebuild changed exactly two pages: manuscript page 12 and title page 2, both the
  data-availability sentence. Both were opened at 150 dpi and read; the other twenty
  rasterized byte-identically, so the review was re-pinned for those two only.
- Gates after the rebuild: release metadata OK (both DOIs resolved through doi.org),
  author identity OK, reference density OK, visual-review currency OK,
  `check_template_conformance.py` structural PASS, pytest 109 passed. CI green on the
  pushed commits.

**One thing is not finished on disk.** `submission/jxst/output/manuscript.pdf` is held
open by another process — a viewer still showing the copy delivered earlier — so Word
could not overwrite it and the file in `output/` is still the 21:39 export with the
v0.2.0 DOI. The `.docx` is current, the page rasters are current, and the PDF content is
known: it was exported to a scratch directory from the same `.docx` and inspected there.
Close the PDF and re-run the build to put it back in place:

    $env:DOCX_PYTHON = "C:\Users\YamamotoShuji\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    .\.venv\Scripts\python.exe -X utf8 -B paper\build_all.py

Until that runs, do not send `output/manuscript.pdf` anywhere: it is the previous
version.

*(Done the same evening: the file was closed, the build re-ran, and the page rasters
came out byte-identical to the ones rendered in the scratch directory.)*

## 2026-11-24 — the independent review, and what it found

The IoO publication gate is deployed in this repository. `publication/` is a
byte-identical copy of `D:/DevGit/IoO/publication`, `publication.json` names the
manuscript, the policy and the submitted artefacts, and
`publication/publication_gate.py --snapshot` pins them. An independent **ChatGPT**
review was obtained over seven rounds against those snapshots, on the author's
instruction that the cross-check be ChatGPT only. The final record is stored verbatim at
`publication/reviews/chatgpt.json`; it was read out of the conversation in slices and
checked against a SHA-256 computed in the browser, so it is the reviewer's text and not
a paraphrase. Its decision is `blocked`, five of its six checks pass, and it states in
its own unresolved list that the Codex and Claude reviews the policy requires were not
obtained.

**It was worth doing.** Four defects it found were real, and three of them were mine,
introduced the same day:

- **A false statement about the replication.** Section 3.3 said the archived D2
  realization "falls inside both ranges". At quarter count it does. At full count it
  does not: the archived low end is 1.0516 HU against a lowest replicate of 1.0671 HU.
  The text now says where it falls outside, to 0.02 HU.
- **A number with no source.** Section 3.3 compared the seed spread against "the
  difference between D2 and D1 itself, 0.36-1.32 mgI/mL". That interval could not be
  reproduced from any frozen file. The archived D2 arm moved the absolute iodine
  deviation by 0.02-0.72 mgI/mL, and the change over the nine seed-and-condition runs
  spans 1.32 better to 0.45 worse. `tools/seed_iodine_summary.py` now derives all of it
  from the frozen evaluations into `results/seed_iodine_summary.json`, so the prose
  quotes a file instead of a memory (runbook 3.1).
- **An attribution stronger than the design.** "The increase in the orthogonal residual
  is therefore a property of the loss term" rests on three D2 trainings against a single
  unreplicated D1. Section 1, section 3.3, section 4.4 and the cover letter now say what
  was actually compared.
- **A claim contradicted by the paper's own Table 3**, which only became visible once
  the reviewer had the built document: section 3.4 said RMSE and structural similarity
  "ranked the extrapolation behavior differently" at 12.5%. They do not. Both rank TV,
  D1w, Raw. The text now reports the ordering they agree on and makes no rate comparison
  between two quantities on different scales.

**And reading the pages found one the reviewer could not see.** All 20 manuscript pages
and both title pages were opened at 150 dpi. The generated tables set negative numbers
with an ASCII hyphen, which Word may break a line on: a cell could print the minus at
the end of one line and the digits at the start of the next, which reads as a positive
number. `submission/jxst/build_submission_docs.py` now writes U+2212 in the table cells
and in the built text, and leaves the CSV copies alone because software reads those. The
prose was already correct. The runbook names this defect class in section 3.4; no gate
in this repository looks for it.

The snapshot definition changed once, for cause. It used to include
`paper/visual_review.json` and `paper/readiness.json`, which record the inspection of the
submission - so recording an inspection invalidated the review that inspection was
carried out for. Those are out; the built manuscript text is in.

**State of the gates.** `check_template_conformance.py` is a structural PASS and
`submission_status` is BLOCKED on two: `independent_codex_claude_review`, because one
review of three was obtained, and `research_end_to_end_reexecution`, which is PARTIAL
because nothing downstream of training reproduces bit-for-bit - disclosed in section 2.3
and now measured, but still PARTIAL on the record. While either is open the title page
prints `DRAFT - not for submission`. That banner is the state of the package, and
removing it is a decision about those two gates, not a formatting step.
