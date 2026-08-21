# Sooth Pick Engine — Build Plan (Synthesized)

**Spine:** Plan A (product-first, model-frozen desk instrument, time-decay paywall).
**Grafts:** Plan B's statistical-honesty layer (published_figures.py iron rule + divergence-decile table with binomial CIs, cut-order discipline). Plan C's credit-budgeted backfill script and Pinnacle fair anchor as the two uses of the optional $30 data month.

**Thesis:** The model is frozen — it honestly loses to the close (49.5% ATS / 2,608 games, published), and that IS the product. Pro sells **timing and instrumentation**: the full sealed slate at seal time, per-pick desk detail, divergence alerts. Every pick decays to public automatically at first kickoff, so the trust surface stays free forever and the paywall never touches the proof. All engineering hours go into the surface, the seal→grade→publish automation, and copy no SEO-farmed copycat can fake — because ours is backed by GitHub-timestamped Merkle commitments and provenance-gated CLV.

**Hard rules (non-negotiable, enforced in code and copy):**
- Zero win-rate or performance claims anywhere. "Research/entertainment access, never winning picks."
- Every slate sealed before kickoff (existing merkle commit path, untouched); graded in public, losses rendered identically to wins.
- No published number exists outside `scripts/published_figures.py` → `figures.json` / `pickengine-record.json`. Nothing hand-typed. (Graft from B.)
- Static HTML + vanilla JS on the desk system; zero-dep Node in `api/`; Python in `engine/` (.venv). No frameworks.
- One commit per workflow run (Vercel 100-deploy/day budget).

---

## Ordered build list

### Step 0 — Freeze the model layer (0 hrs)
No retraining, no blending, no new features. The slate payload is exactly what `engine/pipeline/weekly.py` already emits: independent prob, consensus prob, 0.85 cap, fair odds, reference_price, merkle root. The ONE added number is arithmetic, not training: `divergence = |independent_prob − devigged market prob|`, used only for sorting and alert thresholds.
*Deferred to Phase 2 in writing (docs note): B's tuned market blend and QB-change feature; C's line-movement feature (unbacktestable on nflverse — closes only). Do not ship a feature whose backtest we cannot run.*

### Step 1 — Pick Object + public/pro payload split (Day 1)
**Modify `/Users/b/pick-engine/engine/pipeline/weekly.py`** — display-writing half ONLY; sealing/`commit_slate()` untouched. After commit, write two files per slate:
- `data/pro/{slate_id}.pro.json` — full slate: per game `{event_id, away, home, kickoff, independent{prob,fair_odds,pick}, consensus{prob,fair_odds,pick}, market_prob, divergence, best_price, best_book, n_books, edge_pts, merkle_leaf_index, reference_price}` — best price merged from the existing `best_lines.json` producer.
- `site/public/data/{slate_id}.json` — public payload with picks REDACTED until first kickoff (fields present, pick/probs null; divergence rank visible) plus seal metadata (root, sealed_at, version, supersedes). **Redaction enforced at write time in Python, never in JS.**

### Step 2 — `/api/picks`, the only content gate (Day 1–2)
**New `/Users/b/pick-engine/api/picks.js`** (zero-dep, mirrors `api/me.js`): `auth.readPro(req)` (verified present in `api/_auth.js`) ⇒ Pro gets `data/pro/{latest}.pro.json` with `cache-control: no-store`; non-Pro gets **200** with `{locked:true, teaser:{game_count, sealed_at, merkle_root, top_divergence_matchup_names_only}, upgrade:'/subscribe'}` — never a naked 401; the teaser is the funnel. **After the slate's first kickoff (server time vs kickoffs in the file), the endpoint returns the full payload to everyone.** Time-decay is both the honesty mechanism and the free archive.
**New `/Users/b/pick-engine/api/picks.selfcheck.js`** — exercises the gate, the time-decay branch, and missing-env fail-closed, per repo selfcheck convention.
**Modify `/Users/b/pick-engine/vercel.json`** — `functions.includeFiles: "data/pro/**"`; no-store on /api/picks.

### Step 3 — `picks.html` on the desk system (Day 2–4)
**New `/Users/b/pick-engine/site/public/picks.html`** (NOT engine.html — that page already exists as the Engine Room). `Desk.mount('picks')`; bootstrap `fetch('/api/me')` → `fetch('/api/picks')`.
- **PRO VIEW:** header strip (slate id, SEALED badge → /verify with root prefix, sealed_at ago-ticker, countdown to first kickoff). One `.itab` table sorted by divergence desc: `MATCHUP | KICKOFF | INDEPENDENT (confbar) | MARKET | DIVERGENCE | BEST PRICE (book) | FAIR | EDGE`. Row click expands `Desk.eventCard` + `Desk.spectrum` — every pick on the same implied-probability axis as the whole market (the signature desk-instrument moment; if the $30 month is bought, the FAIR anchor is Pinnacle de-vig). Explicit NO-PLAY banner when max divergence < threshold: *"Nothing on this slate clears our disagreement bar. That is a finding, not a gap."*
- **LOCKED VIEW:** same table skeleton, `.locked` rows (CSS blur + lock glyph, real matchup names, everything else ▓▓), seal metadata fully visible — "the picks exist and are already sealed; you're buying the look before kickoff" — one `.go` button → /subscribe.
**Modify `/Users/b/pick-engine/site/public/assets/desk.js`** — add `Desk.locked(el)`, `Desk.clvChip(v)`, `Desk.proBadge()` (flips static PRO cta → PRO ACTIVE per /api/me), /api/me bootstrap helper.
**Modify `/Users/b/pick-engine/site/public/assets/desk.css`** — `.locked` blur rows, `.clv-pos/.clv-neg/.clv-na` chips, `.seal-badge`.

### Step 4 — Grading as a public, automated surface (Day 4–6)
- **Modify `/Users/b/pick-engine/engine/grade.py`** — add `--publish`: writes `site/public/data/{slate_id}.graded.json` (existing SlateGrade shape + per-pick rows: won, brier, clv, clv_blocked_reason, close_provenance — missing closes are `null` with reason, never inferred).
- **New `/Users/b/pick-engine/scripts/publish_record.py`** — folds every graded file into `site/public/data/pickengine-record.json`: season-to-date per-model W-L, mean CLV, clv_coverage, Brier, per-week rows. Single source the site reads; never hand-typed.
- **Modify `/Users/b/pick-engine/scripts/published_figures.py`** (graft from B) — add a **divergence-decile table** on the existing eval sets (independent-vs-market divergence bucketed, ATS + Brier per bucket, **binomial confidence intervals on every ATS number**) so a hot bucket can never be presented as edge. If it shows nothing, publish that: "divergence flags carry no measured edge" is a legitimate, on-brand finding.
- **picks.html bottom section "LAST SLATE, GRADED":** per-pick CLV chips (green/red/na-with-reason), losses identical in style to wins, running record line with CLV coverage %.
- **Modify `/Users/b/pick-engine/site/public/record.html`** — render the same `pickengine-record.json` block; record page stays the canonical trust surface.

### Step 5 — Cadence automation: two new workflows (Day 6–7)
- **New `/Users/b/pick-engine/.github/workflows/seal.yml`** — cron Wed 09:00 ET in season: `python -m engine.pipeline.weekly` for the upcoming week; commits ledger + `data/pro` + public payload in **one commit**; the push is the GitHub timestamp anchor. `commit.py`'s refuse-post-kickoff and identical-root-no-op guards make re-runs safe.
- **New `/Users/b/pick-engine/.github/workflows/grade.yml`** — cron Tue 09:00 ET (post-MNF): `engine.grade --publish` + `scripts/publish_record.py`, one commit.
- **Docs runbook** (`docs/`): manual Wednesday fallback as a 5-minute operation if a cron misses (a missed seal past kickoff correctly means no slate that week).

### Step 6 — Wire the paid loop, re-arm deliberately (Day 7–8)
**Modify `/Users/b/pick-engine/site/public/subscribe.html`** — swap the free `<a>` for the documented `soothCheckout()` embedded-checkout button per the inline instructions (verified at lines ~101–107). Rewrite the buy card as three honest bullets: (1) full sealed slate Wednesday, before the market digests it — free users see it after kickoff; (2) per-pick desk instrumentation (spectrum, fair vs best price, divergence rank); (3) divergence alerts to your inbox.
**Modify `.github/workflows/alerts.yml` + its script** — alert Stripe Pro subscribers on the new divergence field, threshold configurable.
Keep `CAP_ACTIVE=false` on `api/ask.js` (don't couple two paywalls in one week). Verify `AUTH_SECRET` + `STRIPE_SECRET_KEY` on Vercel; both fail closed. **Accepted v1 gap, documented in-code:** `sooth_pro` is a 60-day cookie with no Stripe re-check/webhook — Phase 2.

### Step 7 — Positioning resolved in writing, same deploy (Day 8)
**Modify `/Users/b/pick-engine/PRODUCT.md`** — amendment: *"We sell access and instrumentation, never outcomes."* **Modify `predictor.html`** → permanent free teaser linking picks.html. Every "no picks sold" surface updated to "no winning picks sold — the record page shows exactly why," with 49.5% ATS visible on the Pro page itself. Footer disclaimer + `disclaimers.html` reviewed in the same pass. **This copy pass ships in the SAME deploy as the paid page** — never hand critics a screenshot window.

### Step 8 — Cold-start rehearsal (Day 9–10)
Run `scripts/replay_grade.py` over 3 settled 2025 weeks → `data/replay`, rendered through the new graded/record pipeline into a clearly-labeled **"REHEARSAL — 2025 replay, not live picks"** block on picks.html, replaced automatically by the first real graded slate (~Sept 16). Proves seal→grade→publish→render end-to-end before money touches it. Re-seal **2026-W01-nfl as v4** (supersedes v3 root, legitimate: earliest kickoff 2026-09-09, `commit.py` refuses post-kickoff) via the new seal.yml path — once, before Sept 9, never again for that slate.

---

## The $20 purchase decision

**Default: spend $0.** The proof loop runs entirely on the free stack (capture.yml/ESPN qualifies as own_capture provenance; nflverse is free). The literal $20 price point does not exist in the odds-data market — everything jumps free → ~$30 → ~$99+.

**If spending (recommended if Week-1 CLV coverage matters): The Odds API — 20K plan, $30 for one month, one-time** ($10 over the user's number; flagged, next tier is $99+). Priced both ways:
- **One-time $30 (recommended):** subscribe the week before Sept 9, run it product-side via **new `/Users/b/pick-engine/scripts/backfill_bulk.py`** wrapping `engine/backfill.py` (graft from C): resumable, **hard stop at 19,000 credits** (historical billed 10x ≈ 2,000 pulls), append-only JSONL, `provenance=oddsapi_historical_close` so grade.py's CLV gate accepts it unchanged. Uses: (a) lock closing snapshots for Weeks 1–4 so early CLV coverage is near-100% instead of ESPN-only; (b) widen the picks.html best-price board to ~40 books including **Pinnacle**, so the FAIR anchor on `Desk.spectrum` is de-vigged from a sharp book. Then cancel; fall back to the free 500-credit tier + existing crons.
- **Recurring $30/mo:** same plus ongoing live 40-book feed — **rejected for now**; decide after Weeks 1–3 conversions.
- **Explicitly rejected:** weather/injury/player-data spend (free via nflverse/StatsAPI/Visual Crossing); anything at $99+.

---

## Exact header copy (picks.html)

> **SOOTH PICK ENGINE — SEALED WEEKLY. GRADED IN PUBLIC. NEVER SOLD AS WINNING.**
> Our model measurably loses to the closing market — 49.5% ATS over 2,608 graded games, below the 52.4% break-even, published in full at /record. We do not claim an edge and you should not bet these picks expecting profit. What this is: a transparent research instrument. Every week, before the first kickoff, we seal our full slate — every game, both models, no cherry-picking — under a Merkle commitment anchored to a public GitHub timestamp you can verify at /verify. After the games close, we grade ourselves against the closing line (CLV), from price sources we captured ourselves, and publish every result — losses styled exactly like wins. Pro buys you the slate at seal time instead of after kickoff, the full desk instrumentation, and alerts. It does not buy you wins; nothing here does. A season is ~285 games — not enough to statistically separate a 52% picker from a coin. We say that out loud because the ledger would out us if we didn't. If someone sells you certainty, ask for their merkle root.

---

## Ship-by-Week-1 (before first kickoff, Sept 9–10)

Live on main before kickoff: picks.html with working gate (locked teaser + full board); /api/picks deployed, selfchecks green; subscribe.html re-armed and verified via a $0 promo-code test purchase; seal.yml + grade.yml crons live; 2026-W01 sealed as v4 through seal.yml with pro payload + redacted public payload; alerts wired to divergence; rehearsal block rendering 3 replayed 2025 weeks. **First real public grading lands automatically Tue Sept 15–16 — that moment (a real slate graded in public, losses included, CLV chips with provenance) is the actual launch.**

**Slips-if-tight cut order (graft from B):** divergence-decile CI table → alerts rewire → rehearsal block (keep the replay run itself as an offline test). **Never slips:** the seal (worst case, v3 already stands sealed and valid), the redaction-at-write, the same-deploy copy pass, the selfchecks.

**Deliberately NOT in v1:** Stripe webhook/renewal re-check (Phase 2, documented in code), ask.js cap re-arm, any new sport, any model change (blend/QB/line-delta deferred with written rationale in docs).

---

## Verification checklist (Sept 8–9 dress rehearsal)

1. seal.yml has produced the W1 slate and pushed (one commit; GitHub timestamp visible on bweezy615/sooth).
2. `/api/picks` returns the full payload with a Pro cookie; the locked teaser (200, not 401) without; `picks.selfcheck.js` green including missing-env fail-closed.
3. Redaction flips public automatically at first kickoff — tested with a past-dated copy of the slate file.
4. A $0 promo-code checkout grants the `sooth_pro` cookie end-to-end (subscribe → Stripe embedded → cookie → full board).
5. capture.yml is filling `data/capture/nfl/` (and, if the $30 month was bought, `backfill_bulk.py` completed under the 19K credit cap) so CLV coverage on the first grade is nonzero.
6. `published_figures.py` regenerated; zero numbers on any page exist outside figures.json / pickengine-record.json; every ATS figure carries its CI.
7. Grep the deployed site for banned claims: no "win", "edge", "beat", "profit" in any selling context; 49.5% visible on the Pro page; PRODUCT.md amendment committed in the same deploy as the paid page.
8. record.html and picks.html render the graded/record JSON with losses styled identically to wins; `clv:null` rows show their blocked reason verbatim.
9. Vercel envs `AUTH_SECRET` + `STRIPE_SECRET_KEY` present; both endpoints fail closed when absent.
10. Then stop touching it and let the crons run.

---

## Key risks

1. **Positioning whiplash** — mitigated by the same-deploy copy pass (Step 7) and checklist item 7.
2. **Entitlement drift** — 60-day cookie outlives cancellation; promo grants Pro with no card. Fine at current scale; must become a Stripe re-check before growth (Phase 2, in code comments).
3. **Sparse first grade** — CLV is provenance-gated; gaps show `clv:null` with reason (correct behavior). The $30 backfill is the one thing that materially de-risks this.
4. **Cron fragility** — missed Wednesday seal past kickoff = no slate that week (commit.py rightly refuses); runbook makes manual fallback a 5-minute job.
5. **Honesty tax on conversion** — "we lose to the close" converts worse than tout copy by design; judge on retention and the ledger's credibility, not week-2 revenue.
6. **Deploy budget** — both new workflows keep one-commit-per-run.