---
title: "Methodology: how our NFL model works, and how it performed against the market"
description: "The full model specification, walk-forward backtest results including the ones that go against us, the calibration table, the confidence cap, the leakage controls, and how the SHA-256 Merkle commitment works."
last_updated: 2026-08-02
model_version: elo-mov-v1+iso
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

## Summary in one paragraph

We predict NFL game outcomes with an Elo rating system that uses a damped
margin-of-victory update, then convert those ratings into probabilities and
correct those probabilities with isotonic regression refit each season on prior
seasons only. Across 2,750 out-of-sample games from 2016 through 2025, the
model recorded a Brier score of 0.22228 against the de-vigged closing market's
0.21061, straight-up accuracy of 63.96% against the market's 66.58%, and an
against-the-spread record of 1333-1352-65, or 49.65%, against a breakeven of
52.38% at standard -110 pricing. **The model does not beat the closing market.**
Our probabilities are well calibrated, which is a different and smaller claim,
and it is the only claim we make.

---

## What we claim and what we do not claim

We claim exactly two things:

1. **Our published probabilities are calibrated.** When we publish 70%, events
   in that band have historically occurred about 70% of the time in our
   out-of-sample testing. The measured expected calibration error of the
   calibrated model is 0.02162.
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

The production model version is `elo-mov-v1+iso`.

---

## How we test: walk-forward, never in-sample

Ratings are built strictly forward in time. For every game in the historical
record the model produces a prediction **using only ratings derived from games
that had already finished**, and only afterwards is the result used to update
the ratings. There is no point at which the model sees a future game.

- Rating warm-up period: 1999 through 2015.
- Out-of-sample scoring period: 2016 through 2025.
- Games graded: 2,750. This is every regular and post-season game in the window
  that was not a tie and for which both moneyline prices were available, so the
  model and the market can be scored on identical games.

The market comparison uses **de-vigged** closing prices. Both sides' implied
probabilities are divided by their sum to remove the bookmaker margin. Comparing
a model to a vigged line is trivially easy and meaningless, because the vig
guarantees the raw line is a biased probability estimate.

---

## Backtest results, 2016-2025

### Against the de-vigged closing market

| metric | our model | de-vigged market | who wins |
|---|---|---|---|
| Brier score | 0.22228 | 0.21061 | market, by 0.01166 |
| log loss | 0.63535 | 0.60863 | market, by 0.02672 |
| straight-up accuracy | 63.96% | 66.58% | market, by 2.62 points |

Lower is better for Brier score and log loss. The market wins on every measure.

### Against the spread

| metric | value |
|---|---|
| record | 1333-1352-65 |
| win rate on decided games | 49.65% |
| breakeven at -110 | 52.38% |
| shortfall | 2.73 percentage points |

The model, betting the side it disagreed with the posted number on, went
1333-1352-65. That is a losing record before pricing and a decisively losing
record after it.

### What this means

The NFL closing line is among the most efficient prediction markets that
exists. Thousands of participants with better data than ours, including
professional syndicates, push it toward the true probability before kickoff. A
clean Elo baseline losing to it is the expected result, not a defect.

We learned this privately, from our own backtest, before launch. The honest
consequence is that **we cannot sell "we beat the market" at any price**, so we
do not sell picks. The paid product is tools and data - no-vig calculators,
line-movement alerts, historical closing-line-value lookups, model exports.
The predictions themselves are free, and they are free because we do not
believe they are worth money.

If you see a service advertising a sustained edge over NFL closing lines, the
appropriate question is not "how big is the edge" but "show me the same table
above, computed the same way, on out-of-sample games, against de-vigged closing
prices."

---

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
| raw Elo | 0.02654 | 0.22228 |
| isotonic-calibrated Elo (published) | **0.02162** | 0.22323 |
| de-vigged market | 0.01802 | 0.21061 |

Two honest notes on that table. First, calibration improves ECE by about 18.5%
but very slightly **worsens** Brier score, from 0.22228 to 0.22323. Isotonic
regression buys reliability at a small cost in sharpness. We publish both
numbers because reporting only the one that improved would be the same
selective disclosure we are criticising. Second, the market is still better
calibrated than we are.

### Reliability table, calibrated model, 2,750 games

| predicted band | n | mean predicted | actual frequency | gap |
|---|---|---|---|---|
| 0.0-0.1 | 12 | 1.00% | 33.33% | -32.33 pts |
| 0.1-0.2 | 18 | 16.66% | 27.78% | -11.12 pts |
| 0.2-0.3 | 149 | 24.84% | 30.87% | -6.03 pts |
| 0.3-0.4 | 324 | 36.21% | 34.88% | +1.33 pts |
| 0.4-0.5 | 593 | 44.80% | 43.00% | +1.80 pts |
| 0.5-0.6 | 401 | 56.10% | 53.62% | +2.48 pts |
| 0.6-0.7 | 739 | 64.98% | 63.87% | +1.11 pts |
| 0.7-0.8 | 244 | 73.66% | 72.54% | +1.12 pts |
| 0.8-0.9 | 210 | 84.77% | 82.86% | +1.91 pts |
| 0.9-1.0 | 60 | 94.51% | 86.67% | **+7.84 pts** |

A positive gap means we were overconfident: we predicted the event more often
than it happened.

Read the extremes with care. The 0.0-0.1 and 0.1-0.2 bands hold 12 and 18 games
respectively; at those sample sizes a handful of upsets moves the observed
frequency by tens of points and the gap is mostly noise. The bands that carry
real weight are 0.3 through 0.9, which hold 2,511 of the 2,750 games, and in
those bands the model is overconfident by between 1.1 and 2.5 percentage
points.

For comparison, the de-vigged market over the same games is mildly
**under**confident in its top bands: it predicted 84.70% and observed 87.57% in
the 0.8-0.9 band. That is the signature of a market that has priced in the vig
asymmetry, and it is another reason we treat the market as the benchmark rather
than the opponent.

---

## Why we cap published confidence at 85%

**We do not publish any probability above 0.85, regardless of what the model
outputs.** The cap exists because of one row in the table above.

In the 0.9-1.0 band, across 60 out-of-sample games, the calibrated model
predicted an average of 94.51% and the events occurred 86.67% of the time. The
model was overconfident by 7.84 percentage points - four times the error of any
other well-populated band.

This is the single most important finding in our testing, because it inverts
the industry's usual sales pitch. The standard product in this category is "our
one highest-confidence pick of the day." That is precisely the band where our
model is least trustworthy. High-confidence selections are not the safe subset;
in our data they are the least reliable subset, because extreme probabilities
are produced by extreme rating gaps, and extreme rating gaps are exactly where a
simple rating system is most likely to be extrapolating past the evidence.

Capping at 0.85 keeps every published probability inside a band where our
measured overconfidence is under two percentage points. It costs us the
headline number that would sell best. We consider explaining why we do not have
that number to be more valuable than having it.

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

The features actually used by the production model are: team identity, prior
ratings derived only from earlier games, home or neutral site, days of rest for
each team, and season boundaries for the carryover regression. That is the
complete list.

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
matters for the paid tier: we can prove a subscriber-only prediction was part of
the pre-kickoff commitment without publishing the whole slate to non-subscribers.

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

- Expected-points-added-based ratings alongside Elo
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

*Last updated 2026-08-02. Model version `elo-mov-v1+iso`.*
