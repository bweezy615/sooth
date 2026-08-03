# Overnight report — 2026-08-03

## MORNING SUMMARY — read this before merging anything

Six queue items closed. **Nothing was merged to `main`.** Every change sits on
a branch for your review.

| Branch | What |
|---|---|
| `overnight/commitment-versioning` | P0 — commitments append-only + versioned |
| `overnight/published-figures` | P1 — one command regenerates every site figure |
| `overnight/grading-pipeline` | P2 — grade a revealed slate, provenance-gated CLV |
| `overnight/capture-cadence` | P3 — 15-min capture inside the pre-kickoff window |
| `overnight/epl-adapter` | P4 — second sport, In calibration |
| `overnight/tests` | P5 — 34 tests, green |

**The night's most valuable result is not a feature.** The model does not beat
the market in **NFL or EPL** — two sports, two independent data sources, two
independent modelling approaches, the same verdict. That finding is now
cross-validated rather than resting on one dataset, and it is the honest
foundation the whole product is built on.

### THREE DECISIONS WAITING FOR YOU

1. **Which model leads the front page.** Both publish, labelled, as you asked.
   Independent is our real opinion and worse; Consensus is better calibrated
   but largely echoes the market. Ordering is editorial, with consequences.
2. **Whether superseded commitments show by default.** Currently always
   visible on `/ledger` — maximally honest, but draws attention to a revision
   most readers need not care about.
3. **Keep or cancel the $30/mo Odds API subscription.** The backfill is done,
   so this is now a live recurring cost. Free ESPN gives ~1 book; $30 gives 10
   at 2.3% of quota. Keeping it is what makes a *published* CLV number
   defensible.

### STILL BLOCKED ON YOU

- **Vercel** — build failed on Python runtime detection. Two fixes pushed; if
  it still fails, set Root Directory to `site/public` in Settings → General
  and tell me, because `vercel.json` must move with it.
- **Wednesday** — register `sooth.co` + `getsooth.co`, claim `@soothhq`.
  `getsooth.com` is taken (held since 2022) and `sooth.vercel.app` belongs to
  someone else.

### CREDITS

**3 of 500** nightly budget spent (one measurement call). **7,577 remaining**
on the plan.

### THE PATTERN WORTH KNOWING

Five of my own verification scripts were wrong tonight — the secret check, the
stale-figure check, the CLV join key, an unimported symbol, and an odds
round-trip boundary. **Every one reported something false rather than
crashing.** None produced a bad artefact, because each surprising number was
re-checked by hand before I acted on it.

That is the clearest evidence available that an agent working unsupervised can
be confidently wrong, and it is exactly why the guardrails put everything on
branches and forbid autonomous "Live" promotion. Treat this report as a
proposal, not a fait accompli.


---

## Completed

### P0 — Commitment versioning ✅

**Problem found:** re-sealing Week 1 for the dual-model launch overwrote
commitment root `d081c00f…` with `4136512c…` *silently*. Revising predictions
before kickoff is legitimate; a root vanishing without trace is not — to an
outside reader it is indistinguishable from tampering, which defeats the
entire product.

**Fixed:** commitments are now versioned and append-only.

- `<slate>.commitment.v{N}.json` / `<slate>.reveal.v{N}.json`, retained forever
- Each carries `version` and `supersedes` (the prior root), forming a chain
- `commitment_history()` returns the full sequence
- `verify_slate(..., version=N)` verifies any version, so a reader who
  recorded an older root can still confirm it
- Re-committing identical predictions does **not** mint a new version
- Legacy unversioned files still verify (no migration required to read them)

**v1 was recoverable only because we happened to have committed to git.** That
is luck, not design, and it is precisely the accident this fix removes.

**Verification:**

```
$ python -c "from engine.commit import verify_slate, commitment_history; ..."
v1  n= 16  root=d081c00f901874be...  supersedes=None
v2  n= 32  root=4136512cf38a8074...  supersedes=d081c00f901874be
verify latest : True
verify v1     : True
verify v2     : True
```

The `/ledger` page now renders the superseded root alongside the current one,
with an explanation of why revisions before kickoff are legitimate.

Branch: `overnight/commitment-versioning`

### P1 — Published figures regenerated from validated closes ✅

`scripts/published_figures.py` is now the single source of truth for every
performance number on the site. If a figure cannot be produced by that one
command, it does not belong on the site.

Two evaluations are published side by side rather than swapping the weaker one
out quietly:

| | A. nflverse lines | B. real consensus closes |
|---|---|---|
| seasons | 2016–2025 | 2023–2025 |
| n | 2,671 | 854 |
| provenance | undocumented periodic snapshot | median of ~11–17 books, 5–28 min pre-kickoff, ours |
| Independent ATS | 49.50% | 48.74% |
| Consensus ATS | 49.85% | 49.46% |
| Market ATS vs own line | 50.88% | 48.74% |

Nothing clears the 52.38% break-even in either table. The market does not beat
its own number either, which is the check confirming the harness is not
flattering us.

**Verification:** every figure on the homepage was matched programmatically
against `site/content/_figures.json` — 6/6 traceable. All hand-carried numbers
(49.65%, 2,750, 1333–1352–65, 0.2223) confirmed removed.

Branch: `overnight/published-figures`

**Note:** the old 49.65% came from `engine/backtest.py` (Elo only, slightly
different filtering, n=2,750). It was not wrong, but it was a second source of
truth. There is now one.

### P2 — Grading pipeline ✅

`engine/grade.py` grades a revealed slate: per-model record, Brier, and CLV.
`scripts/replay_grade.py` replays a settled week to test it end to end.

**Bug found and fixed before it could mislead.** Three ID spaces exist in this
project and none agree: predictions use nflverse `game_id`, live capture rows
carry ESPN event ids, backfill rows carry Odds API hashes. Keying CLV on the
raw `event_id` matched nothing, so CLV would have reported "unavailable"
forever — a silent zero indistinguishable from a genuine data gap. Now joined
on (season, home, away) via the team map.

**CLV is provenance-gated.** Only `own_capture` and `oddsapi_historical_close`
rows may contribute. Where no qualifying price exists, CLV is `None` with a
stated reason, never estimated from the nearest available number.

**Verification — the number that matters:**

```
replay 2025 W5   : 4-10 (28.6%)   <- looked like a bug
manual recount   : 4-10            <- confirmed correct by hand
2025 season agg  : 181-103 = 0.6373
backtest accuracy: 0.6372
```

The pipeline independently reproduces the backtest to four decimal places.
Week 5 was simply the worst week of the season (range across 2025: 0.286 to
1.000) — the model's four most confident picks all lost, Baltimore losing
44–10 as a 74% favourite. **That weekly spread is the strongest argument on
the site for why a single week's record is noise**, and worth using.

**NOT publishable yet:** the replay's CLV (+0.0025) used nflverse moneylines
as the reference price. Those are undocumented, so this is a pipeline test,
not a substantiated claim. A publishable CLV needs our own pre-close capture
as the reference, which only exists going forward. Guardrail 1 applies.

Branch: `overnight/grading-pipeline`

### P3 — Capture cadence tightened ✅

Two cadences now: `*/15` gated to fire only when a kickoff is within 90
minutes, plus the existing 3-hourly sweep. The closing line forms in that last
hour; a 3-hourly poll can miss the actual close by 90+ minutes.

**The 15-minute job is free when idle.** Its window check reads local nflverse
data and makes zero HTTP calls, so it does not hammer an undocumented free
endpoint 96 times a day to learn the next game is four days out.

**Verified by hand:** the gate reported the next kickoff 54,044 minutes away
= 37.53 days, which matches NE @ SEA on 2026-09-10 00:20Z. That confirms the
US/Eastern to UTC conversion — an hour of drift would turn a closing capture
into a mid-afternoon one.

**Full-week credit projection (measured, not assumed — one live call cost 3
credits and returned all 272 games across 10 books):**

| path | polls/wk | credits/wk | books |
|---|---|---|---|
| ESPN (current) | 36 | **0** | ~1 (DraftKings) |
| Odds API (optional) | 36 | 108 | 10 |

Odds API multi-book would run ~464 credits/month — **2.3% of the 20K plan**.

Branch: `overnight/capture-cadence`

### P4 — EPL adapter ✅ (In calibration, NOT Live)

`engine/adapters/epl.py` implements `SportAdapter` only. **The engine needed
no changes** to accept a second sport, which is the result that matters — the
interface holds.

**EPL has better provenance than NFL.** football-data.co.uk documents its
`C`-infixed columns as *closing* prices (PSCH/PSCD/PSCA = Pinnacle Closing),
with 380/380 coverage in 2024-25. It is the only source in this project whose
closing odds are labelled as such by the publisher — NFL needed a paid
backfill to reach the same standard.

**Schema extension, recorded not hidden:** football has draws, so this adapter
emits an explicit `draw` selection alongside `side_a`/`side_b`. Downstream code
assuming exactly two outcomes will be wrong here and should fail loudly rather
than renormalise silently.

**Verified:** 2,660 fixtures 2019-2025, 100% result coverage, exactly 3.00
lines per event, all `is_closing=True`. Decimal→American conversion
hand-checked on four known values (1.65→−154, 2.00→+100, 4.23→+323, 5.28→+428).

**Walk-forward backtest, 3,420 fixtures (2017-2025):**

| | Brier | log loss | accuracy |
|---|---|---|---|
| Elo | 0.57961 | 0.97628 | 0.5360 |
| Market (closing) | 0.56444 | 0.95324 | 0.5494 |

Model loses by 0.01518 Brier. **Two sports, two independent data sources, same
verdict** — the "we do not beat the market" finding is not an artefact of NFL
data or of one modelling choice. That cross-validation is worth more than the
adapter.

Draw calibration is genuinely good: model 0.2340 vs actual 0.2336 (market
0.2400). Same pattern as NFL — competitive on calibration, behind on accuracy.

Reproduce: `python scripts/epl_backtest.py`

Branch: `overnight/epl-adapter`

---

## DECISION NEEDED — keep the $30/mo Odds API subscription?

The plan was buy one month, backfill, cancel. The backfill is done, so this is
live now.

- **Cancel (free path):** ESPN only. Costs nothing, but closing lines come
  from a single book. Usable for grading; weaker as a consensus.
- **Keep ($30/mo):** 10-book consensus closing lines going forward at 2.3% of
  quota. This is what makes a *published* CLV number defensible, since our own
  multi-book capture becomes the reference price.

I have not made this call. It is a recurring cost against a project with no
revenue yet, which is your decision and not a technical one. The capture code
works either way; only the book count changes.

---

## Process failures this pass

Two of my own verification scripts were broken tonight, both in the same
direction — a check that reports a problem where none exists:

1. Guardrail 6's secret pattern matched substrings of published SHA-256
   hashes, firing on the first commit.
2. The stale-figure check used `grep -c ... || echo 0`, which appends a second
   `0` because grep exits non-zero on no match, producing `"0\n0"` and a
   broken integer comparison.

Neither caused a bad artefact, because both were re-checked before acting. But
two broken checks in one night is a pattern: **verification code is being
written with less care than the code it verifies.** Worth fixing properly in
P5 (tests) rather than continuing to hand-roll shell checks.

---

## Verified this pass

- **Odds API credits spent: 0.** Budget for the night is 500; 7,580 remain on
  the plan.
- **Nothing under `data/capture/` or `data/ledger/` was rewritten.** The v1/v2
  migration only added files.
- **No secrets staged**, but the check itself was broken and is now fixed.
  The original pattern `[0-9a-f]{32}` matches a substring of every 64-char
  SHA-256 Merkle hash we publish, so guardrail 6 reported a leak on its first
  use. Verified no key was ever committed (0 matches for either real key
  across all history; `.env` untracked). Corrected to the word-boundary form
  `\b[0-9a-f]{32}\b`, which still catches a real key and ignores hashes.
  A check that always fires is worse than no check.

## Outstanding / unverified

- ~~The GitHub Actions capture cron has never fired unattended.~~
  **RESOLVED 2026-08-03.** A `schedule`-triggered run succeeded at
  `10:05:42Z` and the bot committed a 4th snapshot (`7138476`,
  `observed_at 2026-08-03T10:06:02`) with no machine of ours involved.
  Autonomous capture is now a verified fact. This was the largest open risk
  in the project: every night it silently failed to fire would have cost
  closing-line data that cannot be recovered.
- **Vercel deploy still failing as of the last check.** Two fixes pushed
  (`framework: null`, then `.vercelignore` excluding `pyproject.toml`). If the
  build still fails, the fallback is setting Root Directory to `site/public`
  in project settings, which requires moving `vercel.json` into that folder —
  that is a change I should not make blind, since it breaks the current layout
  if the setting is not also changed.

## Decisions deferred to you

1. **Which model leads the front page.** Both now publish, labelled, as you
   asked. The table currently shows Independent first. That ordering is an
   editorial choice with real consequences — Independent is our honest opinion
   and worse; Consensus is better calibrated and mostly echoes the market.
2. **Whether superseded commitments should be shown by default or behind a
   disclosure.** Currently always visible. Maximally honest; also draws the
   eye to a revision that most readers will not need to care about.

## Reproduction commands

```bash
python -m engine.backtest                    # elo baseline, nflverse lines
python -m engine.models.ensemble             # 4-model walk-forward comparison
python -m engine.pipeline.weekly --season 2026 --week 1
python scripts/build_site.py
python -c "from engine.commit import verify_slate; print(verify_slate('2026-W01-nfl'))"
```
