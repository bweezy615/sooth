# Session handoff — 2026-08-28

Everything below is pushed to `main` and live. Tree clean, gate green.

## What shipped

**College football**, from nothing to live in a day, ahead of week 1:
`Sport.NCAAF`, a parameterised `engine/capture.py`, CFB on the board in
place of UFC (Branden's call — holds the board at 5 credits/run). See
`docs/plans/college-football.md`; two claims in that plan were wrong and are
corrected inline there.

**Capture split** (`docs/plans/capture-cadence.md`, option A, Branden's
call): free ESPN capture moved to `.github/workflows/capture-evidence.yml`
on `13,43 * * * *`, sharing capture.yml's `capture-odds` concurrency group.
The paid board build was deliberately not touched. `capture.yml` keeps its
own capture step as redundancy against dropped schedule events.

**Desktop comprehension redesign**, three phases, all live
(`docs/plans/desktop-comprehension.md`):

1. The dashboard never fetched `board.json` at all — desktop and phone are
   mutually exclusive IIFEs in `index.html` and only the phone asked for the
   games. Desktop now reads board → gaps → movement → proof, using desk.js's
   `eventCard()`/`sportRail()`. Fixed the raw `side_a`/`side_b` leak.
2. Three navigations disagreed about what the site contains; one vocabulary
   now across `desk.js` NAV, the sidebar and the phone tabs.
3. BEST / FAIR / PTS defined; ATS spelled out; legend set in `--mut`
   (5.60:1) not `--dim` (3.04:1, under the AA floor).

## Open, and waiting on Branden

1. **The Odds API reset date.** the-odds-api.com/account, two fields:
   monthly quota (expect 20,000) and the date usage resets. Git cannot
   settle it — the balance series spans 08-06 to 08-28 with no month
   boundary. If the pool refills 2026-09-01 there is no week-1 problem; if
   not, exhaustion lands ~2026-09-11 and NFL week 1 is 09-09.
2. **`/market` headline** — "The best sports betting research analyzer on
   the market", an unverifiable superlative in the largest type on the page.
   Positioning call, deliberately untouched.
3. **`/disclaimers` §7 CLV wording** — rewritten because the old sentence
   was false for 22 days; the replacement phrasing is Branden's to approve.

## Landmines

- **Do not change the capture crons.** The dropped-schedule throttling is
  currently the only thing keeping the credit account alive. Fixing the
  scheduler alone costs ≥504 credits/day against 219 today — exhaustion
  ~2026-09-03, *before* week 1. Two memos disagree; see
  `docs/plans/scheduled-runs-and-silent-green.md` and `capture-cadence.md`.
- **Two API keys exist.** Shell readings show a 500-credit free tier; CI
  runs on the 20,000 plan. Any "500" reading is the wrong key.
- **`sw.js` cache name is a fingerprint of desk.js + desk.css.** Change
  either and regenerate it, or returning visitors keep the old shell while
  the fix looks shipped. `tests/test_service_worker.py` prints the value.
- **`tests/test_figures_on_public_pages.py`** pins hand-typed figures on
  five pages. It will go red if a redesign drops one. That is its job.
- **Never touch `2026-W01-nfl`.** Anchored and final.
- **Shared working tree.** Claude and the supervisor agent both work in
  `E:\sooth-fe` on `main`. Only ever stage explicit paths; never `git add -A`.
  Consider a worktree if both run at once.

## Next action

Jargon pass beyond the landing page: ECE on 12 pages, de-vig on 11, Merkle
on 7, CLV on 6. Scope was deliberately desktop-matching-mobile first, so
these are untouched.
