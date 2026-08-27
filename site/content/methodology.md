---
title: "Methodology: how our NFL model works, and how it performed against the market"
description: "The full model specification, walk-forward backtest results including the ones that go against us, the calibration table, the confidence cap, the leakage controls, and how the SHA-256 Merkle commitment works."
last_updated: 2026-08-02
model_version: elo+epa-v1+iso
---

# Methodology

This page is the complete technical description of how our predictions are
produced and how they performed in testing. It includes the results that argue
against paying us for picks. That is deliberate. It is also the file we would
hand to a regulator, a payment processor, or a journalist who asked us to
substantiate anything on this site.

Everything on this page is reproducible from the public ledger and the open
source code. If a number here cannot be regenerated from published data, treat
it as an error and tell us.

---

## In plain English

If you're new to betting, here's the short version:

- We built a computer model that predicts who wins NFL games.
- We test it honestly, only on seasons it never learned from, and we show our work.
- **It loses to the betting market.** The odds the sportsbooks set are sharper than our model, and we say so out loud instead of hiding it.

So Sooth isn't selling you winning picks. What it does is line up the same bet
across many sportsbooks and show which one pays the most, with the book's
built-in cut ("the vig") removed so you can see the true price. The technical
detail below backs up every claim on this site. You don't need to read it to
use the tool.

---

## Summary in one paragraph

We predict NFL game outcomes with an Elo rating system that uses a damped
margin-of-victory update, augmented with opponent-aware expected-points-added
form and rest, then convert those ratings into probabilities and correct them
with isotonic regression refit each season on prior seasons only. Across 2,671
out-of-sample games from 2016 through 2025, the published model recorded a
Brier score of 0.22151 against the de-vigged closing market's 0.21038,
straight-up accuracy of 63.53% against the market's 66.64%, and an
against-the-spread record of 1298-1310-63, or 49.77% of decided games, against
a breakeven of 52.38% at standard -110 pricing. **The model does not beat the
closing market.** Our probabilities are reasonably calibrated, which is a
different and smaller claim, and it is the only claim we make.

---

## What we claim and what we do not claim

We claim exactly two things:

1. **Our published probabilities are calibrated.** When we publish 70%, events
   in that band have historically occurred about 70% of the time in our
   out-of-sample testing. The measured expected calibration error of the
   published model is 0.03074; the de-vigged market's is 0.01913. The market
   is better calibrated than we are, and we say so.
2. **Our record is tamper-evident.** Every prediction is hashed and committed to
   a public Merkle root before the first kickoff of its slate. We cannot delete
   a loss or add a win after the fact without breaking the root.

We do not claim, and have never claimed, that following our predictions is
profitable. Our own testing says it is not. We do not publish a win rate as a
selling point, a return on investment figure, or a units-won figure. We do not
accept wagers, hold funds, or pay out prizes.

---

## The model

### Ratings: Elo with margin-of-victory damping

Every team carries a single rating. Ratings start at 1500 and move only when a
game settles.

The probability that the home team wins is the standard Elo logistic:

```
p_home = 1 / (1 + 10 ^ (-(R_home - R_away + HFA + rest_bonus) / 400))
```

After the game settles, both ratings move by the same amount in opposite
directions:

```
delta       = K * mov_multiplier * (actual - p_home)
mov_multiplier = ln(|margin| + 1) * (2.2 / (0.001 * winner_elo_diff + 2.2))
```

The margin-of-victory multiplier is the standard log-damped form. It gives more
credit for a 24-point win than a 3-point win without letting a single blowout
dominate a team's rating, and the `winner_elo_diff` denominator corrects for the
fact that better teams are mechanically more likely to win by a lot. Without
that correction the system over-rates favourites in a self-reinforcing loop.

### Parameters

| parameter | value | meaning |
|---|---|---|
| `k` | 20.0 | rating points moved per unit of surprise |
| `home_advantage` | 48.0 Elo | roughly 2 points of spread |
| `season_carryover` | 0.75 | fraction of a rating carried into the next season |
| `base_rating` | 1500.0 | starting and mean-reversion target |
| `elo_per_point` | 25.0 | Elo points per point of scoring margin |
| `rest_per_day` | 1.5 Elo | bonus per extra day of rest versus the opponent |

These values are conventional, were not tuned against the test period, and are
published so that anyone can reproduce our ratings exactly. The model is
deliberately simple. Its job is not to be clever; its job is to be a fully
explainable baseline that we can publish, grade in public, and improve on
in the open.

### Calibration: isotonic regression, refit every season

Raw Elo probabilities are mildly overconfident in the middle bands. We correct
them with isotonic regression, which is a monotone step-fit that reshapes the
probability curve without assuming that curve is logistic.

The calibrator is fitted **only on seasons strictly before the season being
predicted**, and it is refitted every year. Fitting a calibrator on the same
games you then score with it manufactures a perfect-looking reliability curve
that means nothing. Seasons before we have 500 prior games available pass
through uncalibrated rather than being calibrated on thin data.

The production model versions are `elo+epa-v1+iso` (independent) and
`elo+epa+market-v1+iso` (consensus).

---

## How we test: walk-forward, never in-sample

Ratings are built strictly forward in time. For every game in the historical
record the model produces a prediction **using only ratings derived from games
that had already finished**, and only afterwards is the result used to update
the ratings. There is no point at which the model sees a future game.

- Rating warm-up period: 1999 through 2015.
- Out-of-sample scoring period: 2016 through 2025.
- Games graded: 2,671. This is every regular and post-season game in the window
  that was not a tie and for which both moneyline prices were available, so the
  model and the market can be scored on identical games.

The market comparison uses **de-vigged** closing prices. Both sides' implied
probabilities are divided by their sum to remove the bookmaker margin. Comparing
a model to a vigged line is trivially easy and meaningless, because the vig
guarantees the raw line is a biased probability estimate.

---

## Backtest results

Every figure below is regenerated by a single command:

```
python scripts/published_figures.py
```

If a number on this site cannot be produced by that command, it should not be
on this site. We publish **two** evaluations of the same models rather than
choosing the flattering one.

### A. nflverse lines — 2016-2025, n=2671

Larger sample, weaker provenance. nflverse's `spread_line` is an undocumented
periodic snapshot rather than a documented close.

| model | n | Brier | ECE | ATS record | ATS% |
|---|---|---|---|---|---|
| Elo baseline | 2671 | 0.22217 | 0.02698 | 1287-1321-63 | 0.4935 |
| Independent (ours) | 2671 | 0.22151 | 0.03074 | 1298-1310-63 | 0.4977 |
| Consensus (+market) | 2671 | 0.21439 | 0.03221 | 1316-1292-63 | 0.5046 |
| Closing market | 2671 | 0.21038 | 0.01913 | 1296-1312-63 | 0.4969 |

### B. Real consensus closing lines — 2023-2025, n=854

Smaller sample, far better provenance: the median across books, captured
5–28 minutes before each kickoff, from odds we paid for and hold ourselves.

| model | n | Brier | ECE | ATS record | ATS% |
|---|---|---|---|---|---|
| Elo baseline | 854 | 0.22246 | 0.03265 | 402-431-21 | 0.4826 |
| Independent (ours) | 854 | 0.22176 | 0.03356 | 404-429-21 | 0.4850 |
| Consensus (+market) | 854 | 0.21395 | 0.04186 | 414-419-21 | 0.4970 |
| Closing market | 854 | 0.21061 | 0.02396 | 414-419-21 | 0.4970 |

### Break-even is 0.5238

At −110 on both sides a bettor needs 52.38% against the spread to break even.
**No model in either table clears it.** Neither does the closing market
against its own number — which is the sanity check that the test is
well-formed rather than flattering us.

### The engine is allowed to say nothing

Everything above is the record of a model with an opinion on every game. That
is the honest denominator, and it loses. It is also not how the engine now
publishes.

A spread is a question about margin, so the decision against a number comes
from a regression that predicts margin directly, and the distance between our
predicted margin and the posted number — in points — is the only quantity that
decides whether we say anything at all. Below four points we do not. Some weeks
that means no play on the whole slate.

The threshold was chosen by measurement, and here is the measurement, on both
line sources:

| edge bar | A: nflverse 2016-2025 | B: real closes 2023-2025 |
|---|---|---|
| every game | 1298-1310-63 (49.77%) | 404-429-21 (48.50%) |
| ≥ 2 points | 657-631-30 (51.01%) | 193-205-10 (48.49%) |
| ≥ 3 points | 438-409-16 (51.71%) | 127-125-6 (50.40%) |
| **≥ 4 points** | **278-245-7 (53.15%)** | **82-71-1 (53.59%)** |
| ≥ 5 points | 169-140-4 (54.69%) | 47-42-1 (52.81%) |

At the shipped bar that is about 52 plays a season out of roughly 261 games —
one game in five.

**This is not an edge, and we will not describe it as one.** The 95% interval
on 53.15% runs from 48.87% to 57.39%, and on the better-provenance sample from
45.70% to 61.31%. Both intervals contain the 52.38% break-even and both
contain 50%. The threshold was also found by searching thresholds, which
weakens it further than the interval alone suggests. The honest statement is
that selection makes a losing model less bad by an amount we cannot
distinguish from noise.

Every season of the shipped rule on the larger sample, losers included:

| season | record | | season | record |
|---|---|---|---|---|
| 2016 | 26-22 | | 2021 | 33-25-1 |
| 2017 | 24-26 | | 2022 | 31-23-4 |
| 2018 | 28-30-1 | | 2023 | 23-22 |
| 2019 | 29-21-1 | | 2024 | 38-27 |
| 2020 | 23-24 | | 2025 | 23-25 |

Four of ten seasons are losing seasons.

### What we tested and did not ship

At the four-point bar on nflverse lines, the underdog side ran 54.83% and the
favourite side 48.57% — a large split, and a tempting second filter. On the
real captured closes the same split reverses: 52.43% dog against 56.00%
favourite. A split that changes sign when the line provenance improves is a
property of the line source rather than of football, so the underdog flag is
reported on each game and is not used to select. The threshold itself holds on
both sources, which is why the threshold is the part that ships.

### How far apart are the two line sources?

32.9% of spreads differ between nflverse and the real
consensus close, but the typical difference is small: mean
0.217 points, median 0.0,
and only 5.5% differ by a full
point or more. The weaker source was precise enough for the conclusion and not
precise enough to publish closing-line value from, which is why we bought the
better one.

## Calibration results

Calibration asks a narrower question than profitability: when we say 70%, does
it happen about 70% of the time? A model can be well calibrated and still
unprofitable, which is precisely our situation.

### Expected calibration error

Expected calibration error (ECE) is the sample-weighted mean absolute gap
between predicted and observed frequency across ten probability bands. Lower is
better.

| model | ECE | Brier |
|---|---|---|
| Elo baseline | 0.02698 | 0.22217 |
| Elo + EPA + rest, isotonic (published) | **0.03074** | 0.22151 |
| de-vigged market | 0.01913 | 0.21038 |

Two honest notes on that table. First, adding EPA form and rest improves the
Brier score over the Elo baseline but slightly **worsens** measured ECE. Extra
features buy sharpness at a small cost in reliability, and we publish both
numbers because reporting only the one that improved would be the same
selective disclosure we are criticising. Second, the market is better
calibrated than we are — on this test, meaningfully so.

### Reliability table, published model, 2,671 games

| predicted band | n | mean predicted | actual frequency | gap |
|---|---|---|---|---|
| 0.1-0.2 | 26 | 16.70% | 26.92% | -10.22 pts |
| 0.2-0.3 | 152 | 26.16% | 28.95% | -2.79 pts |
| 0.3-0.4 | 270 | 36.02% | 33.70% | +2.32 pts |
| 0.4-0.5 | 419 | 45.37% | 41.29% | +4.08 pts |
| 0.5-0.6 | 569 | 54.99% | 50.26% | +4.73 pts |
| 0.6-0.7 | 593 | 64.97% | 62.39% | +2.58 pts |
| 0.7-0.8 | 440 | 74.86% | 72.95% | +1.91 pts |
| 0.8-0.9 | 190 | 83.93% | 85.26% | -1.33 pts |
| 0.9-1.0 | 12 | 91.13% | 91.67% | -0.54 pts |

A positive gap means we were overconfident: we predicted the event more often
than it happened.

Read the extremes with care. The 0.1-0.2 and 0.9-1.0 bands hold 26 and 12
games respectively; at those sample sizes a handful of results moves the
observed frequency by tens of points and the gap is mostly noise. The bands
that carry real weight are 0.3 through 0.8, which hold 2,291 of the 2,671
games, and in those bands the model runs overconfident by between 1.9 and 4.7
percentage points.

---

## Why we cap published confidence at 85%

**We do not publish any probability above 0.85, regardless of what the model
outputs.**

The honest reason is sample size. In the current out-of-sample record the
0.9-1.0 band holds twelve games — far too few to demonstrate that the model
deserves that much confidence. An earlier, larger evaluation of the raw Elo
baseline showed the opposite problem: roughly eight points of overconfidence
at the top of the range. Between a band too thin to trust and a history of
overconfidence exactly where the industry sells its "locks", the conservative
policy is a hard cap, and we keep it as a design rule rather than a measured
finding. If the extreme bands ever accumulate enough games to be measured
properly, we will publish that table and revisit the cap in the open.

---

## Leakage controls

Data leakage - training on information that would not have been available
before kickoff - is the most common way a sports model backtests beautifully
and then loses live. It is also the easiest way to build a fraudulent-looking
track record without meaning to.

The following columns are present in our source data and are **banned from
feature construction**, enforced by an assertion in the NFL adapter that fails
the build rather than warning:

| banned column | why |
|---|---|
| `temp` | measured at or after the game, not a pre-game forecast |
| `wind` | same |
| `home_score`, `away_score` | the outcome |
| `result` | the outcome |
| `total` | the outcome |
| `overtime` | the outcome |

Betting-line columns require a separate control. In our source dataset,
`spread_line` and the related price columns are **overwritten in place as the
market moves**. A row read today shows the current number, not the number that
existed when the game was scheduled. We therefore treat those columns as a
closing line only for games already marked final, and we never treat them as an
opening line.

Because of that, **we have not published a closing-line-value figure and will
not publish one** until we have validated our line history against an
independent source with explicit open and close objects. CLV is the metric most
often quoted by services in this category and it is the metric most easily
faked by reading a mutable field. Ours will be published when it is defensible
and not before.

The features actually used by the production models are: team identity, prior
Elo ratings derived only from earlier games, opponent-aware expected-points-
added form (also computed only from earlier games), home or neutral site, days
of rest for each team, and season boundaries for the carryover regression. The
consensus model additionally uses the de-vigged market probability. That is
the complete list.

---

## The commitment scheme

The problem with every published pick record on the internet is that it is
self-reported and editable. A losing pick can quietly vanish. A winning pick can
be added afterwards. "We publish everything" is an unfalsifiable claim.

We make our record falsifiable with a commit-reveal scheme.

### How it works

1. **Canonicalise.** Before the first kickoff of a slate, every prediction is
   serialised to deterministic JSON: keys sorted alphabetically, no insignificant
   whitespace, UTF-8. The same logical prediction produces byte-identical output
   on any machine.
2. **Hash each prediction into a leaf.**
   `leaf = SHA-256(0x00 || canonical_json)`
3. **Build a Merkle tree.** Adjacent nodes are combined as
   `parent = SHA-256(0x01 || left || right)`, working up the tree until one node
   remains. If a level has an odd number of nodes, the last node is duplicated.
   The distinct `0x00` and `0x01` prefixes are domain separation: they make it
   impossible to pass an internal node off as a leaf, which is the standard
   second-preimage attack on naive Merkle trees.
4. **Publish the root before kickoff.** Only the root hash is published at this
   stage. A 64-character hash reveals nothing about which teams we picked.
5. **Anchor the root to a third-party timestamp.** The root is committed to a
   public Git repository. GitHub's commit timestamps are issued by a third party
   and are not forgeable by us, which is what turns "we published this early"
   into something you can check rather than take on faith.
6. **Reveal after settlement.** Once the games are final we publish every
   prediction in full, along with the leaf hashes.

Anyone can then recompute the tree from the revealed predictions and confirm it
produces the root we published before kickoff. If we had altered, removed,
reordered, or back-dated a single prediction, the recomputed root would not
match. The algorithm identifier recorded in every commitment file is
`sha256-merkle-v1`.

The commit function refuses to seal a slate after its first kickoff. A
commitment created after games have started proves nothing, so we made it
impossible to create one by accident.

### An inclusion proof lets you check one pick

Because it is a Merkle tree and not a flat hash, a single prediction can be
proven to belong to a committed slate without revealing the rest of the slate.
For our 16-game NFL Week 1 slate, an inclusion proof is four hashes long. This
is what lets one prediction be checked on its own — quoted in a post, or carried
in an alert email — without anyone having to fetch and re-hash the entire slate
to test a single claim.

Step-by-step instructions for verifying all of this yourself, including a
30-line script that does not use any of our code, are on the [verification
page](/verify).

### What the commitment does and does not prove

It proves the record is complete and unedited. Every prediction we made is in
it, in the form we made it, timestamped before kickoff.

It does not prove the predictions are good. Cryptography cannot make a model
accurate. It only makes our reporting of that model honest, which is a
different and much rarer property in this industry.

---

## Known limitations

We would rather state these than have them found.

- **The model loses to the market.** Stated at the top and repeated here.
- **Ratings are team-level.** There is no quarterback adjustment. An injury to a
  starting quarterback is not reflected in our probability until the team has
  played and been re-rated, which means our early-season and post-injury numbers
  are systematically worse than the market's.
- **No play-level information.** The model does not use expected points added,
  success rate, or any drive-level data. It knows who played whom and by how
  much.
- **Small samples at the extremes.** As noted, the outer probability bands hold
  too few games to draw conclusions from.
- **One sport is Live.** NFL only. The other eight sports on this site are
  labelled "in calibration" or "deferred" and are not graded against verified
  closing lines yet. A sport is never marked Live without confirmed free
  closing-odds history, because without it we cannot grade ourselves honestly.
- **No published CLV.** See the leakage section.
- **Backtests are not forecasts.** Ten seasons of out-of-sample results are a
  reasonable sample, not a guarantee about 2026. Past performance does not
  indicate future results.

---

## Planned improvements

These are the changes we expect to make, published in advance so the record
shows what changed and when:

- A quarterback availability adjustment
- Blending model probability with market probability, which usually improves
  Brier score even when the model alone does not
- Validating our line history against an independent source so a
  closing-line-value figure can be published

Any change to the model produces a new `model_version` string, and every
prediction in the ledger records the version that produced it. A prediction can
always be traced to the exact model that made it.

---

## Data sources and code

- Historical NFL schedules, scores, and betting lines: nflverse public datasets.
- Rating, calibration, backtest, and commitment code: open source, in the
  project repository. The verification function has no dependency on our
  honesty; it recomputes everything from published files.
- Ledger: [/ledger](/ledger). Verification guide: [/verify](/verify).

## Disclosures

This site publishes predictions for analysis and entertainment. We do not accept
wagers, hold funds, or pay prizes. We are not affiliated with the NFL, any
league, team, or sportsbook. Full disclaimers, including responsible-gambling
resources, are at [/disclaimers](/disclaimers).

*Last updated 2026-08-06. Model versions `elo+epa-v1+iso` (independent) and `elo+epa+market-v1+iso` (consensus).*
