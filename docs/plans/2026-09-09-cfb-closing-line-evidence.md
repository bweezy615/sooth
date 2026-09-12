# College football cannot be graded yet — but it is closer than it looks

*Measured 2026-09-09 against `data/capture/ncaaf/`, 2026-08-28 onward, with
`scripts/capture_closeness.py`. No engine code changed as a result. This exists
so the next person does not wire the capture in and get a backtest that
flatters us — and so they do not write the sport off either.*

## The question

`engine/adapters/ncaaf.py` returns `[]` from `load_historical_lines`, because
its source (the cfbfastR schedule mirror) carries no odds. HANDOFF §9 therefore
has college football as board only, not Live.

The obvious next move is to close that gap with evidence we already own.
`data/capture/ncaaf/` has been filling since 2026-08-28, its rows carry
`provenance: own_capture` — which HANDOFF §4.3 says may back a published CLV
figure — and its `event_id` is ESPN's, the same id `NCAAFAdapter` emits, so the
join needs no team-name bridge. Everything about that looks ready.

## Measure only the games that have been played

The first pass of this measurement scored every event we hold an observation
for, and reported a median gap of 85 minutes and a p75 of 3,294 — a quarter of
the slate apparently two days stale. **Those numbers were wrong**, and wrong in
a way worth recording because it is easy to repeat.

For a game still days away, "minutes from our last observation to kickoff"
measures how far away the game is, not how close we managed to get. We have not
had the chance to observe it near kickoff yet. Including unplayed events makes
any capture look arbitrarily bad the further ahead the schedule is published —
it put the NFL at a 15,864-minute median while its week 1 had not been played.

Scoring only events that have actually kicked off:

```
197 of 268 observed events had been played

min 2 | p25 28 | median 55 | p75 99 | p90 128 | max 1015   (minutes)

within  15 min of kickoff:   30 / 197   (15%)
within  30 min of kickoff:   54 / 197   (27%)
within  60 min of kickoff:  112 / 197   (57%)
within  90 min of kickoff:  142 / 197   (72%)
within 180 min of kickoff:  187 / 197   (95%)
```

That is a much healthier capture than the first pass suggested. The median
college football game has a price we recorded 55 minutes before kickoff, and
95% have one inside three hours.

## Why it is still not a closing line

The bar is not "recent". It is the purchased NFL backfill that
`engine/closing.py` is built on, which caught 16 books within **5 to 28
minutes** of every kickoff. Against that:

- **27%** of games have any price inside 30 minutes.
- The other 73% are represented by a number that is an hour or more old at
  kickoff, in a sport where lines move on warmups and late scratches.

`engine/adapters/base.py` is explicit that setting `is_closing` untruthfully
"silently corrupts every CLV number downstream", so none of these may be
stamped as closes.

The subtler trap is the one that never touches `is_closing`. Returning these as
ordinary `is_closing=False` lines still hands the backtester a "market price"
to score against, and a price an hour stale has not absorbed what the closing
line has. Our model beats it more often than it beats the real market. That is
a backtest that reads better than the truth, produced without a single
dishonest field — and two sports have already told this project its model loses
to the closing market. A college football number that disagreed would be a
measurement artifact, and it would be the most quotable number on the site.

## What would move it

The cadence is the lever, and it is not tuned for this. `capture.yml` is
`*/30`, which is 48 runs a day. Distinct capture runs per UTC day, counted from
the observation timestamps themselves:

```
2026-08-31  10      2026-09-05  16
2026-09-01  13      2026-09-06  18
2026-09-02  14      2026-09-07  11
2026-09-03  13      2026-09-08  13
2026-09-04  15      2026-09-09   7  (partial day)
```

Ten to eighteen, not forty-eight — a run every 90 to 150 minutes, which is
almost exactly the 55-minute median and 99-minute p75 above. The capture is
performing about as well as its cadence permits. This is the same throttling
`scheduled-runs-and-silent-green.md` §2 measured on 2026-08-28, still present a
fortnight later.

So the fix is not more frequent polling of everything. In rough order of cost:

1. **A kickoff-triggered capture.** `engine/capture.py` already has
   `minutes_to_next_kickoff` and `capture-evidence.yml` already uses the idea.
   A job that fires inside the last 30 minutes before a kickoff and captures
   only those events would convert that 27% toward the backfill's standard at a
   *fraction* of the current request volume — most runs today are spent
   observing games that are days away.
2. **Widen the college window near a Saturday.** `engine.lines` carries a
   36-hour window plus `LOOKAHEAD_EVENTS = 8`, tuned for a weekly NFL slate.
   Neither fits 100 FBS games stacked into one afternoon.
3. **Accept the paid path.** The Odds API historical endpoint is what bought
   the NFL its defensible closes in the first place.

Until one lands, `load_historical_lines` returning `[]` is the correct answer
and "board only" is the correct status.

## The NFL cannot be judged on this yet

`--sport nfl` reports **0 played events** with `own_capture` provenance: week 1
kicks off 2026-09-09 and the board capture that writes those rows only began
covering NFL games recently. HANDOFF §9's "NFL moneyline — needs a season of
our own capture" is untested by this measurement, not contradicted by it. Worth
re-running once a few weeks have been played, since the cadence finding above
applies to that plan too.

## What this does not say

Nothing here is an argument against the capture. 89,173 timestamped pre-kickoff
rows we own outright is real evidence, and the commit timestamps are
third-party attestation that we held those prices when we say we did. It is
what a kickoff-triggered job would build on. It is simply not, yet, a close.
