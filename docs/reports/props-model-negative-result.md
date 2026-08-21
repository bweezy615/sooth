# Prop models: a negative result

*2026-08-20. Strikeouts (`kpoisson-v1`) and total bases (`tbconv-v1`).*

We built a second prop model, backtested both, and found that neither produces
a publishable edge. This is the write-up. It is here rather than in a commit
message because the useful part is not the conclusion, it is the four wrong
explanations we passed through on the way to it.

## The headline

Measured on the population these models would actually deploy on — the 194
pitcher-games that reached a real board with 3+ two-sided books, real lines,
real de-vigged prices, known outcomes:

```
kpoisson-v1     predicted 46.4%   actual 43.3%   market 48.6%
                mean |delta| vs market        11.5 pts
                |delta| >= 3 on               156 of 194 props
                our side wins those           75/156 = 48.1%
```

The model disagrees with the market by 11.5 points on average and wins 48.1%
of those disagreements. **The magnitude is what falsifies it.** This is not an
edge too small to measure; it is a large claimed edge that does not appear.

On statistical power, stated so nobody rounds it off later: n=156, SE about 4
points, so 48.1% is within noise of 50% and we cannot claim the model is
negatively skilled. What this sample excludes is the edge an 11.5-point
average delta implies.

## The finding worth keeping

The models carry real information on all pitcher-starts and effectively none
on the subset books choose to post. Platt slope of outcome on the model's own
log-odds — 1.0 would mean already calibrated, 0.0 means the output carries no
information:

```
general population (all starts)   n=1482    B = 0.483
board population (real props)     n= 194    B = -0.070   95% CI [-0.50, 0.35]
```

Books do not hang props uniformly. They post the marquee starter and the
televised game, and our own board filter compounds it by requiring 3+ books on
both sides — so a prop appears only where several books independently chose to
price it. That is the subset the market has thought hardest about. **Our edge
exists where no market exists.**

The same effect in calibration terms:

```
kpoisson-v1 worst bucket, general population (after slope fix)    2.6 pts
kpoisson-v1 worst bucket, board population                       18.5 pts
```

Every figure quoted before we reconstructed the board population was measured
on an easier sample than the real one. **This failure mode is not specific to
props.** It will recur anywhere in this repo that validates a model against all
available history rather than against what actually reached a board.

## Four explanations, three of them wrong

Kept because each was confidently stated before it was tested.

**1. "Per-player error of ±3.5 points swamps the deltas."** Measured
in-sample and over-read. Done properly — walk-forward, with the binomial
sampling floor separated out — per-player deviation in both models is entirely
consistent with sampling noise (observed SD 10.01 against a noise floor of
12.43 for K; 4.75 against 5.08 for TB). Per-player calibration is not
measurable at 15–25 starts or 100–150 games per player, in either direction.
Withdrawn.

**2. "Plug-in tail probabilities ignoring parameter uncertainty."** The fix
would have been a negative-binomial predictive. Fitted it: r = 180, residual
variance 5.49 against a Poisson 5.32. There is essentially no over-dispersion.
Worst bucket moved 16.9 → 15.8. The variance family was never the problem.

**3. "Shrink the rate toward league, weighted by sample size."** Empirical
Bayes on K/BF. Worse on every measure (worst bucket 28.2, win rate 40.5%). The
diagnostic matters more than the failure: fitting tau to drive the slope to 1.0
ran to the ceiling of the search at 4000 batters faced and the slope still only
reached 0.689. Shrinking the rate cannot fix the slope at any strength, which
rules out the whole branch rather than one setting of it.

**4. What survived.** The defect is in the mean, not the variance. Held-out
regression of actual on projected gives slope 0.631 for strikeouts and 0.214
for total bases — the projections move further than reality does. For total
bases, 0.214 also says only about a fifth of the model's spread between batters
is real. Separately, the recency weighting is actively harmful: season K/BF
beats the last-5 blend on both slope (0.718 vs 0.631) and MAE (1.9054 vs
1.9264), and last-5 alone is worst of all (slope 0.510). The noise enters
through expected batters faced, the one input built from a recency-weighted
last five starts.

## Why there is no research number either

An honest P(over) beside the market's is legitimate for the site even when it
does not beat the price. We tried to produce one. Fitting a Platt
recalibration on half the board props and testing on the other half:

```
kpoisson-v1              worst bucket 22.4   brier 0.2800
+ Platt recalibration    worst bucket  2.7   brier 0.2480
the market itself        worst bucket  4.1   brier 0.2439
```

The recalibration works, and it works by discarding the model: the fitted map
compresses every input to a near-constant 42%, and all 94 held-out props land
in a single bucket. A calibrated `kpoisson-v1` on real board props is a
constant wearing a model's clothes. Publishing it would be publishing the base
rate with extra steps.

## Status

- Neither market is cleared to post. The Discord's postable list is empty and
  that is the correct permanent state on current evidence.
- `tbconv-v1` is not wired into the live board.
- `kpoisson-v1` remains as-is. It is overconfident by up to 18.5 points
  in-bucket on the props that actually reach a board, and nothing consumes its
  output.

## If someone reopens this

The bar is a validation population that reaches a board, not a season of game
logs. Anything measured on all-available-history is measuring the easy case.
The one number that would change the conclusion is a board-population Platt
slope meaningfully above zero, on a sample larger than 194.

Two things we did not find, recorded so they are not rediscovered as news:

- The market predicted 48.6% against a 43.3% actual on this sample, a +5.3
  point gap. n=194, about 1.5 sigma. That is noise, not a discovered bias.
- The total-bases slope of 0.214 points the same way as everything else, but
  it was never tested on a board population — total bases had only 160 captured
  quotes against 3207 for strikeouts.
