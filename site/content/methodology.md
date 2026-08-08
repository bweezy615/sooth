---
title: "Methodology: how our NFL model works, and how it performed against the market"
description: "The full model specification, walk-forward backtest results including the ones that go against us, the calibration table, the confidence cap, the leakage controls, and how the SHA-256 Merkle commitment works."
last_updated: 2026-08-07
model_version: elo-mov-v1 baseline + walk-forward logistic ensemble
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

We publish three NFL models, all built walk-forward so each season is predicted
using only earlier seasons. The **Elo baseline** (`elo-mov-v1`) is a transparent
margin-of-victory rating system. The **independent** model adds opponent-aware
EPA ratings and rest through a logistic fit and never sees the betting line. The
**consensus** model adds one more feature, the de-vigged market price. We score
all three against the de-vigged market on two out-of-sample samples: nflverse
lines from 2016 through 2025 (n=2,671) and real consensus closing lines from 2023
through 2025 (n=854). On both samples, **no model beats the market and none
clears the 52.38% against-the-spread break-even.** Our best model, consensus,
posts a Brier score of 0.21455 against the market's 0.21038 on the larger sample,
and a calibration error of 0.03343 against the market's 0.01913, which means
**the market is better calibrated than we are.** The one thing we can promise is
not an edge; it is that every number here is reproducible from published data and
our record cannot be edited after the fact.

---

## What we claim and what we do not claim

We claim exactly two things:

1. **Every figure on this page is a reproducible measurement.** The whole table
   regenerates with one command against public data and our own published odds;
   if a number cannot be reproduced, it is an error and we want to hear about it.
   Our independent model is calibrated to within about three percentage points
   (expected calibration error 0.03122 on the larger sample), which is honest but
   *worse* than the market's 0.01913. We do not claim to match, let alone beat,
   the market on calibration.
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

### The two model layers above the baseline

The Elo baseline is deliberately weak on its own. Two walk-forward logistic
models are fitted on top of it, each refit every season on strictly prior
seasons only. A season with fewer than 500 prior games passes through unfitted
rather than being trained on thin data. Fitting on the same games you then score
manufactures a perfect-looking curve that means nothing, so we never do it.

- **Independent** (`p_ensemble`). A logistic regression over the Elo
  win-probability plus opponent-aware EPA ratings, offensive and defensive
  rating differentials, rest, and division-game and playoff flags. It **never
  sees the betting line**, so it can disagree with the market informatively. This
  is the number worth publishing as our own opinion.
- **Consensus** (`p_anchored`). The same features plus one more: the de-vigged
  market probability. It is better calibrated and almost entirely uninformative
  as a bet, because it mostly reproduces the market. We publish it labelled as
  such; presenting it as our own opinion would look accurate while carrying
  almost no independent information.

We report both rather than quietly swapping the flattering one for the other.

---

## How we test: walk-forward, never in-sample

Ratings are built strictly forward in time. For every game in the historical
record the model produces a prediction **using only ratings derived from games
that had already finished**, and only afterwards is the result used to update
the ratings. There is no point at which the model sees a future game.

- Rating warm-up period: 1999 through 2015.
- Out-of-sample scoring period: 2016 through 2025.
- Games graded: 2,671 on the nflverse sample. This is every regular and
  post-season game in the window that was not a tie and for which both moneyline
  prices were available, so the model and the market are scored on identical
  games. The real-closing-line sample covers 854 of these.

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
| Independent (ours) | 2671 | 0.22148 | 0.03122 | 1291-1317-63 | 0.4950 |
| Consensus (+market) | 2671 | 0.21455 | 0.03343 | 1300-1308-63 | 0.4985 |
| Closing market | 2671 | 0.21038 | 0.01913 | 1327-1281-63 | 0.5088 |

### B. Real consensus closing lines — 2023-2025, n=854

Smaller sample, far better provenance: the median across books, captured
5–28 minutes before each kickoff, from odds we paid for and hold ourselves.

| model | n | Brier | ECE | ATS record | ATS% |
|---|---|---|---|---|---|
| Elo baseline | 854 | 0.22246 | 0.03265 | 402-431-21 | 0.4826 |
| Independent (ours) | 854 | 0.22164 | 0.03269 | 406-427-21 | 0.4874 |
| Consensus (+market) | 854 | 0.21399 | 0.04231 | 412-421-21 | 0.4946 |
| Closing market | 854 | 0.21061 | 0.02396 | 406-427-21 | 0.4874 |

### Break-even is 0.5238

At −110 on both sides a bettor needs 52.38% against the spread to break even.
**No model in either table clears it.** Neither does the closing market
against its own number — which is the sanity check that the test is
well-formed rather than flattering us.

### How far apart are the two line sources?

32.9% of spreads differ between the nflverse snapshot and the real consensus
close, but the typical difference is small: the mean absolute gap is 0.217
points, the median is zero, and only 5.5% of games differ by a full point or
more. Both samples reach the same verdict, which is the point. The weaker source
was precise enough to support the conclusion and not precise enough to publish a
closing-line-value figure from, which is why we bought the better one.

## Calibration results

Calibration asks a narrower question than profitability: when we say 70%, does
it happen about 70% of the time? A model can be well calibrated and still
unprofitable, which is precisely our situation.

### Expected calibration error

Expected calibration error (ECE) is the sample-weighted mean absolute gap
between predicted and observed frequency across ten probability bands. Lower is
better. The values below are the ECE column from the two backtest tables above.

| model | ECE (nflverse, n=2671) | ECE (real closes, n=854) |
|---|---|---|
| Elo baseline | 0.02698 | 0.03265 |
| Independent (ours) | 0.03122 | 0.03269 |
| Consensus (+market) | 0.03343 | 0.04231 |
| Closing market | 0.01913 | 0.02396 |

The market is better calibrated than every one of our models on both samples. We
report this rather than the one framing where we might look good, because a
calibration number nobody can reproduce is a claim, not a measurement.

### Reliability table, independent model, 2,671 games

This is the independent, market-blind model on the nflverse sample. A positive
gap means we were overconfident: we predicted the event more often than it
happened.

| predicted band | n | mean predicted | actual frequency | gap |
|---|---|---|---|---|
| 0.1-0.2 | 26 | 16.70% | 26.92% | -10.23 pts |
| 0.2-0.3 | 152 | 26.16% | 28.95% | -2.79 pts |
| 0.3-0.4 | 270 | 36.02% | 33.70% | +2.32 pts |
| 0.4-0.5 | 419 | 45.37% | 41.29% | +4.08 pts |
| 0.5-0.6 | 569 | 54.99% | 50.26% | +4.72 pts |
| 0.6-0.7 | 593 | 64.97% | 62.39% | +2.58 pts |
| 0.7-0.8 | 440 | 74.86% | 72.95% | +1.90 pts |
| 0.8-0.9 | 190 | 83.93% | 85.26% | -1.34 pts |
| 0.9-1.0 | 12 | 91.13% | 91.67% | -0.53 pts |

Read the extremes with care. The 0.1-0.2 band holds 26 games and the 0.9-1.0
band holds only 12; at those sample sizes a handful of results moves the observed
frequency by several points and the gap is mostly noise. The bands that carry
real weight are 0.3 through 0.8, which hold 2,291 of the 2,671 games, and there
the model is overconfident by between 1.9 and 4.7 percentage points.

---

## Why we cap published confidence at 85%

**We do not publish any probability above 0.85, regardless of what a model
outputs.** The cap exists because of the sample sizes at the top of the table
above.

In the 0.9-1.0 band the independent model produced only 12 of its 2,671
predictions, and the 0.8-0.9 band holds 190. Whatever gap we measure in those
bands rests on too few games to stand behind: a single upset swings the observed
frequency by several points. The largest overconfidence we can actually measure
in a well-populated band is about 4.7 points, in the 0.5-0.6 range.

Capping at 0.85 keeps every published probability inside a band with enough games
to be measured honestly. It costs us the headline number that sells best in this
category, "our one highest-confidence pick of the day," because that number would
come from exactly the thinly-populated extreme where we cannot back it up. We
consider explaining why we do not publish it to be more valuable than publishing
it.

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
- **Limited play-level information.** The independent model uses opponent-adjusted
  EPA ratings, but no finer detail such as success rate or personnel. The Elo
  baseline uses only who played whom and by how much.
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

- A quarterback availability adjustment, which our team-level ratings currently miss
- Validating our line history against a second independent source so a
  closing-line-value figure can be published
- Additional sports, each added only once we have confirmed free closing-odds
  history to grade against

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

*Last updated 2026-08-07. Baseline `elo-mov-v1`; the independent and consensus
models are walk-forward logistic ensembles, all figures regenerated by
`python scripts/published_figures.py`.*
