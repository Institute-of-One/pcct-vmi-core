"""Re-pin paper/visual_review.json, and only for pages somebody says they opened.

The ledger records that a human looked at every page and pins the sha256 of what
they looked at. A rebuild changes those bytes, which is exactly when the recorded
PASS stops being true, and until now the repair was a hand edit of the JSON. A
hand edit can re-pin a page nobody reopened, and the file would look the same
afterwards.

So this refuses to do that. It re-pins only the artefacts named on the command
line, and it fails if an artefact changed on disk and was not named: the point of
the ledger is that the hashes below have been seen, so a hash can only be
replaced by the person who just saw the new one.

  python paper/record_visual_review.py --opened final-page-11.png final-title-1.png \\
      --note "the declaration paragraph and the DRAFT gate list"

``--reviewer`` and ``--date`` default to the recorded reviewer and today. The
previous entry is appended to ``previous_reviews`` so the history is not lost.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "paper/visual_review.json"
OUTPUT = ROOT / "submission/jxst/output"


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--opened",
        nargs="+",
        required=True,
        metavar="PAGE",
        help="the artefact file names that were opened at their current bytes",
    )
    ap.add_argument("--note", required=True, help="what was looked for and found")
    ap.add_argument("--reviewer", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument(
        "--dry-run", action="store_true", help="say what would change and stop"
    )
    args = ap.parse_args()

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    artifacts: dict[str, str] = review["artifacts"]
    by_name = {Path(rel.replace("\\", "/")).name: rel for rel in artifacts}

    # A page the build has started rendering is not in the ledger yet, and refusing it
    # here would leave the hand edit as the only way to extend the review - which is the
    # thing this module exists to replace. It may be added, but only by being named.
    added = []
    for name in args.opened:
        if name in by_name:
            continue
        candidate = OUTPUT / name
        if not candidate.exists():
            print("not an artefact in the ledger and not on disk: " + name)
            return 1
        rel = str(candidate.relative_to(ROOT)).replace("/", "\\")
        by_name[name] = rel
        artifacts[rel] = ""      # no recorded bytes yet; the loop below pins them
        added.append(rel)
    for rel in added:
        print("adding to the ledger: %s" % rel)

    changed, unchanged = {}, []
    for rel, recorded in artifacts.items():
        now = digest(ROOT / rel.replace("\\", "/"))
        if now is None:
            print("FAIL %s is missing; rebuild before recording a review" % rel)
            return 1
        if now != recorded:
            changed[rel] = now
        else:
            unchanged.append(rel)

    named = {by_name[n] for n in args.opened}
    unnamed = sorted(set(changed) - named)
    if unnamed:
        print(
            "FAIL these changed on disk and were not named as opened:\n  "
            + "\n  ".join(unnamed)
        )
        print("Open them, then name them. A hash nobody has seen is not a review.")
        return 1
    stale_claim = sorted(named - set(changed))
    for rel in stale_claim:
        print("note %s was named but has not changed since the last review" % rel)

    print(
        "re-pinning %d artefact(s); %d unchanged" % (len(changed), len(unchanged))
    )
    for rel, now in changed.items():
        print("  %s %s -> %s" % (rel, artifacts[rel][:8], now[:8]))
    if args.dry_run:
        return 0

    history = review.setdefault("previous_reviews", [])
    history.append(
        {
            "reviewer": review.get("reviewer"),
            "date": review.get("date"),
            "manuscript_pages": review.get("manuscript_pages"),
            "title_pages": review.get("title_pages"),
        }
    )
    if args.reviewer:
        review["reviewer"] = args.reviewer
    review["date"] = args.date or datetime.date.today().isoformat()
    review["findings"] = args.note
    review["reopened_in_this_pass"] = sorted(changed) or sorted(named)
    review["unchanged_pages_note"] = (
        "Every other pinned image is byte-identical to the one opened earlier, so the "
        "hashes below all cover pages that have been seen at these exact bytes."
    )
    artifacts.update(changed)
    REVIEW.write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("wrote %s" % REVIEW)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
