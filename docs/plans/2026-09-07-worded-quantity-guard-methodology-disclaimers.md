# Extend the worded-quantity guard to /methodology and /disclaimers

*Unattended session, 2026-09-07. Closes the gap flagged in
`docs/plans/2026-09-03-unguarded-quantities.md`, "One thing to know before
extending the worded guard".*

## Starting state

Pulled `origin/main`, HEAD landed at `a24244e7` (capture bots ahead of the
`f1215308` in memory). Gate green before touching anything.

The worded-quantity guard (`test_no_worded_quantities_left_in_the_prose` in
`tests/test_props_model_note.py`) only covered `/props-model`. It was never
pointed at `/methodology` or `/disclaimers` because its fraction pattern
false-positives on **"a third party"** — both pages use that phrase several
times to mean an outside company, and the pattern's `_FRAC` group matches
"third" as a fraction regardless of what follows it.

## What changed

1. **Fixed the false positive.** The fraction pattern
   `\b(?:a|one|N)[\s-]FRAC\b` now carries a negative lookahead,
   `(?!\s*-?\s*part(?:y|ies)\b)`, so "a third party" / "a third-party X" no
   longer matches while "a third of the votes" still does. Verified: scanning
   `/methodology` and `/disclaimers` with the fix in place produces zero
   "third party" false positives and a short, reviewable list of real worded
   quantities.

2. **Extracted the shared regex list.** `tests/_worded_quantities.py` is new —
   `WORDED_PATTERNS`, `worded_quantities()`, and a `visible_text()` helper for
   stripping markup between two markers. `test_props_model_note.py` now
   imports from it instead of carrying its own copy. Reason: a second copy of
   this regex list is exactly the kind of thing this repo has already been
   burned by keeping in sync by hand (`site/public/data/figures.json` sat 19
   days stale for the same reason).

3. **New guard: `tests/test_worded_quantities_prose_pages.py`.** Same
   discipline as the /props-model guard — every worded quantity in the
   rendered page's prose must be on a reviewed allowlist with a reason, or the
   test fails naming it. Covers `/methodology` and `/disclaimers`.

## The audit — every phrase the fixed pattern found, read against the page

`/methodology` (12 phrases, all checked 2026-09-07 against
`site/content/_figures.json` and the engine code):

- "two things" / "two evaluations" / "two honest [notes]" / "two facts" /
  "two line [sources]" — each is a count the surrounding sentence names or the
  immediate section structure shows (two numbered claims, sections A and B,
  "First... Second...", the two gap figures in the previous sentence, nflverse
  vs. the real consensus close).
- "four sports" — names all four (college football, MLB, NBA, NHL) in the
  same sentence.
- "four hashes" — log2(16) for the 16-game slate the sentence names.
- "four of [ten seasons]" and "ten seasons" (two occurrences) — checked by a
  new test against `_figures.json`: `by_season` has exactly 10 entries and
  exactly 4 have `pct < 0.5`.
- "five [this... one game in five]" — checked against
  `selectivity.evaluation_a.live.per_season` (52.3) over
  `thresholds[0].all.per_season` (260.8) = 20.05%, i.e. 1 in ~5.0.
- "four point [bar]" — already tracked by
  `test_the_edge_bar_is_spelled_the_same_way_in_the_copy` in
  `tests/test_figures_published.py`.
- "ten probability [bands]" — checked against
  `engine.calibrate.expected_calibration_error`'s default `bins=10`.

`/disclaimers` (2 phrases):

- "nine disclosures" — the page's own numbered sections run 1 through 9.
- "seven days [a week]" — "24 hours a day, seven days a week", the stated
  hours of an external gambling hotline. Not a measurement of anything Sooth
  does.

Nothing was wrong. This closes a gap in coverage, not a live defect.

## Deliberately not touched

- `picks.html:225`, "a card that plays a third of the games" — already noted
  in the 2026-09-03 plan as describing a competitor, not a Sooth measurement.
  Out of scope for this pass (only /methodology and /disclaimers were asked
  for); the new pattern would no longer false-positive on it if someone wants
  to wire a guard there next.
- The spread-play-outside-the-Merkle-commitment item, `seal.yml`, and
  `WINDOW_THROUGH` — untouched per standing instructions.

## Read-only sweep of other hand-written pages (no guard added, no defect found)

With the fixed pattern in hand, ran it (read-only, nothing committed to a
guard) over the other hand-written public pages —
`trust/record/engine/predictor/index/picks/learn/props/verify/ledger.html` —
to check for a live wrong-figure defect before treating this as done for the
day. Every hit found reads correctly against its own immediate context:

- `record.html`: "three samples" / "three models" — section headers ("THE
  THREE SAMPLES", "THE THREE MODELS") that name what follows.
- `picks.html`: "a third [of the games]" — already noted in
  `docs/plans/2026-09-03-unguarded-quantities.md` as describing a competitor,
  not a Sooth measurement; "four points [of disagreement]" — already pinned
  by `test_the_edge_bar_is_the_same_number_in_all_three_places` in
  `tests/test_figures_published.py`.
- `learn.html`: "two even [sides at -110 each]" — definitional, explaining
  vig, not a measurement.
- `props.html`: "two books" — definitional (an arbitrage example); "three or
  [more books]" — the board filter, matches `method.board_filter` already
  tracked in `tests/test_props_model_note.py`; "ten games" — "his last ten
  games", a UI label matching `/props`'s own last-N display, already reviewed
  as "five last"/"ten and" on /props-model.
- `verify.html`: "two files" (×2), "two roots", "two child [hashes]" — all
  self-evident from the two sentences around them (the walkthrough literally
  names both files/roots/hashes it means).

No new guard added for these pages — that would be a larger, separate
decision (whether every hand-written page gets the exhaustive treatment, per
the tradeoff `2026-09-03-unguarded-quantities.md` already discusses), not
something to do unattended. Recorded here so the next sweep does not
re-derive it from zero.

## W02 health check (read-only, nothing sealed)

Also ran `PYTHONPATH=. python scripts/slate_probe.py --season 2026 --week 2
--mocks` ahead of W02's seal (due the Wednesday after 2026-09-09). Read-only:
the script fingerprints the real `data/ledger` before and after and aborts if
it moved — it reported `real data/ledger unchanged` — and the four
`_mock-w02*.json` fixtures it writes are gitignored; deleted them after.

Confirms the spread-in-commitment fix (`bc47f6bc`, 2026-09-04) produces the
predicted shape for W02: **48 sealed predictions**, up from 32, matching
`docs/plans/2026-09-04-spread-in-commitment.md`'s "2 moneyline + 1 spread per
game with a line, 16 games". The qualified play and the two next-widest edges
are identical to the 2026-09-03 dry run down to the last decimal (CIN at HOU,
line 2.5, edge +4.35), so the pipeline is stable going into the seal. Not
sealed, not touched further — sealing stays Branden's to run via
`.github/workflows/seal.yml`.

## Verification

- `PYTHONPATH=. python -m pytest tests/test_props_model_note.py tests/test_worded_quantities_prose_pages.py -q`
  → 11 passed.
- `bash scripts/check.sh` → `green` (includes the full suite, the JS
  selfchecks, and a reproducible site build). `git status --short` after the
  run showed no rewritten `site/public/` output beyond this change's own
  files — the build did not need to regenerate anything.
