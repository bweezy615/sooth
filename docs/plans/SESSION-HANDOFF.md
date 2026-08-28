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

## 3D is closed — do not reopen it

Decided 2026-08-28 by Branden: **remove the whole 3D idea completely.** Done.
Deleted `drafts/flow-3d-draft.html`, the vendored `drafts/vendor/three.module.min.js`,
both 3D concept prototypes, the concept plan and research memo, and the
`sooth-3d-concept` agent. Nothing on the live site ever referenced any of it.

If it comes up again, the exploration already ran and concluded against it, on
two grounds worth not re-deriving: rotating the best 3D chart we could build to
its most readable angle produced a plain 2D bar chart, and only 3 of 116 events
in `timeline.json` carry enough book-movement and sample depth to justify a
third axis — the rest would render a flat plane while implying resolution the
capture does not have.

`drafts/concept-c-price-rail.html` survived the deletion **because it contains
no 3D** — it is a flat SVG rail of every book's price on one scale, no
dependencies. It is unreviewed and orphaned now that its plan doc is gone.
Branden has not said whether to keep it; delete it if the answer is no.

One finding from that work is worth re-deriving properly, because it is free and
checkable and the site has never said it: on a single board snapshot, the
cheapest and dearest book on the *same* game at the *same* minute were holding
margins that differed by more than 3x. Any number published from this must come
out of `published_figures.py`, not out of this note.

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

Jargon pass beyond the landing page. Scope was deliberately
desktop-matching-mobile first, so these are untouched.

**The counts above were measured wrong** (2026-08-28, later the same day).
They came from substring greps, so `ECE` was matching RE*CE*IPTS, PIE*CE*
and tra*de*s, and `vig` was matching na*vig*ation. Word-boundary counts over
user-visible pages and `site/content/*.md` only:

| term | claimed | actual |
| --- | --- | --- |
| ECE | 12 pages | **2** — `record.html`, `methodology` |
| de-vig | 11 | **14** (understated; 3 already glossed) |
| Merkle | 7 | **7** |
| CLV | 6 | **6** |

So ECE is nearly done: `record.html:211-212` prints the bare labels
`Consensus ECE (A / B)` / `Market ECE (A / B)` while the definition already
sits three lines below at :215. Move it up, or label the stats in words.
`record.html:308` defines ECE in a `title=` tooltip, which is invisible on
touch and not reachable by keyboard — that is not a definition.

**de-vig is the real work, and it wants replacing rather than glossing.**
The site already has its own plain word for the concept — *fair price* —
used on `/tools` ("No-vig fair price"), `/game` and the FAIR label defined
in phase 3. Replacing "the de-vigged consensus" with "the fair price" costs
nothing and drops the term entirely at most sites of use. Already glossed
and fine as-is: `engine.html:167,192`, `record.html:179`.

Remember `/methodology`, `/verify`, `/disclaimers` and `/ledger` are
generated — edit `site/content/*.md`, never the HTML. `Merkle root` is
load-bearing on `/verify` (you recompute it by name) and cannot be replaced
there. `site/content/seo-plan.md` is an internal doc, not a built page, and
its jargon is deliberate keyword targeting — leave it alone.
