# The /alerts frequency claim, and the "LIVE PRICING" label

Written 2026-08-28 by the supervisor agent. Two copy-vs-reality defects, both
found by reading a published sentence next to the code that is supposed to
back it.

## 1. "160 divergences between Aug 10 and Aug 22" is not reproducible

`site/public/alerts.html` carries, as hand-typed prose:

> Between **Aug 10** and **Aug 22, 2026** our own capture history recorded
> **160** divergences clearing **2.0** points across MLB game lines and player
> props — about **13** a day.

It arrived in `a18896208` ("Frequency is stated as measured, not promised").
It was measured. It is no longer true, and four separate things are wrong with
it.

**a. The number does not reproduce.** Replaying the committed capture history
for exactly that window, through today's detector and today's dedup rule, gives
**114**, about 8.8/day — not 160, about 13/day. The evidence did not change;
`data/capture` is append-only and every row from that window is still on disk.
The detector changed. Between Aug 22 and today `engine/alerts.py` was fixed for
three real bugs that all inflated counts:

- prop series pooled two different players at the same line and book into one
  "consensus", so each was reported as diverging from the other (346 keys
  merged two or more players);
- `not_started` read only `kickoff`, so prop rows were gated on a field they do
  not have;
- book spellings were not canonicalised on read, so one operator could count as
  two books and manufacture a consensus.

160 is what the buggy detector said. Nobody can obtain it now, which on this
site is the whole problem: a number a reader cannot regenerate is a claim, not
a measurement.

**b. It describes a population the sender does not draw from.** "MLB game lines
and player props" — but `engine/alert_email.main` calls
`alerts_mod.scan(pattern, min_move=floor)` and `scan`'s `include_props`
defaults to `False`. No prop has ever been eligible for an alert email. The
sentence also scopes to MLB while the sender scans every sport on the board.

**c. It quotes a threshold nobody can choose.** The signup form offers 1.5,
2.5 (default) and 4+. There is no 2.0 band. 2.0 is the workflow's
`--min-send`, which only applies on a run with nobody subscribed.

**d. It is frozen.** Even had it been right, a hand-typed window ending six
days ago goes stale by sitting still — the failure mode this repo has already
paid for twice (`figures.json`, `build_site.py`'s drift comment).

### The fix

Make it a measurement again, at the thresholds a subscriber can actually pick.

1. `engine/alerts.py` — `find_drift`, `find_divergence` and `scan` take an
   optional `now`. Both detectors are "as of now" by construction: they read
   the newest price per book and drop games that have started. With the wall
   clock hardcoded there was no way to ask what they would have said last
   Tuesday, and therefore no way to reproduce a published frequency at all.
   Default is the wall clock; every production caller passes nothing.
2. `scripts/alert_frequency.py` — replay the committed capture history over a
   trailing window, cycle by capture cycle, through **the same
   `find_divergence` the sender calls** and **the same `alert_key` +
   `RESEND_STEP` dedup `select_new` applies**. No reimplementation of the
   detector: the replay maintains latest-price-per-key incrementally and hands
   that reduced set to the real function, which is exactly equivalent because
   the function's own first step is that same reduction (verified against a
   naive full-history replay: identical keys, identical magnitudes).
   Writes `site/public/data/alert-frequency.json`.
3. `site/public/alerts.html` — the paragraph is filled at runtime from that
   file. No digits in the markup. If the fetch fails the paragraph says the
   measurement is unavailable; it never falls back to a remembered number.
4. Tests — the JSON's bands must match the form's radio values, the paragraph
   must contain no hand-typed figures, the replay must reproduce a known count
   on a fixture, and the file must be internally consistent.
5. `.github/workflows/alerts.yml` — regenerate the file in the job that
   already runs the sender and already commits, so it cannot go stale by hand.
   No cron, schedule or new workflow is touched.

What the generator said on 2026-08-28 — 14 days to 2026-08-27, every sport on
the board, game lines only, 233,958 observations:

| band | divergences | per day | by sport |
|---|---|---|---|
| 1.5 | 569 | 40.6 | mlb 528, nhl 19, nfl 18, nba 4 |
| 2.5 (the default) | 35 | 2.5 | mlb 27, nhl 5, nba 2, nfl 1 |
| 4.0 | 2 | 0.1 | mlb 2 |

Those are not in this document as a claim — they are here as a record of what
the first run produced. The page reads the file, and the file is rewritten
every time the sender runs. Two things fell out of measuring it that the old
sentence had hidden: the three band descriptions on the form ("many emails a
day", "still not quiet", "Rare") turn out to be accurate, and the gap between
the 1.5 and 2.5 bands is a factor of sixteen, which a visitor choosing between
them could not previously have known. Each band now carries its own measured
rate beside its radio button.

## 2. "LIVE PRICING" on /market

`market.html` labels the desk `MARKET INTELLIGENCE DESK · LIVE PRICING`. The
board is rebuilt by `capture.yml`, which is currently landing about three runs
a day. `desk.js:317` calls a feed stale past 3 hours, and by that rule:

| window | board rebuilds | mean gap | max gap | share of wall clock >3h old |
|---|---|---|---|---|
| Aug 21–28 | 156 | 1.08h | 10.5h | 12.5% |
| last 48h | 11 | 4.19h | 10.5h | 50% |

So half the time a visitor arrives, the page's own machinery says the feed is
delayed while the label above it says LIVE. The cadence needs Branden's
decision (`docs/plans/capture-cadence.md`) and is untouched here. The label
does not need a decision: it should stop promising something the page itself
contradicts. The status strip already states the real age
(`UPDATED <ago>` / `DELAYED — UPDATED <ago>`) and that is the honest surface.

Fix: the static label states what is permanently true — that the desk compares
every book we track — and freshness is left to the strip that measures it.

## Not done here

The /market headline reads "The best sports betting research analyzer on the
market." That is an unverifiable superlative on a site whose position is that
its statements are checkable. Flagged for Branden; not changed, because it is a
positioning decision rather than a defect with a right answer.
