"""The author block: one source, checked against Crossref, against the built page, and
against what the public repository is allowed to carry.

Sage requires a separate title page carrying the corresponding author's institutional
address, telephone and email, and says the details entered in ScholarOne "must exactly
match what is included on your manuscript and/or title page". Read from the live
submission guidelines on 2026-11-02; paper/README.md transcribes them.

Four ways that goes wrong, one rule each:

1. the affiliation is recalled rather than resolved. AGENTS.md section 2: compare with
   the records Crossref actually carries, which is what a copy editor compares with.
2. the single source is bypassed, because the builder keeps its own copy of the string.
3. the file is right and the document is wrong. AGENTS.md section 6: inspect the output,
   not the log. So the built title page is read back and must carry every field.
4. the contact details reach the publication. From 2026-11-02 this repository is public
   and is the version archive the manuscript cites, so a tracked file is published and
   so is every commit: removing a line later does not unpublish it. The telephone and
   street address therefore live in paper/author_contact.local.json, outside the
   repository (submission/jxst/author_block.py), and this gate looks for them in the
   tracked tree and in the history, not only in the file they were moved out of.

Run --selftest to prove the rules fire: each planted defect must add a finding that the
live sources do not already produce.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from author_block import PRIVATE, PRIVATE_FIELDS, PUBLIC, load_author

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILDER = HERE / 'build_submission_docs.py'
LOADER = HERE / 'author_block.py'
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


def sources():
    """The files that are allowed to format the author block but not to remember it."""
    return {p.name: p.read_text(encoding='utf-8') for p in (BUILDER, LOADER)}


def private_leaks(items, public_text=None, run_git=True):
    """Published places that carry a private contact value.

    A value is published if a tracked file holds it now or any commit ever did, so
    `git log -S` is as much part of this as `git grep`. The findings name the field and
    never the value: this runs in terminals and could run in CI, and a gate that prints
    the telephone to prove it is hidden has published it again.
    """
    out = []
    if public_text is None:
        public_text = PUBLIC.read_text(encoding='utf-8')
    for field, value in items:
        value = str(value or '').strip()
        if not value:
            continue
        if value in public_text:
            out.append('%s carries the %s, and that file is published with the '
                       'repository; it belongs in %s'
                       % (PUBLIC.relative_to(ROOT).as_posix(), field, PRIVATE.name))
        if not run_git:
            continue
        for what, cmd in (
                ('tracked file', ['git', 'grep', '--no-color', '-l', '-F', value, '--']),
                ('commit', ['git', 'log', '--format=%h', '-S', value, '--all'])):
            try:
                r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                                   text=True, timeout=180)
            except OSError as exc:
                out.append('could not run git to look for the %s in the repository (%s)'
                           % (field, exc))
                break
            if r.returncode > 1:
                out.append('git exited %d while looking for the %s: %s'
                           % (r.returncode, field, r.stderr.strip()[:120]))
                continue
            for hit in r.stdout.split():
                out.append('%s %s carries the %s, and this repository is published; a '
                           'later removal does not unpublish a commit'
                           % (what, hit, field))
    return out


def check(author=None, src=None, title_text=None, crossref=None,
          private_present=None, public_text=None, run_git=True):
    author = load_author() if author is None else author
    src = sources() if src is None else src
    bad = []

    # 1. Every field the journal asks for is actually filled in.
    for field in REQUIRED:
        if not str(author.get(field) or '').strip():
            bad.append('author block: %s is empty; Sage requires it in the corresponding-'
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

    # 3. No file that formats the block may carry a second copy of what it reads.
    for name, text in src.items():
        code = '\n'.join(re.sub(r'#.*$', '', ln) for ln in text.splitlines())
        for field in ('affiliation', 'orcid', 'email'):
            value = str(author.get(field) or '').strip()
            if value and value in code:
                bad.append('%s contains the %s literally (%r). It must read the author '
                           'block, or the two copies will drift' % (name, field, value))

    # 4. The private contact details, held outside the published repository.
    if private_present is None:
        private_present = PRIVATE.exists()
    if not private_present:
        bad.append('%s is missing, so the title page cannot carry the telephone and street '
                   'address Sage requires. They are deliberately not in the repository, '
                   'which is published; the author holds them'
                   % PRIVATE.relative_to(ROOT).as_posix())
    bad.extend(private_leaks([(f, author.get(f)) for f in PRIVATE_FIELDS],
                             public_text=public_text, run_git=run_git))

    # 5. The built page, not the file that was supposed to produce it.
    if title_text is None:
        title_text = docx_text(TITLE) if TITLE.exists() else None
    if title_text is None:
        bad.append('no built title page at %s, so its contents were not checked'
                   % TITLE.relative_to(ROOT).as_posix())
    else:
        flat = ' '.join(title_text.split())
        for field in REQUIRED:
            value = str(author.get(field) or '').strip()
            if value and ' '.join(value.split()) not in flat:
                bad.append('the built title page does not carry the %s' % field)
    return bad


def selftest():
    live = load_author()
    src = sources()
    public_text = PUBLIC.read_text(encoding='utf-8')
    title = docx_text(TITLE) if TITLE.exists() else None
    cr = crossref_affiliations(live['orcid'])
    LIVE = {'author': live, 'src': src, 'title_text': title,
            'private_present': True, 'public_text': public_text}

    def whole(**kw):
        for k, v in LIVE.items():
            kw.setdefault(k, v)
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
    planted_src = dict(src)
    planted_src['build_submission_docs.py'] = (
        "_=%r\n" % live['affiliation'] + src['build_submission_docs.py'])
    thin_title = (title or '').replace(live['affiliation'], 'LISIT') if title else 'nothing'
    # The defect this rule exists for: the telephone put back into the tracked file.
    pasted = public_text.replace('"name":', '"telephone": "%s",\n  "name":'
                                 % live['telephone'], 1)
    withheld = dict(live, telephone='', street_address='')

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
        ('builder keeps its own affiliation', dict(src=planted_src),
         'contains the affiliation literally'),
        ('title page lost the affiliation', dict(title_text=thin_title),
         'does not carry the affiliation'),
        ('telephone pasted back into the tracked author file', dict(public_text=pasted),
         'is published with the repository'),
        ('the local contact file is gone', dict(private_present=False, author=withheld),
         'is missing, so the title page cannot carry'),
    ]
    ok = True
    # Negative control: once the two author-owned items are resolved and the page carries
    # them, the gate must go silent. A rule that can only ever complain is not a gate.
    phone = '+81-3-1234-5678'
    resolved = dict(live, telephone=phone, confirmed_by_author=True)
    quiet = whole(author=resolved, run_git=False,
                  title_text=(title or '') + ' Telephone: ' + phone)
    print('  %-8s %s' % ('SILENT' if not quiet else 'NOISY',
                         'author items resolved (negative control)'))
    if quiet:
        print('           -> %s' % quiet[0][:130])
    ok = ok and not quiet
    for name, kwargs, expect in cases:
        # NO-OP guard: a case that changed nothing proves nothing.
        changed = any(kwargs[k] != LIVE[k] for k in kwargs if k in LIVE)
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
              'built title page, with the private contact details outside the repository')
    return int(bool(bad))


if __name__ == '__main__':
    raise SystemExit(main())
