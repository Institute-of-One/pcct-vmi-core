# The author's decision on the review requirement — 2026-11-24

The IoO Publication Policy v1 requires three independent reviews — Claude Code, Codex
and ChatGPT — on one fixed snapshot, plus the author's own approval tied to the SHA-256
of all three, before a manuscript is submitted. For IORN-016 that requirement is **not
met**, and this file records why, who decided, and what exists in its place. It is not
an approval record. `publication/reviews/human.json` is deliberately absent: the gate's
human approval is defined as being bound to three reviews, and binding it to one would
be a false statement in a file whose only purpose is to be believed.

## What exists

- **An independent ChatGPT review**, obtained on 2026-11-24 over seven rounds against
  the snapshots pinned by `publication/publication_gate.py`. The final record is
  `publication/reviews/chatgpt.json`, stored byte-identical to the reviewer's output and
  checked against a SHA-256 computed in the browser. Its decision is `blocked`, five of
  its six checks pass, and its own `unresolved` list states that the Codex and Claude
  reviews are absent. It found four real defects, three of them introduced the same day;
  all four were fixed and the fixes were re-reviewed. `docs/MANUSCRIPT_STATUS.md` lists
  them.
- **The author's page-by-page inspection**, recorded separately in
  `paper/readiness.json` under `author_visual_approval`, and the machine page review in
  `paper/visual_review.json`, which pins the sha256 of all 22 rendered pages.
- **The writing side.** The manuscript was drafted and revised with Claude Code working
  under the author's direction, which is disclosed in the article's Declaration of
  generative AI use. That is not an independent review of itself and is not counted as
  one here.

## What does not exist

- **No Codex review of this snapshot.** None was requested and none was performed.
- **No separate Claude Code review of this snapshot.** The Claude Code session that
  wrote the manuscript cannot review itself, and the author did not ask for a fresh
  session to do so.
- **No human approval record in the gate's format**, for the reason given above.

Nobody may describe this article as having passed a three-reviewer gate. Running
`python publication/publication_gate.py publication.json` will continue to exit non-zero
and say which reviews are missing. That is the correct output and it is not to be
suppressed, routed around, or wired out of the build.

## The decision

On 2026-11-24, after being shown the state of both open gates and the three options —
obtain the two missing reviews, record a reasoned exception and close the gates, or hold
the submission — the author chose the second. In his words:

> (b)で記録して門を閉じて、投稿準備を完成させて。論文は、CodeingしたClaude利用だけでいいよ。

So: the two readiness gates that stamp `DRAFT` on the title page are closed on his
instruction and with his reason, the submission proceeds, and the shortfall against the
policy is written down here rather than papered over. `research_end_to_end_reexecution`
is closed on the same instruction; what it records — that nothing downstream of training
reproduces bit-for-bit — is unchanged, is measured, and is stated in Section 2.3 of the
article itself, where a reader meets it.

The decision is his to make and is his alone. It applies to IORN-016 at this submission
and sets no precedent for the next manuscript.
