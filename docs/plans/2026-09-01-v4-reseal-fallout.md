# Fallout from the 2026-W01-nfl v4 re-seal

The Week 1 slate was legitimately re-sealed as commitment **v4** on
2026-09-01T23:28:44Z. The old root had every kickoff four hours early, because
nflverse publishes Eastern league-clock gametimes and `engine/adapters/nfl.py::
_kickoff` was labelling them UTC. That is fixed (commit `0f16972`) and the
re-seal is correct.

Four things downstream of the ledger did not move with it. Each is one commit.

---

## Fix 1 — /ledger published a root that contradicted its own linked file

Live `/ledger` showed root `438f3607…` (v3), sealed 2026-08-06, first kickoff
2026-09-09T20:20Z, and "2 earlier commitment(s)" — while
`/data/2026-W01-nfl.commitment.json`, the file the page links, served root
`bc4cfd1f…` (v4). v3 was missing from the superseded chain entirely.

On the one page whose only job is proving nothing was altered, that reads as
the signature of tampering.

`site/public/ledger.html` is generated from `data/ledger/` by
`scripts/build_site.py`. The generator was already right; the committed page was
stale. Fix: run the generator, commit its output. No hand-edit, no ledger edit.

## Fix 2 — the workflows that write data/ledger never rebuild the page built from it

Root cause of Fix 1, and it recurs on every seal and every grade until fixed.

- `seal.yml` "Commit once (the timestamp anchor)": `git add data/ledger data/pro site/public/data`
- `grade.yml` "Commit once": `git add site/public/data data/ledger`

Both write `data/ledger` and commit; neither runs `scripts/build_site.py`. So
each run publishes a stale `/ledger` and leaves the repo's own gate red
(`tests/test_build_site.py` and the gate's "site build is reproducible" step).

Fix: a build step immediately before each commit step, and the generated pages
folded into the same commit.

Two things checked rather than assumed:

- **Dependencies.** `build_site.py` imports `markdown`, and nothing else
  third-party (measured by importing it and listing the non-stdlib modules that
  loaded: `markdown` only). *Neither* workflow installed it — grade.yml has
  `requests pandas numpy cryptography`, seal.yml adds `scikit-learn`. So
  `markdown` is added to **both** pip lines, not just grade.yml's.
- **`git add` scope.** `build_site.py` writes exactly four files:
  `site/public/{methodology,verify,disclaimers,ledger}.html`. A glob
  `site/public/*.html` would sweep 20 hand-written pages that the generator does
  not own. The four are therefore named explicitly — narrow enough that no
  unrelated file can ride along, complete enough that whichever page the build
  touches is committed.

seal.yml keeps ONE commit: the timestamp anchor is the trust story, and the
regenerated page belongs inside it.

## Fix 4 — the Week 1 results email was permanently suppressed

`data/lifecycle_sent.json` already held `graded:2026-W01-nfl`, but
`site/public/data/pickengine-record.json` reports `n_settled: 0` for that week —
Week 1 has not been played (first kickoff 2026-09-10).

`engine/alert_lifecycle.py::graded_content` returns content for any non-rehearsal
week regardless of `n_settled`, so it was willing to announce a week with
"games settled: 0". The watermark burns on both the zero-recipient path and the
successful-send path, so once burned, the real results email can never send:
the run would print `already announced graded:2026-W01-nfl — not re-sending`.

Fix, two parts:

1. **Root.** `graded_content` returns `None` when the newest live week has no
   settled games. Guarding the newest week (rather than skipping forward to the
   newest *settled* week) is deliberate: grade.yml always announces the week it
   just graded, so the newest week is the subject, and failing closed can never
   mail the wrong week's record.
2. **Damage.** Remove the false `graded:2026-W01-nfl` key from the watermark.
   `seal:2026-W01-nfl` stays — that announcement genuinely went out today.

The check goes into the module's existing `_selfcheck()`, which the gate runs
via `tests/`.

## Fix 3 — /verify's worked walkthrough no longer reproduces

Approved separately, sequenced last. `site/content/verify.md` hand-types every
figure in its walkthrough, and after the v4 re-seal each disagrees with the files
the page tells the reader to download. The algorithm is correct — verified by
running the page's own script against the live v4 pair: 32/32 VERIFIED. Only the
printed values are stale, and the inclusion-proof example is two versions stale
(v1, 16 predictions, four proof steps; the live slate is 32, so five).

Hard rule 5 applies: no published number is ever hand-typed. These are wired to
the `{{fig:...}}` substitution in `build_site.py` via a new `slate_figures()`,
which resolves them from `data/ledger/` at build time. No change to
`scripts/published_figures.py` and no change to `_figures.json` — the `slate`
namespace is merged in alongside it, so regenerating backtests was not needed
and no unrelated value churned.

`slate_figures()` recomputes rather than reads: the leaf hashes, the root, the
inclusion proof and the tampered root are all derived from the published
predictions on every build, and it raises rather than publish a figure it cannot
verify. Three of its checks are the ones this whole session was about — the
recomputed leaves must equal the published ones, the recomputed root must equal
the committed root, and the commitment the site *serves* must be the ledger's
latest. That last one is the Fix 1 defect, now caught at build time.

Measured, not assumed: the canonical string is **296** characters, not the 281
the page claimed, and the proof is **five** steps for a 32-prediction tree, not
four.

### The trap to know about

`data/ledger/2026-W01-nfl.commitment.json` and `.reveal.json` — the
**unversioned** files — are stale at **v2** (root `4136512c…`). Only the
`*.v4.json` pair is current. Anything reading the unversioned names gets a root
two seals old. `build_ledger()` and `slate_figures()` both go through
`commitment_history()`, which globs `*.commitment.v*.json`, so both are correct;
the unversioned files are a legacy fallback. Left alone under hard rule 2 (never
hand-edit `data/ledger/`) — flagged for Branden.

---

## Verification standard for all four

`bash scripts/check.sh` must print `green` on its last line before any push,
read bare — not through a pipe, which returns the pipe's status. After each
push, `curl` the live URL and confirm the specific value changed.

---

## Found, not fixed — for Branden

1. **`engine/alert_lifecycle.py` cannot run its own selfcheck on Windows.**
   `_when()` formats with `%-d`, a glibc extension; MSVC's `strftime` raises
   `ValueError: Invalid format string`. Pre-existing, and harmless in production
   (the workflows run on ubuntu). But it means `python -m engine.alert_lifecycle
   --selfcheck`, which docs/alerts-runbook.md tells you to run, dies on your
   machine before reaching any assertion. Fixing it changes the date text in a
   published email ("Sep 9" vs "Sep 09"), so it was left for a decision.

2. **The unversioned `data/ledger/2026-W01-nfl.{commitment,reveal}.json` are
   stale at v2.** See above. Nothing currently reads them, but the next thing
   that does will read a root two seals old.
