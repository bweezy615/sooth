# The CLV the site said it did not publish

Written 2026-08-28 by the supervisor agent.

## What was wrong

/disclaimers §7 carried this, in bold, from the initial commit on 2026-08-02:

> **We do not currently publish a closing-line-value figure.** Our historical
> line data comes from a source that overwrites line values in place as the
> market moves, which makes any CLV number computed from it unreliable. We will
> publish CLV when we can validate it against an independent source with
> explicit opening and closing records, and not before.

On 2026-08-06 the launch build shipped a **CLV checker** on /tools. Typing
`+150` into it on the live site right now returns:

> Consensus close: −440 · fair 78.1%
> Your +150 vs close: **+41.48 pts** — you beat the close.

That is a closing-line-value figure, published, on a page linked from the nav.
`desk.js` also renders per-pick CLV chips on /picks and /trust, and /record
prints `mean_clv` per model. The statement had been false for twenty-two days,
on the page a skeptical reader opens to check whether we can be trusted.

The promise underneath it was in fact **kept**. The condition was "an
independent source with explicit opening and closing records", and that is
exactly what was bought: timestamped closing snapshots, 5–28 minutes before
kickoff, provenance `oddsapi_historical_close`. `engine/grade.py` enforces it —
CLV is computed only where the close carries `own_capture` or
`oddsapi_historical_close` provenance, and otherwise publishes
`clv_blocked_reason` in place of a number. The discipline was implemented and
the sentence describing it was never updated. Classic "changing the model
changes the copy", on the compliance page.

## The second half: an archive nobody could rebuild

`site/public/data/clv-nfl.json` is the 104 KB payload the checker compares
against. It was committed once, by hand, in that same 2026-08-06 launch build.
**No generator existed anywhere in the repository.** Nothing could rebuild it,
nothing could check it, and a season added to `data/backfill/` would never have
reached it.

It was, as it happens, correct. Rebuilding it from `data/backfill/` reproduces
**all 855 games — every closing price, every de-vigged fair probability, every
date — exactly.** That was luck. Two things had to be got right by hand and
were: the consensus is the median of the implied *probabilities* converted back
to American odds, not the median of the American prices (16 of the 855 games sit
close enough to even money that the difference shows), and the de-vig matches
`engine.schema.devig` to four places.

One thing was not right. /tools described the archive as "the consensus close
across 10–16 books". The real moneyline range is **7 to 16**, median 11 — twelve
games sit below the published floor.

## The fix

- `scripts/clv_archive.py` rebuilds the archive from the backfill and is now the
  only way it is written. It adds `nb`, the book count per game, and derives its
  own `note` from the data rather than restating a remembered range.
- /tools stops quoting a range. The panel states the span and count of the
  archive from the file, and each answer says "median of N books" for the game
  actually selected.
- /disclaimers §7 says what the site does: CLV only against closes we hold, none
  from the free overwritten source, and the reason published where there is no
  qualifying close.
- `tests/test_clv_archive.py` fails if the published archive stops matching the
  backfill, if its note stops matching its contents, if the page re-types a book
  range, or if the disclaimer goes back to denying the feature.

## Flagged for Branden, not changed

**This edits compliance copy.** The bullet was corrected rather than removed,
nothing protective was weakened, and the underlying discipline is unchanged and
still enforced in `grade.py`. But it is a legal-adjacent page and the wording
may have been chosen deliberately, so read the new bullet and tell me if you
want it phrased differently. Leaving a false statement there was not an option;
choosing the replacement wording is yours.
