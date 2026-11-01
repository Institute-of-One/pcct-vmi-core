"""The author block: one source, checked against Crossref and against the built page.

Sage requires a separate title page carrying the corresponding author's institutional
address, telephone and email, and says the details entered in ScholarOne "must exactly
match what is included on your manuscript and/or title page". Read from the live
submission guidelines on 2026-11-02; paper/README.md transcribes them.

Three ways that goes wrong, one rule each:

1. the affiliation is recalled rather than resolved. AGENTS.md section 2: compare with
   the records Crossref actually carries, which is what a copy editor compares with.
2. the single source is bypassed, because the builder keeps its own copy of the string.
3. the file is right and the document is wrong. AGENTS.md section 6: inspect the output,
   not the log. So the built title page is read back and must carry every field.

Run --selftest to prove the rules fire: each planted defect must add a finding that the
live sources do not already produce.
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
AUTHOR = ROOT / 'paper/author.json'
BUILDER = Path(__file__).resolve().parent / 'build_submission_docs.py'
TITLE = ROOT / 'submission/jxst/output/title_page.docx'
REQUIRED = ('name', 'affiliation', 'orcid', 'email', 'street_address', 'telephone')


def crossref_affiliations(orcid):
    """Every affiliation string Crossref carries for this ORCID on a journal article.

    Returns a list of (DOI, string). Raises on a network failure: a gate that cannot
    reach its evidence must say so, not quietly agree with the file it was checking.
    """
    q = ('https://api.crossref.org/works?filter=orcid:%s&rows=50&select=DOI,type,author'
         % urllib.parse.quote(orcid))
    req = urllib.request.Request(q, headers={
        'User-Agent': 'IoO-submission-gate/1.0 (mailto:yamamoto@lisit.jp)'})
    items = json.loads(urllib.request.urlopen(req, timeout=60).read())['message']['items']
    out = []
    for it in items:
        if it.get('type') != 'journal-article':
            continue
        for a in it.get('author', []):
            if orcid in str(a.get('ORCID', '')):
                for aff in a.get('affiliation', []):
                    out.append((it['DOI'], (aff.get('name') or '').strip()))
    return out


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        return ' '.join(ET.fromstring(z.read('word/document.xml')).itertext())


def check(author=None, builder_src=None, title_text=None, crossref=None):
    author = json.loads(AUTHOR.read_text(encoding='utf-8')) if author is None else author
    builder_src = BUILDER.read_text(encoding='utf-8') if builder_src is None else builder_src
    bad = []

    # 1. Every field the journal asks for is actually filled in.
    for field in REQUIRED:
        if not str(author.get(field) or '').strip():
            bad.append('author.json: %s is empty; Sage requires it in the corresponding-'
                       'author contact details on the title page' % field)
    if not author.get('confirmed_by_author'):
        bad.append('author.json: confirmed_by_author is false. The author has not approved '
                   'the contact block, so it must not be submitted')

    # 2. The affiliation, resolved rather than recalled.
    orcid = str(author.get('orcid') or '').strip()
    mine = str(author.get('affiliation') or '').strip()
    if orcid and mine:
        seen = crossref_affiliations(orcid) if crossref is None else crossref
        if not seen:
            bad.append('Crossref carries no affiliation for ORCID %s on any journal '
                       'article, so the manuscript\'s could not be checked' % orcid)
        elif not [d for d, n in seen if n == mine]:
            bad.append('affiliation %r is on none of the %d Crossref record(s); they carry %s'
                       % (mine, len(seen),
                          '; '.join('%s -> %r' % (d, n) for d, n in seen[:3])))

    # 3. The builder must not carry a second copy of what author.json holds.
    code = '\n'.join(re.sub(r'#.*$', '', ln) for ln in builder_src.splitlines())
    for field in ('affiliation', 'orcid', 'email'):
        value = str(author.get(field) or '').strip()
        if value and value in code:
            bad.append('build_submission_docs.py contains the %s literally (%r). It must '
                       'read paper/author.json, or the two copies will drift' % (field, value))

    # 4. The built page, not the file that was supposed to produce it.
    if title_text is None:
        title_text = docx_text(TITLE) if TITLE.exists() else None
    if title_text is None:
        bad.append('no built title page at %s, so its contents were not checked'
                   % TITLE.relative_to(ROOT))
    else:
        flat = ' '.join(title_text.split())
        for field in REQUIRED:
            value = str(author.get(field) or '').strip()
            if value and ' '.join(value.split()) not in flat:
                bad.append('the built title page does not carry the %s (%r)' % (field, value))
    return bad


def selftest():
    live = json.loads(AUTHOR.read_text(encoding='utf-8'))
    src = BUILDER.read_text(encoding='utf-8')
    title = docx_text(TITLE) if TITLE.exists() else None
    cr = crossref_affiliations(live['orcid'])

    def whole(**kw):
        kw.setdefault('author', live)
        kw.setdefault('builder_src', src)
        kw.setdefault('title_text', title)
        kw.setdefault('crossref', cr)
        return check(**kw)

    # What the live sources already report. A planted defect counts only if it adds to
    # this; without the subtraction one unrelated live failure makes every case pass.
    baseline = whole()
    print('baseline (the live sources, %d finding(s)):' % len(baseline))
    for b in baseline:
        print('   - %s' % b[:140])

    swapped = dict(live, affiliation='Institute of One, LISIT Co., Ltd., 150-0044 Tokyo, Japan')
    blank = dict(live, email='')
    unapproved = dict(live, confirmed_by_author=False)
    other_phone = dict(live, telephone='+81-3-0000-0000')
    planted_src = src.replace('a=json.loads', "_=%r\n    a=json.loads" % live['affiliation'], 1)
    thin_title = (title or '').replace(live['affiliation'], 'LISIT') if title else 'nothing'

    # Each case names the one rule it is planted against, and must produce that rule's
    # finding. Without the expected text a case can pass on a different rule: planting a
    # telephone the page lacks also used to clear confirmed_by_author, so the case named
    # for the title-page rule was reported by the approval rule instead.
    cases = [
        ('postcode before the city', dict(author=swapped), 'is on none of the'),
        ('email removed', dict(author=blank), 'email is empty'),
        ('approval withdrawn', dict(author=unapproved), 'confirmed_by_author is false'),
        ('telephone changed after the page was built', dict(author=other_phone),
         'does not carry the telephone'),
        ('builder keeps its own affiliation', dict(builder_src=planted_src),
         'contains the affiliation literally'),
        ('title page lost the affiliation', dict(title_text=thin_title),
         'does not carry the affiliation'),
    ]
    ok = True
    # Negative control: once the two author-owned items are resolved and the page carries
    # them, the gate must go silent. A rule that can only ever complain is not a gate.
    phone = '+81-3-1234-5678'
    resolved = dict(live, telephone=phone, confirmed_by_author=True)
    quiet = whole(author=resolved,
                  title_text=(title or '') + ' Telephone: ' + phone)
    print('  %-8s %s' % ('SILENT' if not quiet else 'NOISY',
                         'author items resolved (negative control)'))
    if quiet:
        print('           -> %s' % quiet[0][:130])
    ok = ok and not quiet
    for name, kwargs, expect in cases:
        # NO-OP guard: a case that changed nothing proves nothing.
        changed = any(kwargs[k] != {'author': live, 'builder_src': src,
                                    'title_text': title}[k] for k in kwargs)
        found = [f for f in whole(**kwargs) if f not in baseline]
        hit = [f for f in found if expect in f]
        verdict = ('DETECTED' if hit else
                   'WRONG' if found else 'MISSED' if changed else 'NO-OP')
        print('  %-8s %s' % (verdict, name))
        if hit:
            print('           -> %s' % hit[0][:130])
        elif found:
            print('           -> expected %r; got %s' % (expect, found[0][:100]))
        ok = ok and bool(hit) and changed
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
        print('OK   author block: every field present, approved, matching Crossref and the '
              'built title page')
    return int(bool(bad))


if __name__ == '__main__':
    raise SystemExit(main())
