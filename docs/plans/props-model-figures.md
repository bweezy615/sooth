# /props-model types all of its numbers by hand

Written 2026-08-28 by the supervisor agent. **Found, characterised, not fixed.**
This is the next session's largest honesty item and it is a real piece of work,
not a copy edit.

## What it is

`site/public/props-model.html` is the research note explaining why we built a
strikeout-prop model, measured it, and refused to ship it. It is one of the best
pages on the site — a published negative result, in detail, with a stated bar
for reopening the decision:

> If you want the bar for reopening this: a model would have to show real
> information on the population books actually post, on a sample larger than
> 194. That number is now written down, so nobody — including us — gets to move
> it quietly.

Every figure in it is hand-typed. Forty-four distinct numbers appear in the
visible prose, and almost none of them exists in any published payload.

## What is and is not covered

Two payloads exist and are generated:

| payload | holds |
|---|---|
| `site/public/data/props_model_backtest.json` | 40 pitchers, 723 starts, MAE 2.044 vs 2.072 baseline, 32.2% within 1K, 84.2% Poisson-80 coverage |
| `site/public/data/props_model_tb_backtest.json` | 40 batters, 3,907 games, MAE 1.628, per-line calibration |

Neither is read by the page, and neither contains the figures the page's
argument actually rests on. Those are the **board-population** numbers, and no
script in the repository produces them:

- 194 props with a gradeable result, reconstructed from capture between
  5 and 21 August 2026
- 156 of 194 where the model disagreed by 3+ points
- our side won 48.1% of those; the market predicted 48.6% over against 43.3%
  actual; 46.4% / 49.8% / 52.4% appear in the same tables
- 1,482 pitcher-starts and 2,608 as separate populations, with information
  coefficients 0.2439 / 0.2480 / 0.2800
- 160 captured total-bases quotes against 3,207 for strikeouts

Watch for a trap while reading: `43.3` appears both in the page's prose (the
strikeout board sample) and in `props_model_tb_backtest.json` (the total-bases
1.5 line's `predicted_over_pct`). They are different measurements that happen to
collide, and treating one as the source of the other would be wrong.

## Why it matters, and why it is not urgent tonight

Same defect class as the `/alerts` "160 divergences" sentence fixed this
session: a measurement published as prose, with nothing able to reproduce it. It
went stale there because the detector was fixed three times underneath it. The
exposure here is larger — this is the page that argues we are honest about a
failure, and it is the page whose numbers a reader would most want to check.

It is not urgent because these describe a **closed experiment** over a window
that has ended, and the evidence is still on disk: `data/capture/mlb-props/`
holds 2026-08-05 through 2026-08-26, and outcomes are obtainable. Nothing is
drifting. It is simply unverifiable.

## How to do it, when someone does

1. Write `scripts/props_model_note.py` that reconstructs the board population
   from `data/capture/mlb-props/` over the stated window, grades it, and emits
   every figure the page quotes into one payload.
2. **Expect the numbers to move**, and do not paper over it if they do. The prop
   pipeline has been fixed at least twice since (player identity in `_series`,
   `commence_time` in `not_started`). If the regeneration disagrees with the
   published prose, that disagreement is the finding, and it gets published the
   way the original negative result was.
3. Then render the page from the payload, as `/alerts` now does, and pin it.

Do not hand-edit the numbers into agreement. If the new run says something
different, the page says the new thing and says that it changed.

## Also flagged this session, not fixed

- **/market's headline reads "The best sports betting research analyzer on the
  market."** An unverifiable superlative, in the largest type on the page, on a
  site whose position is that it only makes checkable claims. This is a
  positioning decision rather than a defect with a right answer, so it is
  Branden's call and has been left alone.
- **`site/public/data/nflboard.json` is 55 hours stale** (286 KB). Not a defect
  today: it is read by `engine/xcards.py` alone and no page fetches it. It would
  become one the moment a page did.
- **`scripts/verify_core.py` prints a market Brier of 0.21061** on a 2,750-row
  frame, which matches neither `evaluation_a` (0.21038) nor `evaluation_b`
  (0.21008). It is a standalone diagnostic that publishes nothing, so it is not
  a site defect, but the three frames being three different populations is worth
  someone confirming deliberately rather than by coincidence.
