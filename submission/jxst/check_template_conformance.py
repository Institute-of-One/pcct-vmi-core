"""Structural draft checks, kept distinct from submission-readiness checks."""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'submission/jxst/output'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def audit(source,docx):
    problems=[]
    abstract=source.split('## Abstract')[1].split('Keywords:')[0]
    if len(abstract.split())!=200: problems.append('Abstract must have 200 words including labels')
    for label in ('Purpose:','Methods:','Results:','Conclusions:'):
        if label not in abstract: problems.append('Missing abstract label '+label)
    body=source.split('## 1. Introduction')[1].split('## Acknowledgements')[0]
    mentions=[int(x) for x in re.findall(r'Figure ([1-5])',body)]
    order=list(dict.fromkeys(mentions))
    if order!=[1,2,3,4,5]: problems.append('Figure first citations out of order or missing')
    required=['Ethical considerations','Consent to participate','Consent for publication',
              'Declaration of conflicting interest','Funding statement','Data availability']
    for heading in required:
        if '### '+heading not in source: problems.append('Missing declaration '+heading)
    with zipfile.ZipFile(docx) as z:
        xml=z.read('word/document.xml'); tree=ET.fromstring(xml)
        text=' '.join(tree.itertext())
        if '{{' in text: problems.append('Unexpanded source placeholder')
        if len(tree.findall('.//w:tbl',NS))!=3: problems.append('Expected three tables')
        if len(tree.findall('.//w:drawing',NS))!=5: problems.append('Expected five embedded figures')
        footers=[z.read(n) for n in z.namelist() if re.fullmatch(r'word/footer\d+\.xml',n)]
        if not any(b'PAGE' in f for f in footers): problems.append('Missing page field')
    refs=json.loads((ROOT/'paper/references.json').read_text(encoding='utf-8'))
    used={int(n) for n in re.findall(r'\[(\d+)(?:,\d+)*\]',source)}
    # Include each number of a multi-reference bracket.
    used=set(int(n) for group in re.findall(r'\[([\d,]+)\]',source) for n in group.split(','))
    if used!=set(range(1,len(refs)+1)): problems.append('Reference citations incomplete')
    return problems

def main():
    p=argparse.ArgumentParser();p.add_argument('--strict',action='store_true');args=p.parse_args()
    source=(ROOT/'paper/manuscript.md').read_text(encoding='utf-8')
    errors=audit(source,OUT/'manuscript.docx')
    manifest=json.loads((ROOT/'paper/figure_manifest.json').read_text())
    for f,h in manifest['inputs'].items():
        if hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=h: errors.append('Stale figure input '+f)
    for f,h in manifest['outputs'].items():
        if hashlib.sha256((ROOT/'paper/figures'/f).read_bytes()).hexdigest()!=h: errors.append('Stale figure output '+f)
    refcheck=json.loads((ROOT/'paper/reference_check.json').read_text())
    if refcheck['status']!='PASS': errors.append('DOI resolution failed')
    readiness=json.loads((ROOT/'paper/readiness.json').read_text())
    # A gate may record what it passed on, so the value is read as a verdict plus a
    # reason. Exact equality against 'PASS' made every annotated gate look pending.
    pending=[k for k,v in readiness.items() if not re.match(r'PASS\b',str(v))]
    report={'structural_status':'FAIL' if errors else 'PASS','errors':errors,
            'submission_status':'BLOCKED' if pending else 'PASS','pending_gates':pending}
    (OUT/'conformance_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return int(bool(errors) or (args.strict and bool(pending)))

if __name__=='__main__':sys.exit(main())
