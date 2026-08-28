# /props-model typed all of its numbers by hand

Written 2026-08-28 by the supervisor agent. **DONE the same day** — see the
"What actually happened" section at the bottom, which is the part worth
reading. The plan is kept above it because one of its predictions came true in
a way that changed what the page says.

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


---

# What actually happened

Shipped 2026-08-28. `scripts/props_model_note.py` rebuilds every figure from
two committed inputs — `data/capture/mlb-props/*.jsonl` and a new cached
`data/mlb/pitching_logs_2026.json` — writes
`site/public/data/props_model_note.json`, and with `--render` writes the
figures into the page. No digit in that markup is authored there.
`tests/test_props_model_note.py` fails if the page, the payload, or a fresh
recomputation disagree, if the conclusion the page argues stops following from
the payload, or if a bare number appears in the prose.

## Step 2 of the plan happened, and it was worth the warning

**The sample grew and the result got worse.** 194 props became 286; the model's
win rate on its own disagreements went 48.1% → 44.8%. Two causes, one of them
a defect: five more days of capture, and `hitrates.find_player` refusing every
duplicate name outright, which silently dropped about a dozen working starters
(Hunter Brown, Luis Castillo) from the original sample. The script resolves
those by preferring the single active pitcher; the engine still does not, which
is noted below.

**One claim did not survive.** The page reported information of 0.48 across all
pitcher-starts against −0.07 on board props, and blamed books for choosing
which games to hang. That 0.48 turns out to be measured against a single
league-median line applied to every pitcher alike:

| what the model was graded against | n | slope |
|---|---:|---:|
| every start, one league-median line for everyone | 2,499 | +0.50 |
| every start, the line that pitcher usually gets | 2,472 | +0.20 |
| board games, the pitcher's usual line | 282 | +0.09 |
| board games, the line books actually posted | 286 | −0.11 |

Line specification is worth 4.7 standard errors. Game selection, holding the
line rule fixed, is worth 0.6. The exact posted price is worth 0.8. **The
selection effect the page published as "the part that generalises" is not
measurable at this sample size.** The conclusion — no edge on real props — is
unchanged and slightly stronger. The page now carries a section saying all of
this in its own words, with the superseded figures quoted and marked `data-was`.

**A statistic was replaced.** Worst-of-ten calibration buckets is a
two-observation artifact at this sample size. Now expected calibration error
over five equal-count buckets, scored out of fold rather than on one 50/50
split (the single split drew a 49.7% half against a 37.8% half and mostly
measured that).

## Deliberate debt, logged rather than hidden

- **The window is pinned** to games through 2026-08-26. Without it every
  `capture: mlb props snapshot` commit would change a published figure and
  redden the gate on work nobody did. A pin is exactly how the CLV disclaimer
  went 22 days stale, so a test fails once capture runs 30 days past it, with
  the command to extend it in the failure message.
- **`engine/hitrates.find_player` still refuses duplicate names.** For the live
  `/props` page that is arguably right — publishing the wrong man's splits is
  worse than publishing none — but it currently costs one prop of eighteen its
  hit rates, and it cost this analysis a dozen pitchers. The resolver in
  `scripts/props_model_note.py` shows the safe version: prefer the single
  *active pitcher* among exact matches, still refuse when two remain. Moving it
  into the engine would change what `/props` publishes, so it was left alone.
- **`props-live.yml`'s annotate step swallows four sub-failures** with
  `|| echo`. Each is individually justified in the comments, but a permanent
  `engine.hitrates` failure would be invisible. Not the total-failure pattern,
  so not fixed with the two workflows in
  `scheduled-runs-and-silent-green.md`.
- **Three withdrawn explanations are still described, not regenerated.** They
  were one-off diagnostics in August 2026 and the analysis no longer exists.
  Their figures were removed from the prose rather than left hand-typed, and
  the page says why.

## Still open from the original note

- `/market`'s "best sports betting research analyzer" headline. Untouched,
  Branden's call.
- `site/public/data/nflboard.json`, 55 hours stale, read by `engine/xcards.py`
  alone and fetched by no page.
- `scripts/verify_core.py`'s market Brier of 0.21061 matching neither published
  evaluation. Standalone diagnostic; publishes nothing.
