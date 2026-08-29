# College football

Written 2026-08-27. Week 1 kicks off 2026-08-29.

**Status.** Phase 1 shipped and live 2026-08-28, all five steps. Phase 2 shipped
except team art. Phase 3 not started and should not be started until November.

| | |
|---|---|
| Phase 1 capture | live; `data/capture/ncaaf/` accumulating, CI verified |
| Phase 1 board feed | live; CFB on `board.json`, UFC swapped out |
| Phase 2 pickers | live; rail, mobile rail, /market order, /edges labels |
| Phase 2 spreads/totals | not done, and not a defect: every sport on /market is moneyline and every card says so. `nflboard.json` (the only spread/total feed) is read by `engine/xcards.py` alone, never by a page |
| Phase 2 team art | done; 138 FBS crests read from ESPN's group-80 roster, HEAD-verified. Fixing this exposed `crest.js` fetching the map with `force-cache`, which meant no crest update had ever reached a returning visitor |
| Phase 3 model | not started. Do not start it before November |

**Endpoint claims in this document were unverified when it was written.** They
were checked against the live ESPN core API on 2026-08-28 and two were wrong or
incomplete; the corrections are inline below, marked **VERIFIED** or
**CORRECTION**. Nothing here is now an assumption.

## Why now, and why the order below is not negotiable

`engine/capture.py` opens with the sentence that decides this plan:

> a closing line we did not capture is a closing line we can never obtain.

ESPN drops the odds block when a game finishes. There is no archive and no
backfill. Every Saturday that passes without CFB capture running is a Saturday
of evidence that cannot be recovered at any price, by us or anyone. The model
can be built in November. The archive cannot be built in November.

So: **capture first, board second, model last.** The model is the interesting
part and it is the part that waits.

## What the site may claim about college football

/disclaimers §7 already governs this, and it was written before anyone thought
about CFB:

> Only NFL is graded against verified closing lines. Every other sport on this
> site carries a status label of "in calibration" or "deferred" and its
> predictions are explicitly unproven.

That is a promise already published. Shipping a CFB prediction without that
label does not just overstate the model — it makes the site contradict its own
disclaimer page, which is the exact failure this project exists to not have.

Concretely:

- CFB **line shopping** needs no label. It is arithmetic over quoted prices,
  identical in kind to what /market already does for MLB and NHL. Nobody is
  claiming a forecast.
- CFB **predictions** carry "in calibration" and are explicitly unproven,
  everywhere they appear, from the first one published.
- CFB is **not sealed into the NFL ledger**. 2026-W01-nfl is anchored and
  final; nothing here reopens it. If CFB predictions are ever sealed they get
  their own slate id (`2026-W01-ncaaf`) and their own root.
- CFB games **never enter** the NFL graded record, the NFL backtest frame, or
  anything /record, /trust or /picks reports. Two sports, two records, and the
  site says which is which.
- Any published CFB number comes out of `scripts/published_figures.py` into
  `_figures.json` like everything else. Nothing hand-typed. Same rule.

## Phase 1 — the archive (do this first, finish it before Saturday)

Goal: our own timestamped price series for CFB starts accumulating this week.

1. `engine/schema.py` — add `Sport.NCAAF = "ncaaf"`.
2. `engine/capture.py` — `CORE` is hardcoded to
   `football/leagues/nfl`. Parameterise the league and add `--sport`, keeping
   `nfl` the default so every existing caller is unchanged.

   - **CORRECTION — the output path did NOT branch on sport.** This document
     claimed `out_dir / "nfl"` already branched. It did not: both the directory
     and the `sport` field on every row were the literal string `"nfl"`, so
     college games would have been filed into the NFL series and become
     indistinguishable from it. Two hardcodings, `capture()`'s write path and
     `_extract()`'s `sport="nfl"`, both now take the sport.
   - **CORRECTION — the real truncation risk was not `limit=50`.** It was the
     missing `groups` filter, which nothing in the response advertises. The
     unfiltered week-1 endpoint returns **25** curated "featured" games; the
     same week with `groups=80` (FBS) returns **99**. Asking for a larger limit
     without `groups` would have looked entirely healthy and quietly archived a
     quarter of the season. `groups=90` would be all of Division I.
   - **VERIFIED — `limit=50` does truncate**, once `groups=80` is in play:
     2026 week 1 returns `count=99`, `pageCount=2`, 50 items on page 1. Capture
     now pages via `&page=N` until `pageCount` is exhausted, de-duplicates, and
     compares the total against ESPN's own `count`. A shortfall is reported and
     exits non-zero **after** the rows are written.
   - **VERIFIED — week/season-type numbering differs.** NFL regular season is
     `types/2` weeks 1–18. College football is `types/2` weeks 1–15, with the
     bowls under `types/3` (a single "week"), which we do not capture. College
     "week 1" is also not a week: it spans 2026-08-22 to 2026-09-08, so one
     week-ahead is a fortnight of games — 99 FBS events, 7 of them on Aug 29
     and 60 on Sep 5.
   - **VERIFIED — timing fits.** One CFB week (99 events, two requests each at
     `PAUSE = 0.25`) measured 73s; NFL at `--weeks 3` measured 37s. The
     workflow's `timeout-minutes: 20` is not close to binding.
3. `engine/lines.py` — add
   `"americanfootball_ncaaf": {"label": "CFB", "slug": "ncaaf"}`.
   This is the board build, one Odds API credit per run per sport.

   **Budget — decided by Branden, 2026-08-27: drop UFC, add CFB.** The swap
   holds the board at 5 credits per run, so no cron change and no extra spend.
   Captured UFC history stays on disk; we stop publishing it, we do not delete
   evidence. Removing UFC reaches further than `engine/lines.py` — at minimum
   `site/public/assets/desk.js`, the `--sports` list in the timeline step of
   `.github/workflows/capture.yml`, `market.html`'s sport order, the
   `SPORT_LABEL` maps in `index.html`/`game.html`/`market.html`, and any copy
   claiming UFC coverage.

   **Separately, and needing Branden's attention** — *corrected 2026-08-28,
   see the "two keys" addendum in `capture-cadence.md`:* a shell reading that
   day reported `x-requests-remaining: 120` against `x-requests-used: 380`, a
   500-credit allowance. **That is a different key from the one CI runs on.**
   The account the board actually builds against had 3,008 credits left the
   same morning.

   The original of this paragraph went on to say the 500 allowance "is why the
   live board is refreshing a few times a day rather than every 30 minutes."
   That was wrong twice over: wrong key, and wrong cause. `capture-cadence.md`
   measured the real cause the same day — GitHub drops `schedule` events, and
   every other scheduled workflow in the repo collapsed identically. At three
   runs a day the board build was nowhere near a credit ceiling on either key.

   What survives is the deadline, on the right account: 3,008 credits at 219 a
   day empties around 2026-09-11, inside NFL week 1. The swap does not make
   that worse and does not fix it. See the session report.
4. `.github/workflows/capture.yml` — capture CFB alongside NFL. One extra step,
   same commit, no extra deploy.
5. `engine/timeline.py` — `--sports nfl,mlb,nhl,nba,ufc`; add `ncaaf` once
   capture rows exist, not before, or it publishes an empty series.

   Done 2026-08-28, after step 2 had written rows. Both the module default and
   the workflow step now read `nfl,ncaaf,mlb,nhl,nba`.

   **Also found while doing this:** `data/capture` is append-only, so retiring
   UFC left its history on disk and `engine/alerts.py` kept reading it — /edges
   was publishing 232 UFC "moves" from prices nobody was refreshing any more.
   `load_observations()` now reads only the sports `lines.SPORTS` fetches.

Acceptance: a real (non-dry-run) capture writes CFB rows for this week's
games, with `provenance: own_capture`, and `bash scripts/check.sh` is green.

**Met 2026-08-28.** A live dry run returned 1,088 observations across all 99
week-1 FBS events (544 `own_capture`, 544 `espn_open`), and the NFL path was
unchanged at 48 events over 3 weeks. `tests/test_capture_ncaaf.py` pins the
grouping, the pagination, the week numbering, the de-duplication and the
per-row sport, all against fakes, so none of it depends on ESPN being up.

## Phase 2 — the board

The board renderer is already sport-agnostic; `board.json` carries a list. The
known hardcoded list is `site/public/assets/desk.js:88` (`var SPORTS=[...]`).
Find the others rather than assuming that is the only one.

- Add CFB to the sport pickers on the line-shopping surfaces.
- `engine/nflboard.py` builds spreads and totals from our own capture rather
  than from credits. Its two documented failure modes (side mapping, and
  calling one book a "consensus") apply unchanged to CFB. If it is generalised,
  its `_selfcheck` grows a CFB case; if it is not, CFB shows moneyline only and
  the page says so.
- Team names and logos: `engine/team_logos.py` and `crest.js` are NFL-shaped.
  ~130 FBS teams will include names neither one has. Missing crest must degrade
  to a readable fallback, not a broken image.

Acceptance: /market and /edges show CFB with real prices, verified in a browser
at desktop and mobile widths, and nothing NFL regressed.

**Met 2026-08-28**, in full. CFB renders on the desktop rail and the
mobile rail with live prices from 9 books; no UFC appears anywhere in the
rendered page; NFL is unchanged. Live-verified after deploy by fetching
`sooth.bet/assets/desk.js`, `/data/board.json`, `/data/moves.json` and
`/methodology`.

One thing phase 2 did not anticipate: **the schedule that feeds all of this is
firing about three times a day against a `*/30` cron, and the Odds API plan can
only afford about that many.** The two cap each other. See
`docs/plans/capture-cadence.md` - it needs a decision from Branden and is the
largest open risk to the archive this plan exists to build.

## Phase 3 — the model (only after 1 and 2 are shipped and green)

`engine/models/elo.py` is team-string agnostic and will run on CFB as-is. That
is a trap, not a feature.

- Every constant in `EloConfig` was chosen for a 32-team league with a draft
  and a salary cap. CFB has ~130 FBS teams, no parity mechanism, enormous
  talent spread, and games against unrated FCS opponents. `k`,
  `home_advantage`, `season_carryover` and `elo_per_point` must be **refit on
  CFB data**, walk-forward, and the refit reported. Reusing NFL numbers and
  publishing the output would be a fabricated model.
- History source: nflverse has no CFB. `cfbfastR-data` (sportsdataverse) and
  the CollegeFootballData API are the candidates. Whichever is chosen, the
  adapter documents its leakage boundary the way `adapters/nfl.py` does — a
  BANNED_FEATURES list, and `is_closing` set truthfully or left False.
- Same walk-forward discipline: predict season S using only seasons before S,
  isotonic calibration refit per season on prior seasons only.
- `EDGE_THRESHOLD = 4.0` is an NFL measurement. CFB's number is a different
  measurement. Measure it; do not inherit it.
- Publish the CFB backtest beside the NFL one, labeled in calibration, with
  the same honesty about whether it beats the close. If it does not beat the
  close, that is the result and it gets published as the result.

Acceptance: a CFB backtest whose figures come from `published_figures.py`, on a
page that states plainly that these predictions are unproven and ungraded.

## Out of scope

Sealing CFB predictions. Alerts on CFB. CFB props. Any comparison of the CFB
model to the NFL model. Touching 2026-W01-nfl in any way.

---

# Phase 3 — started early, partially, on 2026-08-29

**This contradicts the line above that says "Do not start it before November."**
Branden authorised the exception in session on 2026-08-29 after being shown
that line. What was authorised is narrow, and the rest of the deferral stands:

- **Done:** the history adapter and the Elo refit.
- **Not done, still out of scope:** sealing CFB predictions, any CFB slate,
  any change to `engine/pipeline/weekly.py`. The pipeline remains hardcoded to
  NFL, so nothing in this repo can publish a college prediction. That was
  deliberate — the "Out of scope" section below was not overridden.

## What shipped

`engine/adapters/ncaaf.py` — `NCAAFAdapter`, on `cfbfastR-data` schedules
(`schedules/csv/cfb_schedules_{season}.csv`, 2002-2025, no API key, so the
backtest is reproducible from this repo alone). 19,135 FBS-involved games.

`engine/models/elo.py` — `NCAAF_ELO`, the refit config. `EloConfig`'s NFL
defaults are untouched.

`scripts/refit_elo_ncaaf.py` — the refit, re-runnable, ~3 minutes.

`tests/test_ncaaf_adapter.py` — 17 tests, no network.

## The finding that constrains everything downstream

**cfbfastR-data carries no betting lines.** Not a spread, not a total, not a
moneyline, opening or closing — verified column by column against the 2024
file. Consequences, all of them forced rather than chosen:

- `load_historical_lines` returns `[]`. It does not fabricate or backdate.
- **No CLV and no ATS record can be computed for CFB from this source.** The
  `EDGE_THRESHOLD = 4.0` selectivity rule has no college equivalent, and
  inheriting the NFL number would be the fabrication this plan warns about.
- CFB cannot become "Live" on this data, by the README's own rule. It is
  in calibration, as /disclaimers §7 already promises.

Our own capture is the series that will eventually grade CFB. On 2026-08-29 it
was two days old. `current_lines` reads it; `load_historical_lines`
deliberately does not, so a 2002-2025 backtest cannot appear to have market
data for two days of 2026.

## The refit, as this plan required

Hyperparameters searched on **2002-2015 FBS-vs-FBS only**, then frozen and
evaluated once on **2016-2025**. Choosing a config by its walk-forward score
over the whole span would have made the reported score no longer out of sample.

| | NFL default | CFB refit |
|---|---|---|
| `k` | 20.0 | **36.0** |
| `home_advantage` | 48.0 | **60.0** |
| `season_carryover` | 0.75 | **0.80** |
| `elo_per_point` | 25.0 | **17.9** |

Every constant moved, in the direction the sport's structure predicts. The
plan's warning that `elo.py` "will run on CFB as-is — that is a trap" is
confirmed rather than assumed.

Frozen-config evaluation, 2016-2025:

| | n | Brier | log loss | acc | ECE |
|---|---|---|---|---|---|
| FBS vs FBS | 7,294 | 0.18816 | 0.55374 | 0.7051 | 0.02146 |
| all FBS-involved | 8,367 | 0.17118 | 0.50988 | 0.7353 | 0.01860 |

FBS-vs-FBS is the headline; the pooled-FCS games are ~11% of rows and near-free
to predict, so including them measures scheduling rather than skill.

**There is no market comparison in that table and there cannot be one from this
source.** The model is unproven against the market, not shown to beat it.
Publishing any of these numbers still goes through `scripts/published_figures.py`
per the rule above — none of them are on a page yet.

## Two defects found while building, both silent

1. **Negative rest days.** College week numbers are not chronological — a
   week-2 game can kick off before a week-1 game. Computing rest in
   (season, week) order recorded some teams' "previous" game as one not yet
   played: 157 negative values across 2002-2025, in a column nobody eyeballs.
   The pass now runs in kickoff order and asserts non-negativity.

2. **The capture join matched nothing, then matched the wrong school.** Capture
   carries ESPN's full names ("North Dakota State Bison"), cfbfastR the short
   form ("North Dakota State"), so exact matching returned `[]` for every game
   — indistinguishable from "no prices captured yet". A bare prefix rule then
   left 18 of 188 captured names ambiguous, and worse, could match uniquely and
   wrongly: "Ohio State Buckeyes" prefixes `Ohio`, so in a week where Ohio
   plays and Ohio State does not, the price files against the wrong game.
   Requiring the remainder to look like a mascot rather than a school qualifier
   leaves 4, all resolved correctly by specificity.

## What November still has to do

- Decide whether CFB predictions publish at all, and if so build the
  publishing path — `weekly.py` is NFL-only by design and was not touched.
- Measure a CFB selectivity threshold, which needs the line archive our own
  capture is accumulating. It cannot be done from cfbfastR.
- Consider an opponent-adjusted efficiency feature. The NFL model's EPA
  features have no cfbfastR schedule equivalent; the CFB feature set is
  currently Elo, rest, neutral site, conference game, division gap.
