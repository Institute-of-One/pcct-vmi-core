"""Does this manuscript cite like a research article in the journal it is going to?

Genre is read off the surface before anything else, and the reference list is the
cheapest surface there is. IORN-013 went to the editor with eight references and
IORN-004 was reclassified for being short. JXST has no Note or Short Communication
category - the live submission guidelines list only Research articles - so a manuscript
that reads as slight is rejected rather than reclassified.

The threshold is not a number anyone typed. --measure asks Europe PMC what the journal
actually published and writes the sample, with its date, to the benchmark file; the
check compares against that. Re-measure if the file is older than the submission.

  python submission/jxst/check_reference_density.py --measure
  python submission/jxst/check_reference_density.py
  python submission/jxst/check_reference_density.py --selftest
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / 'paper/references.json'
BUILD = ROOT / 'submission/jxst/output/build_report.json'
BENCH = ROOT / 'paper/venue_reference_benchmark.json'
API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/'
QUERY = 'JOURNAL:"J Xray Sci Technol" AND (PUB_YEAR:2025 OR PUB_YEAR:2026)'


def _get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'IoO-submission-gate/1.0 (mailto:yamamoto@lisit.jp)'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def measure(sample_size=20):
    """Reference counts of recent papers in the target journal."""
    found = _get(API + 'search?query=%s&format=json&pageSize=40&resultType=core'
                 % urllib.parse.quote(QUERY))
    rows = []
    for r in found['resultList']['result'][:sample_size]:
        try:
            n = _get(API + '%s/%s/references?format=json&pageSize=1'
                     % (r['source'], r['id'])).get('hitCount', 0)
        except Exception as exc:                      # recorded in the sample, not hidden
            rows.append({'id': r.get('id'), 'references': None, 'error': str(exc)[:80]})
            continue
        rows.append({'id': r.get('id'), 'title': (r.get('title') or '')[:90],
                     'references': n})
        time.sleep(0.2)
    counted = sorted(r['references'] for r in rows if r.get('references'))
    if len(counted) < 8:
        raise SystemExit('only %d of %d sampled papers had reference data; too few to set '
                         'a threshold' % (len(counted), len(rows)))
    data = {
        'measured': time.strftime('%Y-%m-%d', time.gmtime()),
        'query': QUERY,
        'source': 'Europe PMC',
        'note': ('Papers whose reference list Europe PMC does not hold come back as 0 and '
                 'are excluded; they are not papers with no references.'),
        'papers_sampled': len(rows),
        'papers_with_reference_data': len(counted),
        'minimum': counted[0],
        'median': counted[len(counted) // 2],
        'maximum': counted[-1],
        'counts': counted,
        'rows': rows,
    }
    BENCH.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('wrote %s: n=%d, min %d, median %d, max %d'
          % (BENCH.relative_to(ROOT), len(counted), data['minimum'], data['median'],
             data['maximum']))
    return data


def check(refs=None, bench=None, body_words=None):
    bad = []
    bench = json.loads(BENCH.read_text(encoding='utf-8')) if bench is None else bench
    if refs is None:
        refs = len(json.loads(REFS.read_text(encoding='utf-8')))
    if body_words is None:
        body_words = json.loads(BUILD.read_text(encoding='utf-8'))['body_words']
    floor = bench['minimum']
    if refs < floor:
        bad.append('the manuscript cites %d references; the thinnest of the %d recent %s '
                   'papers measured on %s cites %d, and the median cites %d. There is no '
                   'Note category to be moved into.'
                   % (refs, bench['papers_with_reference_data'], 'JXST',
                      bench['measured'], floor, bench['median']))
    per_1000 = 1000.0 * refs / body_words
    if per_1000 < 2.5:
        bad.append('%.1f references per 1000 body words (%d references, %d words); an '
                   'original article in this programme carries 2.5-3.'
                   % (per_1000, refs, body_words))
    return bad


def selftest():
    bench = json.loads(BENCH.read_text(encoding='utf-8'))
    live_refs = len(json.loads(REFS.read_text(encoding='utf-8')))
    live_words = json.loads(BUILD.read_text(encoding='utf-8'))['body_words']

    def whole(**kw):
        kw.setdefault('refs', live_refs)
        kw.setdefault('bench', bench)
        kw.setdefault('body_words', live_words)
        return check(**kw)

    baseline = whole()
    print('baseline (the live sources, %d finding(s)):' % len(baseline))
    for b in baseline:
        print('   - %s' % b[:150])
    cases = [
        ('one below the venue floor', dict(refs=bench['minimum'] - 1)),
        ('at the floor but too thin for the length',
         dict(refs=bench['minimum'], body_words=bench['minimum'] * 1000)),
    ]
    ok = True
    for name, kwargs in cases:
        found = [f for f in whole(**kwargs) if f not in baseline]
        print('  %-8s %s' % ('DETECTED' if found else 'MISSED', name))
        if found:
            print('           -> %s' % found[0][:140])
        ok = ok and bool(found)
    # Negative control: a list at the venue's median, on this body, must be silent.
    quiet = whole(refs=bench['median'])
    print('  %-8s %s' % ('SILENT' if not quiet else 'NOISY',
                         'reference list at the venue median (negative control)'))
    if quiet:
        print('           -> %s' % quiet[0][:140])
    ok = ok and not quiet
    print('selftest %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--measure', action='store_true',
                   help='re-query Europe PMC and rewrite the benchmark')
    p.add_argument('--selftest', action='store_true')
    args = p.parse_args()
    if args.measure:
        measure()
        return 0
    if args.selftest:
        return selftest()
    bad = check()
    for b in bad:
        print('FAIL %s' % b)
    if not bad:
        print('OK   reference list is within what this journal publishes')
    return int(bool(bad))


if __name__ == '__main__':
    raise SystemExit(main())
