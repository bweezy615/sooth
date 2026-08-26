# Plan: Polymarket Whale Tracker

- **Date:** 2026-08-25
- **Branch:** `feat/whale-tracker`
- **Size estimate:** medium
- **Status:** complete

## 1. Problem

Sooth has no surface showing checkable, public money already committed in
Polymarket sports futures. Add a season-futures page that reports positions,
trades, prices, timestamps, and open interest without interpreting any record
as betting advice.

## 2. Non-goals

- This change will not join Polymarket data to `/market` or `/game`; no
  per-game Polymarket sports markets exist to join.
- This change will not predict outcomes, rank traders as smart money, recommend
  a wager, or change any published figure or disclaimer.
- This change will not identify wallet owners, store email/PII, add accounts,
  add a paid tier, or add a runtime service.
- This change will not add a dependency, rate limiter, historical database,
  leaderboard, or wallet-profile enrichment.

## 3. Premises

| # | Premise | Verified |
|---|---|---|
| 1 | `origin/main` contains the complete build spec and this worktree is based on it. | ✅ `7493475` |
| 2 | Polymarket sports coverage in scope is season futures/novelty, not a usable per-game feed. | ✅ spec §3 live checks dated 2026-08-25 |
| 3 | Gamma `/events` supports `tag_slug` discovery and returns nested markets with condition IDs. | ✅ spec §4 and official Polymarket Events API docs |
| 4 | Public Data API exposes `/holders`, `/oi`, and `/trades` without adding auth code. | ✅ spec §4 and official Polymarket market-data/API docs |
| 5 | `requests` is already installed and the repo's capture modules use it with bounded timeouts. | ✅ `pyproject.toml`, `engine/injuries.py` |
| 6 | Atomic temp-file replacement is the existing fail-soft publish pattern. | ✅ `engine/injuries.py` |
| 7 | Offline module selfchecks are an existing project pattern. | ✅ `engine/watchlist.py`, `engine/watch_email.py` |
| 8 | Static pages use `Desk.mount`, `.ph`, one `<h1>`, and `Crest.team`; sport-scoped crest lookup is supported. | ✅ `desk.js`, `desk.css`, `crest.js` |
| 9 | Vercel publishes extensionless static HTML from `site/public` when `main` is pushed. | ✅ `vercel.json`, `AGENTS.md` |
| 10 | A 30-minute GitHub Actions capture-and-commit job matches the existing deployment architecture. | ✅ `.github/workflows/capture.yml` |

## 4. Approach

### Considered alternatives

| Approach | Effort | Key tradeoff |
|---|---|---|
| A. One Python capture that discovers all five tags, deduplicates markets, fetches all three Data API records, then atomically publishes one JSON file | Medium | Smallest complete implementation; any failed request preserves the last complete snapshot |
| B. Separate discovery/capture/publish modules with intermediate files | Large | More independently retryable, but adds orchestration and partial-state handling with no current need |
| C. Client-side calls from the page | Small | No durable/checkable snapshot, exposes visitors to API failures, and violates the repo's capture → JSON → page shape |

### Chosen approach and why

Choose A. It follows the existing architecture, adds no service or dependency,
and makes the fail-soft guarantee simple: build the complete payload in memory
and replace the public file only after every required request and validation
succeeds.

## 5. Design

```text
Gamma events (nfl/nba/mlb/nhl/sports)
                |
                v
 dedupe open markets by conditionId + retain explicit sport
                |
                v
 Data API holders + oi + trades per market
                |
                v
 normalize + threshold + copy guard + atomic replace
                |
                v
 site/public/data/whales.json
                |
                v
 /whales static page (loading / error / empty / success)
```

Affected files:

- `engine/whales.py`: constants, network fetch, pure normalization, atomic
  publish, CLI, offline fixture selfcheck, and recommendation-language guard.
- `.github/workflows/whales.yml`: 30-minute no-secret capture and path-limited
  commit/push.
- `site/public/whales.html`: season-futures reader with exactly one `<h1>`,
  explicit threshold/timestamp, positions, trades, prices, and open interest.
- `site/public/sitemap.xml`: add `/whales`.
- `site/public/sw.js`: add `/whales` to the shell and bump the cache key.
- `site/public/data/whales.json`: initial live snapshot produced by the capture.

Existing code to reuse:

- `requests.Session`, bounded timeouts, and `os.replace` from capture modules.
- `Desk.mount`, `Desk.load`, `Desk.esc`, existing data-state/table CSS, and
  `Crest.team(name, {sport: ..., size: 14})`.
- Word-boundary banned-language checking and literal negation handling described
  by `AGENTS.md`, applied to the page's authored reader-visible copy.

Audit clarification: `/holders` reports outcome shares, not USD. The published
`whale_min_usd` threshold applies to `shares * current outcome price`; both
inputs and the derived current value remain in the output so readers can check
the classification.

## 6. Failure modes

| Scenario | Expected behavior |
|---|---|
| Gamma discovery fails for any required tag | Exit nonzero and leave the previous `whales.json` byte-for-byte intact |
| Holders, OI, or trades fails/malforms for any discovered market | Exit nonzero and leave the previous file intact; never publish a partial snapshot |
| The same market appears under multiple tags | One record by `condition_id`; prefer the explicit league tag over generic `sports` |
| A valid run finds no open markets | Publish a complete empty snapshot with threshold and timestamp; page names the observed empty state |
| Repeated workflow run | Deterministic normalization except `generated_at`; atomic replacement prevents half-written JSON |
| Concurrent readers during publish | Readers see the old complete file or new complete file, never a temp file |
| Missing display name or malformed optional field | Fall back to shortened public wallet; skip only unusable rows, never infer identity |
| Page JSON request fails | Show a load error and make no claim about market activity |
| Crest map fails or team cannot be resolved | Keep the full market title in text; crest remains optional and silent |
| Long titles/wallets at 375px | Existing stacked-table pattern plus wrapping/ellipsis prevents page overflow |

## 7. UI states

| Screen/component | Empty | Loading | Error | Success | Narrow viewport |
|---|---|---|---|---|---|
| `/whales` | Explicitly says the completed capture found no qualifying markets/records | Skeleton/state text while `whales.json` loads | Says the file could not be read, not that no activity exists | Threshold, capture time, OI, held positions, and recent trades | Stacked cards/wrapped titles; document width stays at 375px |

## 8. Test plan

| Case | Level | Covers failure mode |
|---|---|---|
| Fixture normalization produces stable sport, OI, holder, trade, price, timestamp, and wallet/display fields | unit selfcheck | malformed/optional input |
| Duplicate condition IDs collapse and explicit sport wins | unit selfcheck | duplicate tags |
| Auth/PII fields never enter normalized output | unit selfcheck | public-data boundary |
| Recommendation-language guard scans page/module reader copy with word boundaries | unit selfcheck | tip-service drift |
| Simulated endpoint failure with an existing file preserves its exact bytes | integration selfcheck | fail-soft/atomic publish |
| Live capture produces valid `whales.json`, then offline selfcheck passes | integration | API contract + output contract |
| Exactly one `<h1>` and every `Crest.team` call passes `sport` | static check | page/crest acceptance |
| Browser QA at 375, 768, 1440: no console errors, crest resolution, no horizontal overflow | e2e/manual | UI states and responsive layout |
| `pytest -q` and every `api/*.selfcheck.js` | regression | repository acceptance |

## 9. Steps

1. [x] Implement `engine/whales.py` and its offline selfcheck; run the selfcheck,
   live capture, and forced-failure preservation check.
2. [x] Add the scheduled workflow and verify its YAML/path-limited commit behavior.
3. [x] Build `/whales`, add sitemap/cache entries, and run static + browser QA at
   375, 768, and 1440 pixels.
4. [x] Run `pytest -q`, every `api/*.selfcheck.js`, review plan against diff, sync
   with current `origin/main`, rerun all required checks, and present the final
   commit list for push approval. Never run `vercel --prod`.

## 10. Retro (fill after shipping)

- Premises that turned out wrong: Polymarket added per-game sports markets after
  the spec check; the generic sports tag contains thousands of markets; empty
  holder responses can be JSON `null`.
- Missing from this plan: bounded discovery and a safe lifetime-volume
  prefilter. Markets below the published threshold cannot contain a qualifying
  acquired position or trade, so they are skipped before Data API requests.
- Context-file updates made: none.
