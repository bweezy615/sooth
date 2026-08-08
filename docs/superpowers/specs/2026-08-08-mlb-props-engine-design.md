# Sooth Props Engine — Slice #1: MLB player props

**Date:** 2026-08-08
**Branch:** `exec/props-engine`
**Status:** Design approved, spec for review.

## Purpose

Add predictive **player-prop picks** to Sooth, starting with MLB pitcher
strikeouts. Unlike Sooth's existing line-shopping edge (best price vs de-vigged
fair line — no prediction), this engine **forecasts a player outcome** from
per-player analytics and takes a position against the book's prop line.

Because that is a genuine predictive claim — the exact thing Sooth's honesty
charter forbids advertising until proven — the engine runs **in the dark** and
publishes nothing until sealed picks clear a pre-registered beat-close bar.

## Honesty constraints (non-negotiable, inherited from Sooth charter)

- Graded and marketed on **% beat-the-close only**. Never a win-rate, "locks,"
  or profit claim. Actual over/under result is captured for *internal model
  calibration only* and never surfaced as a public flex.
- Banned words enforced end-to-end: guaranteed / lock / risk-free / insider /
  sure thing.
- Every published pick carries the sealed Merkle root (proof we committed before
  first pitch) + the analysis-only / 1-800-522-4700 / 21+ compliance line.
- Props stay invisible on the board and in premium until the gate below clears.

## Scope (this slice)

**In:** MLB **pitcher strikeouts** (`pitcher_strikeouts`) only. One closing-line
capture per game per day. Model → seal → grade pipeline, running internally.

**Deferred (not this slice):** Batter props (`batter_hits`, `batter_total_bases`)
— they roughly double Odds API credit cost and are noisier; add them when Branden
moves to a paid Odds tier. NBA/NFL props — different season, different models.

**Budget constraint driving scope:** current free/low Odds API tier (~500
credits/mo). Prop lines are fetched per-event (`/events/{id}/odds`), ~1 credit
per market per game. Pitcher K's for ~15 MLB games × 1 closing snapshot/day
≈ 15 credits/day ≈ 450/mo — fits. A second market or second daily snapshot
would blow the free tier, hence K's-only, close-only.

## Architecture — reuse the existing spine, add three subsystems

The engine already has: `capture.py` (append-only evidence), `commit.py`
(Merkle sealing), `grade.py` (CLV grading), `publish_plays.py` (gated Discord
delivery). Props plug into this spine. **No rebuild.**

### Subsystem 1 — Prop-line capture (`engine/props_capture.py`) — BUILD FIRST

Prerequisite: you cannot validate beat-close without weeks of captured prop
closes. This runs from day one, before any model exists.

- Fetches `pitcher_strikeouts` from The Odds API per-event endpoint for MLB.
- Captures the **closing** line per game — the last snapshot before that game's
  first pitch (games start at staggered times → several small per-event calls
  through the day, ~15 credits total).
- Appends to `data/capture/mlb-props/YYYY-MM-DD.jsonl`, append-only, same
  evidence discipline as game lines. Never mutate or delete a captured line.
- Credit-capped via config (`max_credits`-style ceiling); refuses to exceed it.

### Subsystem 2 — Predictive model (`engine/models/mlb_props.py`)

Inputs from **free** sources (no API cost): MLB StatsAPI (`statsapi.mlb.com`,
no key) for schedule / probable pitchers / box scores; Baseball Savant /
pybaseball for pitcher K%, opponent team K% by handedness, park factors.

- **Pitcher K's model:** projects a strikeout distribution per start (inputs:
  pitcher K% or K/9, opponent lineup K% vs pitcher handedness, park factor,
  expected batters faced / pitch-count ceiling) → a model **fair line** + an
  over/under probability.
- Deterministic given fixed inputs (testable). Model is intentionally simple
  first; sophistication only after the pipeline proves out.

### Subsystem 3 — Select → seal → grade (reuse `commit.py` + `grade.py`)

- Compare model fair line vs the current book prop line → edge candidates
  (positions where the model thinks the book is mispriced).
- Select top N → **Merkle-seal before first pitch** via `commit.py`.
- After games settle: grade each sealed pick on
  1. **beat-close** — did our sealed line beat the captured closing prop line?
     (the honesty metric, the only public number) and
  2. actual K result vs the line (internal calibration only).
- Append graded results to an internal props record.

## The validation gate (success criteria)

Props remain dark (capture + model + seal + grade, internal only) until sealed
picks clear a **pre-registered** bar. Proposed: **≥54% beat-close over ≥100
sealed picks across ≥3 weeks** (Branden sets the final bar before go-live; the
bar is registered in the record before it is measured, not moved to fit
results). Only on clearing does props visibility flip on for board + premium.

## Data flow (daily)

1. `props_capture` → append closing K's lines to `data/capture/mlb-props/`.
2. `mlb_props` model (from free stats) → fair line per probable pitcher.
3. select + seal (before first pitch) → Merkle root committed.
4. games play → `grade` beat-close + actual → append to internal record.
5. when the gate clears → props go visible (board + gated premium via the
   existing `publish_plays` pattern).

## Testing

Unit tests per subsystem, same TDD discipline as the current 51 tests:
- capture: parse a fixture Odds API prop payload → correct append rows; credit
  ceiling refuses over-budget calls.
- model: deterministic projection on fixed stat inputs; sane bounds.
- select/seal/grade: fixture picks seal to a stable Merkle root; beat-close
  grading math is correct on known close vs sealed lines.

## Open items (resolve before/at plan time)

- Exact free-tier credit ceiling and MLB game count on a typical day (size the
  per-day capture precisely).
- Final beat-close gate numbers (%, sample size, window) — Branden's call.
- Whether pybaseball is an acceptable dependency or we hit Baseball Savant
  endpoints directly.
- Closing-snapshot timing: fixed cutoff (e.g. T-10 min) vs. last-seen-before-lock.
