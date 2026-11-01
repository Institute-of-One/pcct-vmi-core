"""Does the recorded visual review still describe the files that would be submitted?

paper/visual_review.json says a human opened every page and every figure, and pins the
sha256 of each artefact that was opened. Nothing compared those hashes with the files on
disk, so any rebuild - a corrected title page, a regenerated figure - left the review
claiming to cover bytes that no longer existed, with readiness.json still saying PASS.

That is the defect class AGENTS.md section 3 describes for figures: the manuscript gates
read the .docx, so nobody was looking at the artefacts themselves. Here the ledger
existed; what was missing was anything that read it back.

  python submission/jxst/check_visual_review_currency.py
  python submission/jxst/check_visual_review_currency.py --selftest
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'paper/visual_review.json'
MANIFEST = ROOT / 'paper/figure_manifest.json'
READINESS = ROOT / 'paper/readiness.json'
REVIEW_GATES = ('figure_visual_review', 'document_all_page_visual_review')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def check(review=None, readiness=None, manifest=None, live=None):
    review = json.loads(REVIEW.read_text(encoding='utf-8')) if review is None else review
    readiness = (json.loads(READINESS.read_text(encoding='utf-8'))
                 if readiness is None else readiness)
    manifest = (json.loads(MANIFEST.read_text(encoding='utf-8'))
                if manifest is None else manifest)
    bad = []
    stale = {}                      # gate name -> the artefacts that invalidate it
    for rel, recorded in review.get('artifacts', {}).items():
        path = ROOT / rel.replace('\\', '/')
        now = digest(path) if live is None else live.get(rel)
        if now is None:
            why = '%s is missing' % rel
        elif now != recorded:
            why = ('%s was rebuilt after the review (%s -> %s)'
                   % (rel, recorded[:8], now[:8]))
        else:
            continue
        # Attribute the staleness to the gate it actually invalidates: a regenerated
        # figure does not unreview the document, and a rebuilt document does not
        # unreview the figures.
        gate = ('figure_visual_review' if '/figures/' in rel.replace('\\', '/')
                else 'document_all_page_visual_review')
        stale.setdefault(gate, []).append(why)
        bad.append('the visual review no longer covers what would be submitted: %s' % why)

    # The pinned artefacts are the rendered pages, so the review covers a document only
    # while every page of it has been rasterized and opened.
    rendered = [r for r in review.get('artifacts', {}) if 'final-page-' in r]
    if review.get('manuscript_pages') and len(rendered) != review['manuscript_pages']:
        bad.append('the review says %d manuscript pages but pins %d page images'
                   % (review['manuscript_pages'], len(rendered)))

    # Every figure that ships must have been opened, and the count comes from the
    # manifest rather than from a number written into this file.
    shipped = sorted({int(m.group(1)) for name in manifest.get('outputs', {})
                      for m in [re.match(r'figure(\d+)\.png$', name)] if m})
    opened = sorted(review.get('standalone_figures_opened', []))
    if shipped and opened != shipped:
        bad.append('the review opened figures %s but the build ships %s'
                   % (opened or 'none', shipped))

    # A PASS in readiness.json is only allowed to stand while the above holds.
    for gate in REVIEW_GATES:
        if stale.get(gate) and re.match(r'PASS\b', str(readiness.get(gate, ''))):
            bad.append('readiness.json still records %s as PASS, but %s'
                       % (gate, stale[gate][0]))
    return bad


def selftest():
    review = json.loads(REVIEW.read_text(encoding='utf-8'))
    readiness = json.loads(READINESS.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    live = {rel: digest(ROOT / rel.replace('\\', '/'))
            for rel in review.get('artifacts', {})}

    def whole(**kw):
        kw.setdefault('review', review)
        kw.setdefault('readiness', readiness)
        kw.setdefault('manifest', manifest)
        kw.setdefault('live', live)
        return check(**kw)

    baseline = whole()
    print('baseline (the live sources, %d finding(s)):' % len(baseline))
    for b in baseline:
        print('   - %s' % b[:150])

    first = next(iter(review['artifacts']))
    rebuilt = dict(live, **{first: 'f' * 64})
    gone = dict(live, **{first: None})
    one_short = json.loads(json.dumps(review))
    one_short['standalone_figures_opened'] = one_short['standalone_figures_opened'][:-1]
    claiming = dict(readiness, figure_visual_review='PASS')

    cases = [
        ('an artefact was rebuilt after the review', dict(live=rebuilt)),
        ('a reviewed artefact is missing', dict(live=gone)),
        ('one shipped figure was never opened', dict(review=one_short)),
        ('readiness still claims PASS over a stale review',
         dict(live=rebuilt, readiness=claiming)),
    ]
    ok = True
    for name, kwargs in cases:
        found = [f for f in whole(**kwargs) if f not in baseline]
        print('  %-8s %s' % ('DETECTED' if found else 'MISSED', name))
        if found:
            print('           -> %s' % found[0][:140])
        ok = ok and bool(found)

    # Negative control: a review whose hashes are the files on disk must be silent.
    current = json.loads(json.dumps(review))
    current['artifacts'] = {k: v for k, v in live.items() if v}
    quiet = whole(review=current, live=live)
    print('  %-8s %s' % ('SILENT' if not quiet else 'NOISY',
                         'review recorded against the current files (negative control)'))
    if quiet:
        print('           -> %s' % quiet[0][:140])
    ok = ok and not quiet
    print('selftest %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--selftest', action='store_true')
    args = p.parse_args()
    if args.selftest:
        return selftest()
    bad = check()
    for b in bad:
        print('FAIL %s' % b)
    if not bad:
        print('OK   the recorded visual review matches the artefacts on disk')
    return int(bool(bad))


if __name__ == '__main__':
    raise SystemExit(main())
