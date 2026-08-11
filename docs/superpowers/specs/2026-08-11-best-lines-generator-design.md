# Spec: best_lines.json generator

**Date:** 2026-08-11 · **Owner:** Branden (solo) · Approved design.

## Problem
`predictor.html` fetches `/data/best_lines.json`, frozen at `generated_at 2026-08-04`.
No generator ever existed — it was a one-time static drop (commit fdc314888). Build the
generator + schedule it so the Predictor stops being stale.

## Approach: pure join, zero new Odds-API calls
`best_lines.json` = join of two files the pipeline already maintains:
1. **Picks + confidence** — latest weekly slate. `slates.json.latest` → `{slate}.json` →
   per-game `independent` block (`pick`, `prob`). `our_prob` = **independent** model
   (market-blind, honest; matches the frozen file; what /methodology sells). NOT consensus.
2. **Prices** — `board.json`, the board where `sport == "nfl"`. Each `events[].sides[]`
   already carries `quotes[]`, `best_price/book`, `worst_price/book`, `n_books`, `gain_pts`.

Coverage decision (Branden, 2026-08-11): **join board.json only, 0 credits.** board.json
holds games within a 36h window of kickoff, so the Predictor fills in game-by-game through
the week (sparse early, full by Sunday). Sparse early week is expected and correct.

## Join
- Board side names are full club names; slate picks are abbrevs. Reuse
  `engine/closing.py::TEAM_MAP` (full name → abbrev). Do NOT rebuild the map.
- Match board event ↔ slate game by (home_abbr, away_abbr).
- Take the side whose abbrev == the slate `pick`. Copy that side's
  `quotes`, `best_price/book`, `worst_price/book`, `n_books`; set `edge_pts = side["gain_pts"]`.
- Emit only games present in BOTH files.

## Output schema (match the frozen file exactly)
```
{ generated_at, slate_id, source, note,
  games: [ { game_id, away, home, kickoff, pick, our_prob, best_price, best_book,
             worst_price, worst_book, n_books, edge_pts, quotes:[{book,price}] } ],
  avg_edge_pts, max_edge_pts, n_books }
```
- `source`/`note`: copy the frozen strings.
- Atomic write to `site/public/data/best_lines.json`, mirroring `engine/lines.py` write style.
- Module runs as `python -m engine.best_lines`.

## Self-check
`demo()`/`__main__` assert: join on current files yields schema-valid games AND
`edge_pts` == recomputed `(worst_implied − best_implied) × 100` (raw american implied prob)
within rounding. No test framework.

## Wiring
One step in `.github/workflows/capture.yml` AFTER `engine.lines`, and add
`site/public/data/best_lines.json` to the `git add`. Zero API cost — reads the file
`engine.lines` just wrote. Don't break existing capture/board/props steps.

## Guardrails
- Solo project, engine edits fine. Test locally before wiring.
- Build + local-verify + commit to a **feature branch**. Do NOT push to main.
  No unattended deploy. Final merge + scheduled-run verification is Branden's.

## Out of scope (flagged, not done)
`weekly.py` isn't auto-scheduled — advancing to Week 2+ needs a manual
`python -m engine.pipeline.weekly`. best_lines just reads whatever `latest` slate exists.
