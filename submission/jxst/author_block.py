"""The author block, split by what may be published.

`paper/author.json` is a tracked file, and from 2026-11-02 this repository is public:
the version archive the manuscript's data-availability statement cites is this
repository, so every byte of that file is published and stays in the history even if a
later commit removes it. Sage needs the corresponding author's telephone number and
institutional street address on the title page, and a journal office is not the public.

So the two private fields live in `paper/author_contact.local.json`, which `.gitignore`
keeps out of the repository, and this module merges them for the builder and the gate.
Only the fields named in `PRIVATE_FIELDS` are taken from the local file: a local file
that could override the affiliation would be a second copy of the one string AGENTS.md
section 2 requires to be resolved against Crossref rather than remembered.

A reader who clones the public repository has no local file. The title page then builds
with `[PENDING]` in those two lines and `check_author_identity.py` reports the file as
missing, which is the honest outcome - the contact details are the author's to supply,
not the archive's to carry.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'paper/author.json'
PRIVATE = ROOT / 'paper/author_contact.local.json'
PRIVATE_FIELDS = ('street_address', 'telephone')


def load_private(private=None):
    """The local contact file, or an empty mapping when it is not there."""
    if private is not None:
        return dict(private)
    if not PRIVATE.exists():
        return {}
    return json.loads(PRIVATE.read_text(encoding='utf-8'))


def load_author(public=None, private=None):
    """The published author block with the private contact fields merged in.

    Missing private fields come back as empty strings rather than absent keys, so a
    caller that formats the title page does not have to know which fields are held
    outside the repository.
    """
    merged = (json.loads(PUBLIC.read_text(encoding='utf-8'))
              if public is None else dict(public))
    local = load_private(private)
    for field in PRIVATE_FIELDS:
        merged[field] = str(local.get(field) or '').strip()
    return merged
