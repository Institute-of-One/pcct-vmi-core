"""Build the cover letter from the same sources as the manuscript.

A cover letter is a submitted document. Every gate in this directory reads the
manuscript, and a letter written by hand beside it drifts: it keeps a retired DOI, an
old title, or a number that the frozen results no longer support, and nothing notices
because nothing is looking at it.

So the letter is generated. The title comes from `paper/manuscript.md`, the repository
and the archive DOI from `paper/release.json`, the author block from the public fields of
`paper/author.json` - never from `paper/author_contact.local.json`, because the telephone
and street address belong on the title page and not in a textarea - and the one place
numbers appear is a verbatim quotation of the abstract's Results sentence, which is
itself built from the frozen result files. No figure is typed here (runbook 3.1).

While `paper/readiness.json` has an open gate the letter carries a DRAFT line, for the
same reason the title page does: a letter that reads as final is the one that gets
pasted into the portal.

The venue facts below were read on the live Sage pages on 2026-11-23: the call's six
numbered topics, the scope sentence about interdisciplinary studies, and
"Identity transparency: Single anonymized" in the submission guidelines.

    python submission/jxst/build_cover_letter.py
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from readiness_gates import pending_gates                      # noqa: E402

ROOT = HERE.parents[1]
PAPER = ROOT / 'paper'
OUT = ROOT / 'submission/jxst/output'

ISSUE = ('Artificial Intelligence in Photon-Counting CT: Advances in Imaging, '
         'Reconstruction, and Applications')
MANUSCRIPT_TYPE = 'Special Issue - AI in PCCT'
TOKENS = ('{{', 'PENDING', 'TODO', 'FIXME', 'XXXX')

BODY = """Dear Guest Editors,

I submit the enclosed original research article, "{title}", for the special thematic \
issue "{issue}", under the manuscript type "{manuscript_type}".

The study measures what AI denoising does to two quantities photon-counting CT is used \
for: energy-dependent model-observer detectability, and iodine quantitation after \
material decomposition. A convolutional denoiser was trained on simulated spectral data \
in two arms that differ in the loss alone - a reconstruction loss, and the same network \
with an added penalty on the material-basis coordinates - and both were compared with a \
total-variation reference over six dose and lesion-size conditions, with a public \
specimen reconstruction as a stress test.

The result I would put in front of this issue's readers is that loss ablation. The \
physics-motivated penalty improved the quantity it targeted in some conditions, and \
made the spectral residual orthogonal to those coordinates several times worse at \
quarter count. Retraining that arm from three seeds fixed before any outcome was \
inspected reproduced the effect in every draw, so it is a property of the loss term \
rather than of the initialization. Two further findings follow from the same \
measurements: a narrower iodine distribution was not a more accurate one, and a \
fixed-template detectability calculation credits noise suppression without accounting \
for signal loss, which moved one condition's optimal energy to the top of the sampled \
grid.

This is the manuscript's own summary of what was measured, quoted from its abstract:

{results}

The work answers three of the call's topics in its own terms: deep learning methods for \
PCCT denoising and low-dose imaging (topic 2); AI-based spectral information \
utilization, material decomposition and quantitative imaging in PCCT (topic 3); and \
evaluation metrics, robustness and uncertainty analysis (topic 6). It is the kind of \
interdisciplinary study the scope asks for, integrating artificial intelligence with \
PCCT imaging physics, spectral characteristics and quantitative analysis, and several \
of its findings identify technical challenges rather than report an improvement.

What I do not claim is as much a part of the submission as what I do. There is no new \
network architecture, no detection or diagnostic performance against human readers, and \
no clinical validation. The primary data are simulated spectral images and the stress \
test uses a public specimen reconstruction, so no patient data were involved and no \
ethics approval or informed consent was required.

The code, the frozen result files from which every figure and table in the article is \
regenerated, the trained weights and the figure-drawing code are public at {repository} \
and archived at https://doi.org/{version_doi}. The work is original, has not been \
published elsewhere, and is not under consideration by another journal. There is one \
author. I have no conflicting interests and received no funding, and my use of \
generative AI is declared in the manuscript. The journal's review is single anonymized, \
so the manuscript is not anonymized; the title page carrying my contact details is \
uploaded as a separate file.

Yours sincerely,

{name}
{affiliation}
ORCID {orcid}
{email}
"""


def title_of(markdown):
    m = re.search(r'^#\s+(.+)$', markdown, re.M)
    if not m:
        raise SystemExit('paper/manuscript.md has no level-1 title')
    return m.group(1).strip()


def results_sentence(markdown):
    """The abstract's Results paragraph, verbatim.

    It is the only place in this letter where a number appears, and it is quoted rather
    than restated so that it cannot disagree with the article.
    """
    for block in markdown.split('\n\n'):
        block = ' '.join(block.split())
        if block.startswith('Results:'):
            return block
    raise SystemExit("paper/manuscript.md has no abstract paragraph starting 'Results:'")


def build():
    markdown = (PAPER / 'manuscript.md').read_text(encoding='utf-8')
    release = json.loads((PAPER / 'release.json').read_text(encoding='utf-8'))
    author = json.loads((PAPER / 'author.json').read_text(encoding='utf-8'))
    if not release.get('version_doi'):
        raise SystemExit('paper/release.json has no version_doi; the archive DOI is '
                         'minted on release and the letter cites it')
    letter = BODY.format(
        title=title_of(markdown),
        issue=ISSUE,
        manuscript_type=MANUSCRIPT_TYPE,
        results=results_sentence(markdown),
        repository=release['repository'],
        version_doi=release['version_doi'],
        name=author['name'],
        affiliation=author['affiliation'],
        orcid=author['orcid'],
        email=author['email'],
    )
    open_gates = pending_gates()
    if open_gates:
        letter = ('[DRAFT - not for the portal. Open gates: %s. '
                  'Rebuild this file once they close.]\n\n' % ', '.join(open_gates)
                  ) + letter
    return letter, open_gates


def main():
    letter, open_gates = build()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'cover_letter.txt'
    path.write_text(letter, encoding='utf-8')
    body = letter.split(']\n\n', 1)[-1] if open_gates else letter
    for token in TOKENS:
        if token in body:
            raise SystemExit('the letter contains %r, which reads as filled in at a '
                             'glance' % token)
    print('wrote %s (%d words%s)' % (
        path, len(body.split()),
        '; DRAFT, %d gate(s) open' % len(open_gates) if open_gates else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
