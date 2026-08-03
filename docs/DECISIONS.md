# Decisions & Findings

Living record of what we chose and, more importantly, what the data forced us
to change. Written so that a decision is never quietly reversed later.

Last updated: 2026-08-02

---

## Deadline

**NFL Week 1 kicks off 2026-09-09 (NE @ SEA).** Everything below is scoped
against that date.

---

## Positioning

**We sell transparency, not edge.**

This was not the original plan. The original plan was to mirror the
competitor: a subscription selling high-confidence picks. Our own backtest
killed that premise (see Findings), so the product changed rather than the
claims.

- Free tier: committed predictions, calibrated probabilities, public graded
  record shown side by side with the market's record.
- Paid tier: **tools and data, explicitly not picks.** No-vig calculators,
  line-movement alerts, historical CLV lookups, model exports.
- We make **zero performance claims**, which means zero FTC substantiation
  burden. This is a deliberate legal posture, not modesty.

Banned from all copy: *guaranteed, lock, risk-free, insider, sure thing.*
Also banned: any win-rate or ROI claim we cannot reproduce from the public
ledger on demand.

---

## Findings that shaped the build

### 1. The baseline model does not beat the market

Walk-forward, 2,750 out-of-sample games (2016-2025), no leaked features:

| metric | model | market (de-vigged) |
|---|---|---|
| Brier | 0.22228 | 0.21061 |
| log loss | 0.63535 | 0.60863 |
| SU accuracy | 63.96% | 66.58% |

ATS record: **1333-1352-65 (49.65%)** against a 52.38% breakeven.

The NFL closing line is among the most efficient markets that exists. A clean
Elo baseline losing to it is the expected result, not a bug. The value of
knowing this is that we learned it privately, before launch, instead of
publicly in Week 6 with subscribers watching.

**Consequence:** we cannot honestly sell "we beat the market" at any price.

### 2. Calibration is our one real, defensible asset

| metric | raw | calibrated | market |
|---|---|---|---|
| ECE | 0.02654 | 0.02162 | 0.01802 |
| Brier | 0.22228 | 0.22323 | 0.21061 |

Isotonic calibration improves ECE ~18% but slightly *costs* sharpness. Both
numbers get published. A calibrated probability is a claim we can actually
substantiate; profitability is not.

### 3. High-confidence picks are the least trustworthy

| bucket | n | predicted | actual | gap |
|---|---|---|---|---|
| 0.7-0.8 | 244 | 73.66% | 72.54% | +0.011 |
| 0.8-0.9 | 210 | 84.77% | 82.86% | +0.019 |
| 0.9-1.0 | 60 | 94.51% | 86.67% | **+0.078** |

The competitor's entire product is "one highest-confidence pick per day" -
exactly the band where the model is most overconfident.

**Consequence:** cap published confidence (~85%) and explain the cap on the
methodology page. The explanation is itself marketing.

### 4. Leakage is the real technical risk, not data availability

nflverse columns that are NOT knowable pre-kickoff and are banned from
features (enforced by assertion in `adapters/nfl.py`):

- `temp`, `wind` - measured at/after the game, not forecasts
- `away_score`, `home_score`, `result`, `total`, `overtime` - the outcome
- `spread_line` et al. are **overwritten in place** as the market moves, so
  they are only treated as closing for FINAL games, and CLV must be validated
  against ESPN's explicit open/close objects before any CLV figure is
  published.

A model trained on post-game weather backtests beautifully and loses live.
This is how tout-site "models" are accidentally (or deliberately) built.

---

## Category assessment

We audited the leading paid "AI picks" subscription services in this category
before building. Detailed per-company notes are kept out of this repo by
policy; the generalisable conclusions:

- **The technical barrier is roughly a weekend.** These are typically a static
  marketing site plus a scheduled job that asks a language model for a pick
  and a confidence number. That architecture cannot produce calibrated
  probabilities, which is the one thing their marketing promises.
- **"Public ledger" is usually a claim, not a page.** Advertised results pages
  frequently 404, and displayed "verified" receipts are often labelled as
  samples in small print.
- **Nobody publishes their record against the closing market**, because doing
  so would make the advertised edge falsifiable.

**The one practice worth copying:** allow-listing AI crawlers in `robots.txt`
to be cited by AI search engines. It is free and it works. The difference in
our case is that what gets cited is reproducible from the ledger.

This is the opening. The scarce asset in this category is not a model - it is
a record that can be checked.

---

## Compliance posture

Derived from legal research, 2026-08-02.

1. **Never touch wagers, funds, or prizes.** This single fact keeps us a
   publisher rather than a gambling operator, and keeps us inside Stripe's and
   Paddle's acceptable-use policies and outside Apple 5.3.4.
2. **FTC substantiation is the binding constraint, not gaming law.** No state
   currently licenses tout services. Objective performance claims require
   pre-existing competent and reliable evidence; "AI" branding puts us inside
   Operation AI Comply's stated target zone.
3. **Web-first.** Own Stripe checkout, no App Review, no platform fee. Native
   app later as a retention surface.
4. **Android caveat:** Play policy forbids sportsbook ads inside an app that
   also provides odds/score tracking. Affiliate ads and an odds product are
   mutually exclusive there - pick one.
5. **Subscription mechanics:** separate affirmative consent, one-click
   same-medium cancel, renewal reminders (ROSCA + California AB 2863).
6. Responsible-gambling helplines: name both the CCGNJ line and the NCPG line
   (1-800-522-4700); the old single-number guidance is out of date.

The immutable pick log does triple duty: differentiator, FTC substantiation
file, and chargeback defence.

---

## Multi-sport plan

One sport-agnostic engine; each sport is an adapter implementing
`adapters/base.py`. Sports ship with an honest status badge:

- **Live** - real backtestable model graded against verified closing lines
- **In calibration** - predictions published, flagged as unproven
- **Deferred** - insufficient free data to grade honestly

A sport is never marked Live without confirmed free closing-odds history.
Tier assignment pending multi-sport data research.

---

## Brand

**Sooth** — archaic English for *truth* ("in sooth"), and the root of
*soothsayer*, one who foretells. Truth and prediction in one syllable.

Canonical domain `sooth.co` (`.com` unavailable). `getsooth.com` is taken
since 2022; `getsooth.co` reserved as a redirect. Bare `@sooth` is taken on
GitHub, Reddit, Instagram, TikTok and YouTube — standard handle is
**`@soothhq`**.

---

## Capture: the archive is for backtesting, our capture is for grading

Live since 2026-08-03. `engine/capture.py`, every 3 hours.

ESPN exposes `open` and `current` for unplayed games only. Once a game
finishes the odds block disappears and **cannot be backfilled**. Every hour
not captured is evidence permanently lost — this is why capture was built
before the site.

`provenance` is a first-class column on every row:

- `own_capture` — we observed it ourselves at `observed_at`. **Gradeable.**
- `espn_open` — ESPN's claim about the past. Recorded, never graded on.
- `espn_close` — ESPN's close block. Last poll it happened to take, not
  authoritative.

Public CLV claims may only be computed from `own_capture` rows.

**Runs on GitHub Actions**, not locally — `.github/workflows/capture.yml`,
every 3 hours. Verified end to end 2026-08-03: GitHub's runner captured odds
and committed them autonomously (commit `cf54ae3`, 572 rows).

The commit timestamp is the point. GitHub attests that we held a given price
at a given time, which is what makes a closing-line-value claim auditable
instead of asserted — the same role the Merkle root plays for predictions.

The local launchd agent was **deliberately disabled** (kept at
`scripts/co.sooth.capture.plist.disabled`). It appended to the same file the
Actions runner commits, which would have produced rebase conflicts every time
the laptop woke. Actions is strictly better: it runs while the laptop is off.

Known limit: single book (DraftKings) via ESPN. Multi-book needs The Odds API.

---

## Open items

- [x] Decide brand name
- [x] Tier list for the other 8 sports
- [x] Odds capture running
- [ ] **Push repo to GitHub** — makes capture durable and gives commit
      timestamps as third-party attestation
- [ ] Register `sooth.co` + `getsooth.co`; claim `@soothhq`
- [ ] Buy 1 month of The Odds API; backfill 2020-2025 closes; re-run the
      backtest (the 49.65% ATS figure used nflverse lines now known to
      disagree with documented closes on 27.8% of 2024 spreads)
- [ ] Swap `example.com` for `sooth.co` in robots.txt + sitemap.xml
- [ ] Model upgrade path: EPA-based ratings, QB adjustment, market blending
- [ ] Stripe onboarding with explicit written business description, non-7995 MCC
- [ ] MLB stays out of the paid tier until its source licence is reviewed
