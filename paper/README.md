# IORN-016 manuscript source and build

`manuscript.md` is the editable English source. Do not edit generated DOCX files.
The primary manuscript contains 5,193 body words, a 200-word abstract, five figures,
three tables, and 36 DOI-verified references. Those counts are measured by the build and
written to `submission/jxst/output/build_report.json`; the sentence above is prose and
can go stale, which it did once already at ten references.

## Build

From the repository root, using a Python environment with the packages in
`paper/requirements-manuscript.txt`:

```powershell
.venv\Scripts\python.exe -X utf8 -B paper\build_all.py
```

The build regenerates all figures from frozen JSON and original local walnut data,
then tables, text, Word files, and PDFs (Microsoft Word COM on Windows).
`DOCX_PYTHON` can select a separate interpreter with python-docx installed.
`--no-pdf` explicitly requests only a draft build; it is not a full delivery build.
`--strict` fails while any submission gate remains open. Default structural success
does not mean that the package is ready to submit.

Source images are not redistributed. Figure 5 requires the existing archive
`data/walnut/Reconstructions.zip`; obtain it following `docs/DATA.md`.
No download is performed automatically.

```powershell
.venv\Scripts\python.exe -X utf8 -B submission\jxst\check_references.py
.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s submission\jxst -p test_conformance.py -v
.venv\Scripts\python.exe -X utf8 -B paper\verify_results.py
```

The reference checker resolves every DOI using doi.org content negotiation and
compares registered titles and years. The original implementation was adapted
from ctp-core's SoftwareX submission checker. The conformance tests include known
defects in abstract length, figure order, reference use, and declarations.
The result verifier reaggregates both 60-slice walnut runs and replays slice 530
at 25%; it does not retrain networks or rerun the entire simulation experiment.

## Scientific interpretation retained in this draft

- H1: all frozen-template D1 peaks move 60 → 40 keV, but only five of six
  amplitude-scaled peaks are 40 keV. The remaining peak is 190 keV.
- H2: not supported for D1; variance and the deviation RMS proxy improve.
  Residual quarter-count bias remains.
- H3: not supported as a consistent recovery strategy. D2 improves some
  quarter-count biases but introduces full-count positive bias and larger residuals.
- H4: limited directional evidence of noise reduction with systematic material
  shifts. It does not validate detection or unchanged-model transfer.
- D1 jointly processes 16 channels; it is not an independently trained
  single-energy network. D1w is separately retrained on two channels.
- Walnut test-slice mean offsets and VMI operator fitting prevent a fully
  independent external-validation claim. SSIM is whole-image; RMSE is centrally
  masked. Material errors are on a calibration-table scale, not chemical truth.

## Journal requirements checked 2026-10-29

Official current sources:

- https://journals.sagepub.com/page/xst/callforsubmissions-ai-pcct
- https://journals.sagepub.com/author-instructions/xst
- https://www.sagepub.com/docs/default-source/msg/submission-guidelines_-journal-of-x-ray-science-and-technology_-sage-journals.pdf?sfvrsn=f4e3f1f3_3

The current CFP gives 31 December 2026 and manuscript type `Special Issue - AI in PCCT`.
The author page prefers Word, explicitly says no template is required, asks for a
structured 200-word abstract, and uses single-anonymized review and Vancouver
references. A separate title page is included. The current page points to ScholarOne;
the older PDF points to Editorial Manager, so the current page/CFP takes precedence.
The author page itself has inconsistent color-print fee wording; obtain a quote if
print color is requested. No payment or submission has been performed.

### Re-checked 2026-11-02, immediately before submission

The call is still open and nothing above has changed. Sage serves both pages behind a
bot challenge that refuses WebFetch and the in-app browser, so the pages were read in
the author's own Chrome. Requirements taken verbatim from the live pages, each of which
the submission gates must enforce rather than remember:

- Submission deadline 31 December 2026; first decision 28 February 2027; issue in Q2 2027.
- ScholarOne at `https://mc.manuscriptcentral.com/xst`, manuscript type
  `Special Issue - AI in PCCT`.
- A publication fee of `$450/£350` is payable on acceptance *on the subscription route*;
  open access via Sage Choice is a separate, optional fee.
- Single-anonymized. "Two independent reviews are required for a manuscript to reach a
  Revise decision".
- Structured abstract of 200 words between the title and the body; minimum 4-5 keywords.
- Sage Vancouver references. "Citations to preprints are otherwise discouraged."
- Title page as a separate file, not sent to reviewers, carrying the title, every author
  with affiliations, and corresponding-author contact details that must include a
  **telephone number and institutional street address**, plus Acknowledgments,
  declaration of conflicting interest, funding statement, ethical approval and informed
  consent statements, and a data availability statement.
- A `Statements and Declarations` section at the end of the article itself, after
  Acknowledgements and Author Contributions, repeating those sub-headings.
- "The author information you enter at submission must exactly match what is included on
  your manuscript and/or title page, including full names, academic affiliations, and
  corresponding author contact details."
- Article types list only Research articles. There is no Note or Short Communication
  category, so there is no bucket to be downgraded into; a manuscript that reads as too
  slight is rejected rather than reclassified.

## Open gates

See `readiness.json` and `submission/jxst/output/conformance_report.json`.
Contact details are resolved: on 2026-11-02 the author supplied his telephone number and
approved the block, so `check_author_identity.py` passes. All declarations are now final
wording. The generative-AI declaration closed on 2026-11-03, when the author confirmed
that OpenAI Codex was the only generative-AI tool used during the October research and
implementation work; the two sentences it used to carry were notes asking for exactly
that, and prose cannot declare what nobody had been asked.
The public code locator and the version archive DOI are resolved: the repository is
public at https://github.com/Institute-of-One/pcct-vmi-core, release v0.2.0 is archived
on Zenodo, and the data-availability statement prints that release's version DOI. They
are held once in `release.json` and checked by `submission/jxst/check_release_metadata.py`.

Independent review is still not PASS, and the reason has changed. The 2026-10-26
fixed-prompt report recorded errors from both services, but a live `ai_check.py doctor`
run on 2026-11-02 returned pass from Codex and from Claude Code. What blocks it is that
AI-Check v1 accepts one test command, `python -m unittest discover`, and will not report
PASS without a passing test inside the snapshot it copies; every test file here is
pytest, and the submission gates need the repository layout, Word and network access, so
none of them run in that snapshot. Its POLICY.md section 4 says to run the project's own
execution checks and an independent review instead of claiming a basis that did not
execute. No project files have been sent to either reviewer.

`tools/run_pipeline.py` runs the research pipeline end to end, in dependency order, from
the physics tables up, and `tools/compare_results.py` compares the results it writes
against this repository's frozen ones leaf by leaf. Until this existed, every result file
was produced by a command typed by hand, and `paper/verify_results.py` re-aggregated the
walnut runs and replayed one slice without retraining anything.

Before submission, the author must inspect every figure and the final Word/PDF,
approve all declarations, and complete the remaining review gates.

### Re-checked 2026-11-23, with the cover letter

Both live pages were read again in the author's own Chrome. The call, the dates, the
manuscript type and the fee are unchanged, and the guidelines still say
"Identity transparency: Single anonymized". Two things were read that the earlier
transcription had wrong or did not have:

- **The journal does not take suggested reviewers at all.** "To ensure the integrity of
  the peer review process we assign reviewers and cannot accept author recommendations."
  The 2026-11-02 note above said the submission "needs suggested reviewers to be
  realistic about timing"; that is not an option here, and the line has been removed
  rather than left to be acted on.
- **The fee is a publication fee on the subscription route, not an open-access charge.**
  "When an article is accepted for publication, authors are required to pay a
  publication fee of $450/£350." Nothing is payable at submission. Optional open access
  through Sage Choice is a separate fee, and the discounts Sage lists depend on the
  corresponding author's affiliation matching an Open Access agreement at acceptance,
  which this affiliation does not.
- The colour wording is still inconsistent between the two sections of the same page:
  "There is no charge for reproducing figures in colour in the printed version" under
  artwork, and "If you wish to have colour figures in the printed version, fees will be
  determined and applied at production stage" under fees. Ask for a quote rather than
  assume either.

The call's six numbered topics were taken verbatim for the cover letter; this manuscript
answers topics 2, 3 and 6. `submission/jxst/build_cover_letter.py` holds them.
