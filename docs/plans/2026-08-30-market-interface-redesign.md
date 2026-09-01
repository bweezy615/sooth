# SOOTH.BET market-interface redesign plan

## Verified baseline

- Worktree: `C:\Users\bkrec\sooth-whale`
- Branch: `feat/market-interface-redesign`, created from current `origin/main`
- Baseline commit: `1b0d84e`
- Local static server: running successfully on `http://127.0.0.1:4173`
- Production match: local and `https://sooth.bet/` render the same homepage copy, navigation, and board structure at baseline
- Whale tracker: commit `39712c2` is already contained in `origin/main`; no older checkout needs to be merged

## Product decisions

- Preserve all routes, data URLs, API contracts, analytics hooks, legal copy, and the sealed-slate verification system.
- Treat the user brief as the latest positioning decision: sportsbook price intelligence is the homepage story, and the market is the interface.
- Preserve the current free product. Do not recreate the deleted checkout, account, or paid Pro tier. Translate the brief's monitoring value into the existing free Alerts surface.
- Keep `Picks` only for the real sealed pick engine. Do not use that word for market or props pricing.
- Never rank a price surface using model edge. Use best price, fair price, range, and movement from existing payloads.
- Do not hand-type published performance figures. Continue reading them from `figures.json` or generated pages.

## Design system

- Direction: calm sports-market desk, graphite surfaces, off-white type, restrained existing teal accent.
- Dials: `DESIGN_VARIANCE 6`, `MOTION_INTENSITY 4`, `VISUAL_DENSITY 8`.
- Foundation: existing native HTML/CSS/JavaScript. No new framework or animation dependency.
- Shape rule: square data surfaces with small-radius interactive controls only where already required.
- Motion rule: CSS transitions for price/state feedback only, with reduced-motion fallbacks.
- Numeric rule: IBM Plex Mono and tabular numerals for all odds, times, ranges, and records.

## Phase 1: shared system and shell

- Consolidate semantic tokens for spacing, type, surfaces, borders, state feedback, table density, and motion in `assets/desk.css`.
- Simplify desktop navigation labels without changing route slugs.
- Preserve mobile bottom navigation and all existing accessibility behavior.
- Verify shared loading, empty, error, stale, and restricted states remain visible and useful.

## Phase 2: homepage

- Replace the traditional image-led hero with a real market-led hero sourced from `board.json`.
- Make the core statement unavoidable: every sportsbook prices the same bet differently, and Sooth shows the best available price.
- Add the one-bet price comparison, embedded live board, price-return education, alerts story, 49.5% origin story, proof ledger, and final free-product CTA using existing data and routes.
- Remove decorative hero imagery from the primary reading path without deleting assets used elsewhere.

## Phase 3: primary product routes

- Apply the standardized market-row hierarchy to `/market`, `/props`, `/edges`, and game detail surfaces.
- Keep best price, book, market, and fair context visible first.
- Use progressive disclosure for full sportsbook comparison and methodology details.
- Keep the whale tracker intact and visually aligned through shared tokens only.

## Phase 4: trust and research

- Refine `/trust`, `/record`, `/ledger`, `/verify`, `/methodology`, `/research`, and `/engine` around a three-layer architecture: use the product, understand the market, verify Sooth.
- Keep every published loss, commitment, methodology statement, and verification path intact.

## Phase 5: mobile and responsive QA

- Validate 375, 390, 430, 768, 1024, 1280, 1440, and 1920 widths.
- Ensure market blocks do not become overflowing desktop tables on phones.
- Keep at least 44px tap targets, visible focus, semantic labels, and reduced-motion support.

## Verification gates

After each phase:

1. Run frontend self-checks and targeted Python tests.
2. Run the static site locally and inspect changed routes in the browser.
3. Compare data-derived figures and market values against their JSON sources.
4. Check for prohibited product language and accidental route/metadata changes.

Before completion:

- `python scripts/build_site.py`
- `python -m pytest -q`
- `node tests/frontend/desk.selfcheck.js`
- `node tests/frontend/picks.selfcheck.js`
- Manual route and breakpoint inspection
- No push or production deployment unless explicitly requested

## Plan audit

- Frozen interfaces: no data schema, API, engine, grading, or route changes.
- Main failure mode: stale or fabricated market content. Mitigation: render only existing JSON and provide explicit loading/empty/error fallbacks.
- Main legal/product failure mode: implying prediction value or restoring monetization. Mitigation: keep current free model, preserve disclaimers, and keep price intelligence separate from the sealed pick engine.
- Main SEO failure mode: route or metadata loss. Mitigation: retain canonical URLs, titles, descriptions, redirects, and generated-page structure.
- Main concurrency failure mode: production `main` moves via capture automation. Mitigation: work only on this feature branch, do not push, and rebase plus retest only if the user later requests shipping.

## Baseline failure classification (2026-08-30)

Comparison method:

- Recorded the redesign branch status and diff before testing: only `site/public/index.html`, `site/public/assets/app.css`, and this untracked plan differed from baseline.
- Created a temporary detached worktree at untouched pre-redesign commit `1b0d84e`.
- Ran only the two failing tests in that clean worktree, then removed it.

Results:

- `tests/test_props_model_note.py::test_payload_rebuilds_from_committed_evidence` fails unchanged at `1b0d84e`.
  - Rebuilt `cover.k_quotes`: `3,859`; committed published value: `3,807`.
  - Rebuilt `slope.typical_n`: `2,473`; committed published value: `2,472`.
  - Classification: pre-existing evidence drift. The redesign must not modify evidence, historical data, or published figures to make this green.
- `tests/test_service_worker.py::test_the_cache_name_matches_the_shell_it_holds` fails unchanged at `1b0d84e`.
  - Declared: `sooth-e49527175d9c`; test-derived expected value: `sooth-52cd6797a1e6`.
  - The repository test fingerprints only `site/public/assets/desk.js` and `site/public/assets/desk.css`.
  - The redesign changes `index.html` and `app.css`, so it did not cause or alter this hash.
  - The repository has no separate cache-key generator; the existing documented process is the test itself, which prints the derived value when shared shell assets change.
  - Classification: pre-existing shared-shell cache maintenance blocker. Do not change it as part of this redesign unless the redesign later changes `desk.js` or `desk.css`.

These two failures remain reportable blockers but do not stop unrelated frontend work. All other verification gates remain active.

## Product-scope decisions after route implementation

- `PRODUCT.md` says the paid tier and checkout were deleted and all current surfaces are free. The monitoring proposition, "Sooth looks when you aren't," is implemented on the real Alerts product. No fake Pro entitlement, price, checkout, or subscription state is introduced.
- Public Record, Methodology, Verify, Ledger, and Engine Room remain deep verification routes. They share the market design layer but do not outrank the live board in the primary journey.
- There is no sign-in route in the current product. It remains intentionally absent instead of adding a nonfunctional authentication surface.

## Final rendered route checklist

A route is checked only after browser inspection at approximately 1440px and 390px.

- [x] `/` (`index.html`)
- [x] `/404.html`
- [x] `/alerts`
- [x] `/ask`
- [x] `/desk`
- [x] `/disclaimers`
- [x] `/edges`
- [x] `/engine`
- [x] `/game` (verified in its valid out-of-pricing-window empty state)
- [x] `/gamelog`
- [x] `/learn`
- [x] `/ledger`
- [x] `/market`
- [x] `/methodology`
- [x] `/picks`
- [x] `/predictor`
- [x] `/props-model`
- [x] `/props`
- [x] `/record`
- [x] `/research`
- [x] `/tools`
- [x] `/trust`
- [x] `/verify`
- [x] `/whales`

## Approved-design refinement pass (visual review)

This pass preserves the approved architecture and changes hierarchy only.

1. Homepage: remove dead space from the live-market side, make best available price dominant, and keep competing real book prices visible.
2. Board: collapse the marketing introduction so filters, Ask Sooth, and real rows begin in the first viewport; strengthen numeric hierarchy without changing board data or navigation.
3. Alerts: convert the movement tape from a database-like row into movement-first blocks emphasizing sportsbook, selection, price transition, recency, and market context.
4. Trust: add the published `49.77%` as the dominant record figure, then retain the approved origin statement and shorten only the introductory explanation.
5. Mobile: replace compressed board rows with purpose-built market blocks and a native details disclosure for competing prices; enlarge homepage odds and reduce terminal-style metadata.
6. Verify the same six review surfaces at 1440px and 390px, rerun focused checks and the full suite, then regenerate the temporary six-panel review screenshot outside production.

Audit: no route, schema, source data, historical evidence, alert API, authentication, monetization, or production navigation changes. Native HTML/CSS disclosure is sufficient; no new dependency or abstraction is needed.

## Final production-polish pass

- Simplify only the existing desktop sidebar hierarchy: primary product routes first, existing research/proof routes grouped and visually quieter.
- Rename the homepage hero contexts to `MARKET FAIR PRICE` and `BEST AVAILABLE`; retain the same data fields and values.
- Demote Board utility chrome while keeping sport filters, analyzer, metadata, and rows functional.
- Raise only undersized mobile supporting type; odds remain the dominant scale.
- Compare hero, Board, expanded market, and Alerts odds against `board.json` and `moves.json`; preserve unusual legitimate prices.
- Run interaction QA and the existing verification suite. No evidence, route, product scope, commit, push, or deployment changes.

## Full-product audit delta (2026-08-31)

Rendered review covered the homepage, Board, game workspace, Analyst, Pick Engine,
Proof, and their 390px states. No P0 issue or horizontal mobile overflow reproduced.

- P1: the game header currently reads as three competing fragments instead of a
  matchup followed by a clearly labelled market fair price. Recompose that existing
  data only; add native section anchors for Prices, Movement, Research, and Analyst.
- P1: Proof opens on the record table before explaining the verification sequence.
  Put a compact `SEALED → GRADED → PUBLIC → VERIFY` orientation ahead of the table.
- P1: the Pick Engine's API-unavailable state is honest but a dead end. Keep the
  failure and add links to already-published evidence; never substitute mock picks.
- P2: Analyst answers are visually flat. Label the existing answer as a market read,
  retain its capture-time stamp, and provide existing Board/Research follow-ups.
- P2: the global header has many equal-weight destinations. Do not restructure the
  approved navigation in this pass; route hierarchy is already clearer in the desktop
  sidebar and a new menu would add behavior and regression risk.

Plan audit: these are markup/CSS refinements around existing data and routes. They do
not touch schemas, APIs, source figures, grading, authentication, monetization, or the
service-worker fingerprint. Native links and CSS are sufficient; no dependency or new
abstraction is justified.

## Rendered visual QA refinement (2026-08-31)

Reviewed Homepage, Board, Game, Analyst, Research, Pick Engine, Proof, and Alerts
at 390, 430, 768, 1440, and 1920 widths. The product language is coherent and
the market remains the identity; no additional redesign is warranted.

- Tighten only the Board's desktop section rhythm so controls, market rows, and
  the featured disagreement read as one continuous workflow.
- Keep the full game sportsbook ladder on desktop; initially show four books on
  mobile with an explicit control for the remainder.
- Keep all Research rows and filters; initially show twelve matchups on mobile
  so the route is scannable before exposing the complete 56-row archive.
- Replace Analyst's conversational idle paragraph with a compact factual contract
  for fair price, best available, and market gap. Runtime answers remain unchanged.

Audit: no data, calculation, API, route, evidence, navigation, or shared shell
changes. These are progressive-disclosure and spacing rules around existing output.

## Third pass: signature market instrument

Design read: targeted evolution of a dense sports-market research product. Sooth
should read as a live sports market tape plus research desk. Variance 5, motion 3,
density 8. Keep the native static stack and the existing black, graphite, teal,
Archivo, and IBM Plex Mono system.

### Phase 1: shared market tape

- Add one dependency-free tape renderer backed only by `/data/board.json`.
- Mount it beneath the existing navigation on Home, Board, Game, Analyst, and Proof.
- Each item shows matchup, selected market, fair, best, and measured gap, and links
  to the existing populated game route. Mobile uses native horizontal scrolling.

### Phase 2: signature Board

- Replace the generic table presentation with market-scanner rows using the same
  event objects and navigation targets.
- Compose each row as matchup, market, and disagreement. Best is dominant; fair is
  secondary; teal is reserved for best and material gap.
- Add a distribution mark based on the real quote range and fair probability.
- Collapse games/books/freshness into one market context line and place Analyzer
  after the primary market rows.

### Phase 3: open-market Game workspace

- Recompose the existing above-fold values into matchup, selected market, fair,
  best book, range, and gap without metric cards.
- Keep all existing spectra, comparison, timeline, moves, research, and Analyst
  content, but connect them with shared rules and tighter section rhythm.
- On mobile, make Prices, Move, Research, and Ask a sticky segmented control that
  switches real sections instead of stacking the full workspace.

### Phase 4: contextual Analyst and homepage continuity

- Lead standalone Analyst with one real market context from the current board.
- Keep the existing non-chat answer treatment and API contract.
- Make the homepage live object and Board transition share the same tape/scanner
  language without replacing the approved homepage concept.
- Keep Proof editorial and evidence-heavy; add only the shared tape continuity.

### Verification

- Render and interact at 1440px and 390px after each major phase.
- Verify tape navigation, Board scanning and route opening, mobile Game pane
  switching, mobile horizontal tape, Analyst context, focus, overflow, and states.
- Run the documented build, frontend self-checks, and full Python suite.
- Preserve and report the two already-proven evidence/cache blockers unless the
  implementation itself changes their inputs. Do not alter evidence or figures.
- Capture the requested final eight-view contact sheet and stop.

Plan audit: the shared service-worker fingerprint covers `desk.js` and `desk.css`,
so this pass deliberately leaves both untouched. The new tape lives in its own
asset and the existing `market-system.css`; no manual cache fingerprint change is
needed. No backend, source data, grading, SEO route, legal copy, authentication,
or monetization work is in scope.

Completed 2026-08-31: all four phases rendered at 1440px and 390px. Board filters,
market links, Game comparison expansion, mobile pane switching, and real-data
Analyst context were exercised. Build and all six JavaScript self-checks pass.
Python verification is 323 passed with only the two documented baseline failures.
Final eight-view capture: `artifacts/visual-qa-signature/CONTACT-SHEET.png`.
