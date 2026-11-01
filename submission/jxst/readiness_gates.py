"""Which submission gates are still open, resolved from paper/readiness.json.

Two callers ask this: the conformance report, and the builder, which stamps a draft
warning onto the title page while anything is open. They must not answer it differently,
and the builder must not answer it from a hand-written list - it used to key that warning
on two fields of paper/author.json, so supplying the telephone silently removed a
sentence that also named the generative-AI disclosure and the data locator.

A gate records why it passed ("PASS - 36 references over 5193 body words, ..."), so the
test is the PASS word and not string equality. Exact equality once made every annotated
gate look pending.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / 'paper/readiness.json'


def pending_gates(readiness=None):
    if readiness is None:
        readiness = json.loads(READINESS.read_text(encoding='utf-8'))
    return [k for k, v in readiness.items() if not re.match(r'PASS\b', str(v))]
