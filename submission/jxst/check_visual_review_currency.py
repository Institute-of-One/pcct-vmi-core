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
OUTPUT = ROOT / 'submission/jxst/output'
REVIEW_GATES = ('figure_visual_review', 'document_all_page_visual_review')
PAGE_IMAGE = re.compile(r'final-(page|title)-\d+\.png$')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def basename(rel):
    return Path(str(rel).replace('\\', '/')).name


def rendered_pages():
    """The page images the build actually wrote, which is the fact the ledger claims."""
    if not OUTPUT.is_dir():
        return []
    return sorted(p.name for p in OUTPUT.iterdir() if PAGE_IMAGE.match(p.name))


def check(review=None, readiness=None, manifest=None, live=None, on_disk=None):
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
    # while every page of it has been rasterized and opened. Both halves of this have to
    # come from the build: an earlier version counted the ledger's 'manuscript_pages'
    # against the page entries in the same hand-written ledger, which is a value compared
    # with itself. A manuscript that grew to 21 pages would have rendered two images that
    # appear on neither side, and the rule stayed green.
    on_disk = rendered_pages() if on_disk is None else sorted(on_disk)
    pinned = {basename(r) for r in review.get('artifacts', {})
              if PAGE_IMAGE.match(basename(r))}
    unpinned = [n for n in on_disk if n not in pinned]
    if unpinned:
        bad.append('the build renders %d page image(s) the review does not pin: %s'
                   % (len(unpinned), ', '.join(unpinned[:5])))
    pages = [n for n in on_disk if n.startswith('final-page-')]
    if on_disk and review.get('manuscript_pages') and len(pages) != review['manuscript_pages']:
        bad.append('the review says %d manuscript pages but the build rendered %d'
                   % (review['manuscript_pages'], len(pages)))

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
    on_disk = rendered_pages()
    GOOD = dict(review=review, readiness=readiness, manifest=manifest,
                live=live, on_disk=on_disk)

    def whole(**kw):
        merged = dict(GOOD)
        merged.update(kw)
        return check(**merged)

    baseline = whole()
    print('baseline (the live sources, %d finding(s)):' % len(baseline))
    for b in baseline:
        print('   - %s' % b[:150])

    a_page = next(r for r in review['artifacts'] if 'final-page-' in r)
    a_figure = next((r for r in review['artifacts']
                     if '/figures/' in r.replace('\\', '/')), None)
    one_short = json.loads(json.dumps(review))
    one_short['standalone_figures_opened'] = one_short['standalone_figures_opened'][:-1]
    miscounted = json.loads(json.dumps(review))
    miscounted['manuscript_pages'] = review['manuscript_pages'] + 2

    # Each case names the finding it must produce. Without that a case can be reported
    # DETECTED on a finding some other rule raised, which is how a rule that never fires
    # keeps its green tick.
    cases = [
        ('a page was rebuilt after the review',
         dict(live=dict(live, **{a_page: 'f' * 64})),
         'was rebuilt after the review'),
        ('a reviewed artefact is missing',
         dict(live=dict(live, **{a_page: None})),
         'is missing'),
        ('one shipped figure was never opened',
         dict(review=one_short),
         'the review opened figures'),
        ('the manuscript grew a page nobody pinned',
         dict(on_disk=sorted(on_disk + ['final-page-99.png'])),
         'the review does not pin'),
        ('the ledger miscounts the pages the build rendered',
         dict(review=miscounted),
         'but the build rendered'),
        ('readiness still records PASS over a stale document review',
         dict(live=dict(live, **{a_page: 'f' * 64})),
         'still records document_all_page_visual_review as PASS'),
    ]
    if a_figure:
        cases.append((
            'readiness still records PASS over a regenerated figure',
            dict(live=dict(live, **{a_figure: 'f' * 64})),
            'still records figure_visual_review as PASS',
        ))

    ok = True
    for name, kwargs, expect in cases:
        if all(json.dumps(v, sort_keys=True, default=str)
               == json.dumps(GOOD[k], sort_keys=True, default=str)
               for k, v in kwargs.items()):
            print('  NO-OP    %s (the injection changed none of the inputs)' % name)
            ok = False
            continue
        found = [f for f in whole(**kwargs) if f not in baseline]
        hit = [f for f in found if expect in f]
        print('  %-8s %s' % ('DETECTED' if hit else 'MISSED', name))
        if hit:
            print('           -> %s' % hit[0][:140])
        else:
            ok = False
            print('           expected a finding containing %r; got %s'
                  % (expect, [f[:90] for f in found] or 'nothing'))

    # Negative control: a review whose hashes are the files on disk must be silent.
    current = json.loads(json.dumps(review))
    current['artifacts'] = {k: v for k, v in live.items() if v}
    quiet = whole(review=current, live=live)
    print('  %-8s %s' % ('SILENT' if not quiet else 'NOISY',
                         'review recorded against the current files (negative control)'))
    if quiet:
        print('           -> %s' % quiet[0][:140])
    ok = ok and not quiet

    # Second control: the readiness rule must stay silent when the gate is not PASS.
    if a_figure:
        not_claiming = dict(readiness, figure_visual_review='PENDING - being redrawn')
        spoken = [f for f in whole(live=dict(live, **{a_figure: 'f' * 64}),
                                   readiness=not_claiming)
                  if 'figure_visual_review as PASS' in f]
        print('  %-8s %s' % ('SILENT' if not spoken else 'NOISY',
                             'a stale figure while readiness does not claim PASS'))
        ok = ok and not spoken

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
