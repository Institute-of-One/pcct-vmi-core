"""The archived release: one version in every file, and no DOI that was not minted.

The manuscript's data-availability statement cites a Zenodo record of this repository.
AGENTS.md section 5 counts eight places that restate the version, the release date or
the DOI; `paper/release.json` holds them once and this gate checks that the eight agree.
It checks, it does not fix: a gate that rewrites the files it reads cannot disagree
with them.

What it is here to catch, each learned from a lost round:

* the archived version disagrees with the code that produced the numbers. Zenodo records
  the version from the `.zenodo.json` of the commit the release points at and **cannot
  correct it after publication**.
* a top-level `doi` in `.zenodo.json`, which stops Zenodo minting a version DOI at all.
* the concept DOI reaching the manuscript. It resolves, it belongs to this software, and
  it is the wrong identifier: it follows the newest release, so the article would stop
  citing the version it was built from. No other check sees this.
* an affiliation string that differs by a postcode from the one Crossref carries. One
  author with two strings reads as two organisations to an affiliation matcher.
* a description in `CITATION.cff` that still calls an older version "the release used
  in" this work. Raising the version makes that sentence false and nothing else reads it.
* a repository URL that is not the repository this checkout pushes to.

Run --selftest to prove the rules fire: each planted defect must add a finding that the
live sources do not already produce.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / 'paper/release.json'
BUILT = ROOT / 'submission/jxst/output/manuscript.txt'
FILES = ('pcctvmi/__init__.py', 'pyproject.toml', 'CITATION.cff', '.zenodo.json',
         'README.md', 'paper/author.json', 'paper/references.json')
DOI = re.compile(r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+')


def dois(text):
    """Every DOI in the text, without the punctuation that ends the sentence.

    The DOI syntax allows a dot, so a DOI at the end of a sentence comes back with the
    full stop attached and compares unequal to the same DOI in a JSON field.
    """
    return {m.rstrip('.,;:)') for m in DOI.findall(text)}


def sources():
    return {name: (ROOT / name).read_text(encoding='utf-8') for name in FILES}


def load_release():
    return json.loads(RELEASE.read_text(encoding='utf-8'))


def doi_resolves(doi):
    """True when doi.org has a record for this identifier.

    A DOI is a claim about a record that exists somewhere else, so it is resolved rather
    than pattern-matched. A network failure raises: a gate that cannot reach its evidence
    must say so, not quietly agree with the file it was checking.
    """
    req = urllib.request.Request('https://doi.org/' + doi, method='HEAD', headers={
        'User-Agent': 'IoO-submission-gate/1.0 (mailto:yamamoto@lisit.jp)'})
    try:
        urllib.request.urlopen(req, timeout=60)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return False
        raise


def git_remote():
    """The push URL of origin, or None when there is no remote yet."""
    try:
        r = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=60)
    except OSError:
        return None
    return r.stdout.strip() or None


def _canon(url):
    return (url or '').strip().rstrip('/').removesuffix('.git')


def check(release=None, files=None, built=None, resolve=None, remote=None,
          check_remote=True):
    release = load_release() if release is None else release
    files = sources() if files is None else files
    resolve = doi_resolves if resolve is None else resolve
    bad = []
    version = str(release.get('version') or '').strip()
    tag = str(release.get('tag') or '').strip()
    if not version:
        bad.append('paper/release.json names no version, so nothing can be compared with it')
        return bad
    zen = json.loads(files['.zenodo.json'])
    cff = files['CITATION.cff']

    # 1. One version. Zenodo archives one, and cannot be corrected after publication.
    found = {
        'pcctvmi/__init__.py': re.search(r'^__version__ = "(.*?)"$',
                                         files['pcctvmi/__init__.py'], re.M),
        'pyproject.toml': re.search(r'^version = "(.*?)"$', files['pyproject.toml'], re.M),
        'CITATION.cff': re.search(r'^version: (.*)$', cff, re.M),
    }
    for name, m in found.items():
        got = m.group(1).strip().strip('"') if m else None
        if got != version:
            bad.append('%s declares version %r; paper/release.json says %r'
                       % (name, got, version))
    if str(zen.get('version') or '') != version:
        bad.append('.zenodo.json declares version %r; paper/release.json says %r. Zenodo '
                   'reads this file from the commit the release points at and the '
                   'published record cannot be corrected'
                   % (zen.get('version'), version))
    if tag != 'v' + version:
        bad.append('the tag %r is not v%s, so the archived release and the version it '
                   'claims cannot be matched up by name' % (tag, version))

    # 2. The release date, which CITATION.cff states and a reader believes.
    want_date = str(release.get('date_released') or '').strip()
    m = re.search(r'^date-released: "?(\d{4}-\d{2}-\d{2})"?$', cff, re.M)
    if not m:
        bad.append('CITATION.cff has no date-released; it is the day the tag is cut')
    elif want_date and m.group(1) != want_date:
        bad.append('CITATION.cff date-released is %s; paper/release.json says %s'
                   % (m.group(1), want_date))

    # 3. A top-level doi in .zenodo.json stops Zenodo minting a version DOI.
    if 'doi' in zen:
        bad.append('.zenodo.json has a top-level "doi". Zenodo then stops issuing a '
                   'version DOI for each release, and the manuscript cites the version DOI')

    # 4. One affiliation string, and one ORCID, resolved from paper/author.json.
    author = json.loads(files['paper/author.json'])
    affiliation = str(author.get('affiliation') or '').strip()
    orcid = str(author.get('orcid') or '').strip()
    creators = zen.get('creators') or [{}]
    if str(creators[0].get('affiliation') or '').strip() != affiliation:
        bad.append('.zenodo.json gives the affiliation as %r; paper/author.json, checked '
                   'against Crossref, has %r. DataCite metadata is what an affiliation '
                   'matcher reads, and two strings read as two organisations'
                   % (creators[0].get('affiliation'), affiliation))
    if affiliation and ('affiliation: "%s"' % affiliation) not in cff:
        bad.append('CITATION.cff does not carry the affiliation from paper/author.json (%r)'
                   % affiliation)
    if orcid and orcid not in cff:
        bad.append('CITATION.cff does not carry ORCID %s' % orcid)
    if orcid and orcid not in json.dumps(zen):
        bad.append('.zenodo.json does not carry ORCID %s' % orcid)

    # 5. One repository URL, and it is the one this checkout pushes to.
    repo = _canon(release.get('repository'))
    if not repo:
        bad.append('paper/release.json names no repository, so the manuscript has no '
                   'public code locator')
    else:
        m = re.search(r'^repository-code: "(.*?)"$', cff, re.M)
        if _canon(m.group(1) if m else None) != repo:
            bad.append('CITATION.cff repository-code is %r; paper/release.json says %r'
                       % (m.group(1) if m else None, release.get('repository')))
        if repo not in json.dumps(zen):
            bad.append('.zenodo.json does not relate the record to %r' % release['repository'])
        if check_remote:
            if remote is None:
                remote = git_remote()
            if not remote:
                bad.append('this checkout has no git remote named origin, so %r is not a '
                           'locator anything was pushed to' % release['repository'])
            elif _canon(remote) != repo:
                bad.append('origin is %r but paper/release.json names %r; the archive '
                           'would be cut from a different repository than the manuscript '
                           'cites' % (remote, release['repository']))

    # 6. The two DOIs: minted, distinct, and each resolving.
    version_doi = release.get('version_doi')
    concept_doi = release.get('concept_doi')
    for field, value in (('version_doi', version_doi), ('concept_doi', concept_doi)):
        if value is None:
            continue
        if not DOI.fullmatch(str(value)):
            bad.append('%s %r is not a DOI. Nothing may fill these in except the archive '
                       'that mints them' % (field, value))
        elif not resolve(value):
            bad.append('%s %s does not resolve through doi.org' % (field, value))
    if version_doi and version_doi == concept_doi:
        bad.append('version_doi and concept_doi are the same identifier. The concept DOI '
                   'follows the newest release, so the article would stop citing the '
                   'version it was built from')

    # 7. CITATION.cff lists both, and no description still names a retired version.
    for field, value in (('concept DOI', concept_doi), ('version DOI', version_doi)):
        if value and value not in cff:
            bad.append('CITATION.cff does not list the %s (%s)' % (field, value))
    for stated in re.findall(r'^\s*description: "[^"]*?(\d+\.\d+\.\d+)[^"]*"\s*$', cff, re.M):
        if stated != version:
            bad.append('CITATION.cff describes an identifier as belonging to version %s, '
                       'but this release is %s. Raising the version makes that sentence '
                       'false and nothing else reads it' % (stated, version))

    # 8. The README badge advertises the concept DOI, not the version.
    readme_records = set(re.findall(r'zenodo\.(\d+)', files['README.md']))
    if concept_doi:
        if concept_doi.rsplit('.', 1)[-1] not in readme_records:
            bad.append('README.md does not carry the concept DOI badge (%s), which is the '
                       'one that keeps resolving as versions are added' % concept_doi)
        if version_doi and version_doi.rsplit('.', 1)[-1] in readme_records:
            bad.append('README.md carries the version DOI. The badge is the concept DOI; '
                       'the manuscript cites the version')

    # 9. The built document, not the source that was supposed to produce it.
    if built is None:
        built = BUILT.read_text(encoding='utf-8') if BUILT.exists() else None
    if built is None:
        bad.append('no built manuscript at %s, so the data-availability statement was '
                   'not read back' % BUILT.relative_to(ROOT).as_posix())
    else:
        flat = ' '.join(built.split())
        if repo and release['repository'] not in flat:
            bad.append('the built manuscript does not carry the repository URL')
        for token in ('{{RELEASE', 'PENDING', 'TODO', 'FIXME', 'XXXX'):
            if token in flat:
                bad.append('the built manuscript contains %r. A token reads as filled in '
                           'at a glance, which is how it survives into a submitted PDF'
                           % token)
        if version_doi and version_doi not in flat:
            bad.append('the built manuscript does not carry the version DOI %s' % version_doi)
        if concept_doi and concept_doi != version_doi and concept_doi in flat:
            bad.append('the built manuscript carries the concept DOI %s; it must cite the '
                       'version DOI of the release it was built from' % concept_doi)
        known = dois(files['paper/references.json']) | {version_doi}
        stray = {d for d in dois(flat) if 'zenodo' in d} - known
        if stray:
            bad.append('the built manuscript cites Zenodo record(s) %s that are neither '
                       'this release nor anything in the reference list'
                       % ', '.join(sorted(stray)))
    return bad


def selftest():
    live_release = load_release()
    live_files = sources()
    live_built = BUILT.read_text(encoding='utf-8') if BUILT.exists() else None
    live_remote = git_remote()
    LIVE = {'release': live_release, 'files': live_files, 'built': live_built,
            'remote': live_remote}

    def whole(**kw):
        for k, v in LIVE.items():
            kw.setdefault(k, v)
        return check(**kw)

    # What the live sources already report. A planted defect counts only if it adds to
    # this; without the subtraction one unrelated live failure makes every case pass.
    baseline = whole()
    print('baseline (the live sources, %d finding(s)):' % len(baseline))
    for b in baseline:
        print('   - %s' % b[:140])

    version = live_release['version']
    repo = live_release['repository']
    minted = '10.5281/zenodo.11111111'
    concept = '10.5281/zenodo.22222222'
    # A release that is complete and consistent, to prove the gate can go silent.
    good_release = dict(live_release, version_doi=minted, concept_doi=concept)
    good_files = dict(live_files)
    good_files['CITATION.cff'] = (live_files['CITATION.cff']
                                  + '\nidentifiers:\n  - type: doi\n    value: "%s"\n'
                                    '    description: "Concept DOI (resolves to the latest '
                                    'version)"\n  - type: doi\n    value: "%s"\n'
                                    '    description: "Version DOI of the %s release"\n'
                                  % (concept, minted, version))
    good_files['README.md'] = live_files['README.md'] + '\n[![DOI](https://zenodo.org/badge/DOI/%s.svg)](https://doi.org/%s)\n' % (concept, concept)
    good_built = '%s %s see https://doi.org/%s' % (live_built or '', repo, minted)
    always_true = lambda doi: True
    quiet = check(release=good_release, files=good_files, built=good_built,
                  resolve=always_true, remote=repo)
    print('  %-8s %s' % ('SILENT' if not quiet else 'NOISY',
                         'a minted, consistent release (negative control)'))
    for q in quiet:
        print('           -> %s' % q[:130])

    def patch(name, old, new):
        out = dict(good_files)
        assert old in out[name], (name, old)
        out[name] = out[name].replace(old, new, 1)
        return out

    cases = [
        ('one file left on the old version',
         dict(files=patch('pcctvmi/__init__.py', '__version__ = "%s"' % version,
                          '__version__ = "0.0.9"')),
         'declares version'),
        ('.zenodo.json left on the old version',
         dict(files=patch('.zenodo.json', '"version": "%s"' % version,
                          '"version": "0.0.9"')),
         '.zenodo.json declares version'),
        ('tag does not match the version',
         dict(release=dict(good_release, tag='v0.0.9')), 'is not v%s' % version),
        ('date-released removed',
         dict(files=patch('CITATION.cff', 'date-released:', 'date_released_was:')),
         'no date-released'),
        ('a top-level doi in .zenodo.json',
         dict(files=patch('.zenodo.json', '"title":', '"doi": "%s",\n  "title":' % concept)),
         'stops issuing a version DOI'),
        ('postcode dropped from the Zenodo affiliation',
         dict(files=patch('.zenodo.json', 'LISIT Co., Ltd., Tokyo 150-0044, Japan',
                          'LISIT Co., Ltd., Tokyo, Japan')),
         'affiliation matcher reads'),
        ('concept DOI used as the version DOI',
         dict(release=dict(good_release, version_doi=concept)),
         'same identifier'),
        ('a DOI that does not resolve',
         dict(resolve=lambda doi: doi != minted), 'does not resolve through doi.org'),
        ('the manuscript cites the concept DOI',
         dict(built=good_built + ' and https://doi.org/' + concept),
         'carries the concept DOI'),
        ('the manuscript lost the repository URL',
         dict(built=(good_built or '').replace(repo, 'the project repository')),
         'does not carry the repository URL'),
        ('a placeholder survived into the document',
         dict(built=good_built + ' DOI: PENDING'), 'reads as filled in at a glance'),
        ('CITATION.cff still describes the previous version',
         dict(files=patch('CITATION.cff', 'Version DOI of the %s release' % version,
                          'Version DOI of the 0.0.9 release')),
         'belonging to version 0.0.9'),
        ('README badge carries the version DOI',
         dict(files=patch('README.md', 'badge/DOI/%s' % concept,
                          'badge/DOI/%s' % minted)),
         'README.md carries the version DOI'),
        ('no remote to push to', dict(remote='', check_remote=True),
         'no git remote named origin'),
        ('origin is a different repository',
         dict(remote='https://github.com/someone-else/pcct-vmi-core'),
         'would be cut from a different repository'),
    ]
    GOOD = {'release': good_release, 'files': good_files, 'built': good_built,
            'resolve': always_true, 'remote': repo}
    ok = not quiet
    for name, kwargs, expect in cases:
        # NO-OP guard: a case that changed nothing proves nothing. Every input the cases
        # can plant is in GOOD, including the resolver - a case that only replaces the
        # resolver did change something, and leaving it out of the guard made a detected
        # case count as a no-op.
        changed = any(kwargs[k] != GOOD[k] for k in kwargs if k in GOOD)
        for key, value in GOOD.items():
            kwargs.setdefault(key, value)
        found = [f for f in check(**kwargs) if f not in quiet]
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
        print('OK   release metadata: one version in every file, the repository this '
              'checkout pushes to, and the minted DOIs in the places that take them')
    return int(bool(bad))


if __name__ == '__main__':
    raise SystemExit(main())
