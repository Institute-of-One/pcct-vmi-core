# IORN-016 manuscript source and build

`manuscript.md` is the editable English source. Do not edit generated DOCX files.
The primary manuscript contains approximately 4,600 body words, a 200-word abstract,
five figures, three tables, and ten DOI-verified references.

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

## Open gates

See `readiness.json` and `submission/jxst/output/conformance_report.json`.
Author declarations and contact details are deliberately unresolved.
No public code locator or version archive DOI was invented (this checkout has no
configured Git remote). A clean snapshot/new environment figure rebuild remains.
AI-Check's existing 2026-10-26 fixed-prompt report records errors for both services;
independent review is not PASS. No project files were sent to either reviewer.
pytest and visual review are outside AI-Check v1's standard unittest execution path.

Before submission, the author must inspect every figure and the final Word/PDF,
approve all declarations, and complete the remaining release and review gates.
