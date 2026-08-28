# The consensus close merged rematches into one game

Written 2026-08-28 by the supervisor agent.

## What is wrong

`engine/closing.py:consensus()` reduces the paid backfill to "one consensus
closing row per game". Its grouping key is:

```python
key = ["season", "home_abbr", "away_abbr"]
```

That is not a game. It is a **matchup**. When two teams meet twice in one
season — a regular-season game and a playoff rematch — both games fall into one
group and the function takes the median closing price across all of them. The
backfill holds 855 games; `consensus()` returns 841 rows. The missing 14 were
not dropped, they were **blended**.

The blends are not small. Fourteen matchups, with their two real closes:

| season | game | close (home) |
|---|---|---|
| 2025 | SF @ SEA, week 1 then week 20 | +112 then −300 |
| 2024 | HOU @ KC, week 16 then week 20 | −184 then −570 |
| 2023 | MIA @ KC, week 9 then week 19 | −114 then −240 |
| 2024 | GB @ PHI, week 1 then week 19 | −128 then −270 |

In the first row the favourite is a different team in the two games. The median
of those two prices was never anybody's closing line, and it is the number a
week-1 prediction was being graded against.

## How far it reached

**1. The line-provenance figure on /methodology.** `compare_to_nflverse` merges
`cons` into nflverse on the same three columns. Because the key is not unique on
either side, the merge fans out: each of the 28 rematch games matches the one
blended row, so `matched_games` comes back to 855 while 28 of those rows carry a
close that belongs to neither game. The published figures move:

| figure | published | correct |
|---|---|---|
| spreads that differ from nflverse | 32.9% | 31.5% |
| mean absolute difference | 0.217 pts | 0.180 pts |
| differ by a full point or more | 5.5% | 4.4% |

The error runs in the direction that **flatters us**: it makes nflverse's
`spread_line` look further from the real close than it is, which is the whole
argument for having bought the backfill in the first place.

**2. Evaluation B on /methodology** — the smaller, better-provenance sample the
page calls "the better evidence". `published_figures.py` merges `frame` into
`cons` on the same three columns, with the same fan-out. Every ATS record in
that table is computed against `close_spread`, so every one of them is wrong:

| model | published | correct |
|---|---|---|
| elo | 402-431-21 (48.26%) | 398-435-21 (47.78%) |
| independent | 404-429-21 (48.50%) | 401-432-21 (48.14%) |
| consensus | 414-419-21 (49.70%) | 411-422-21 (49.34%) |
| market benchmark | 414-419-21 (49.70%) | 416-417-21 (49.94%) |

Again in the direction that flatters us: every model of ours gets worse and the
market benchmark gets better. `n` stays 854 and Brier, log-loss, accuracy and
ECE are unchanged — those read probabilities, not the close. Nothing crosses
the 52.38% break-even in either version, so no published claim reverses; the
site still says nothing beats the close. It now says it with the right numbers.

## The fix

1. `consensus()` groups by `event_id`, which is one game, and carries `week`
   through. The backfill's 68,120 rows map 1:1 onto 855 event_ids and each
   event_id has exactly one (season, week, home, away), verified before the
   change. The function asserts that, so if the assumption ever breaks it
   breaks loudly instead of silently averaging two games again.
2. `compare_to_nflverse` and `published_figures.py` merge on
   season + week + home + away, which is unique on both sides. A merge that can
   fan out is the mechanism here, not a detail of it.
3. `tests/test_closing_consensus.py` builds a fixture containing a rematch and
   fails if the two games come back as one row, and asserts the merge key is
   unique so a future fan-out is caught at the key rather than in a figure.
4. Regenerate `_figures.json` and `figures.json`, rebuild the site. Every
   affected number on /methodology is already a `{{fig:}}` token, so nothing is
   retyped by hand.

## Why this was invisible

`matched_games` came back as 855 both before and after, because the fan-out
restores exactly the count the blending removed. Every count on the page
therefore looked right. Only the values inside 28 of the rows were wrong, and
nothing compared them to anything. This is the "check the payload, not just the
HTML" lesson one level deeper: the payload was the right *shape*.
