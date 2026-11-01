"""Resolve all DOIs; retain CSL metadata and compare title/year on subsequent runs.

Adapted from ctp-core/submission/softwarex/check_references.py. No DOI is inferred.
First acquisition uses reference_seed.json; later runs verify references.json.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'paper'

def normalise(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()

def main():
    target = OUT / 'references.json'
    seeds = json.loads((OUT / 'reference_seed.json').read_text())
    previous = {r['doi']:r for r in json.loads(target.read_text())} if target.exists() else {}
    refs = [previous.get(r['doi'],r) for r in seeds]
    records, errors = [], []
    for ref in refs:
        doi = ref['doi']
        try:
            req = urllib.request.Request('https://doi.org/' + doi, headers={
                'Accept':'application/vnd.citationstyles.csl+json',
                'User-Agent':'IORN-016 manuscript reference verification'})
            with urllib.request.urlopen(req, timeout=40) as response:
                record = json.load(response)
            title = record['title']
            if isinstance(title, list): title = title[0]
            year = record['issued']['date-parts'][0][0]
            if ref.get('title') and normalise(ref['title']) != normalise(title):
                raise ValueError('registered title changed')
            if ref.get('year') and ref['year'] != year: raise ValueError('year changed')
            records.append({'doi':doi, 'title':title, 'year':year, 'csl':record})
            print('RESOLVED', doi, year, title)
        except Exception as exc:
            errors.append({'doi':doi, 'error':str(exc)})
    report = {'checked_at':datetime.now(timezone.utc).isoformat(),
              'status':'FAIL' if errors else 'PASS', 'resolved':len(records), 'errors':errors}
    (OUT / 'reference_check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if errors:
        print(errors)
        return 1
    target.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding='utf-8')
    return 0

if __name__ == '__main__': sys.exit(main())
