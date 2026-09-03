# /methodology hand-types its numbers, and one table has already gone stale

*Backlog item 3. Written 2026-08-27 before any code.*

> **STATUS: CLOSED — shipped 2026-08-27 in `05f1d479`, re-verified live
> 2026-09-03.** Everything below was implemented, including the three items
> under "Found while reading". The verification is at the bottom of this file
> under "Closure". Nothing here is outstanding; do not re-do it. The one gap
> that survived is recorded there.

## The rule being broken

Hard rule 1: no published number is ever hand-typed. Every figure comes from
`scripts/published_figures.py` → `site/content/_figures.json`.

`site/content/methodology.md` types all of its in by hand. The workflow today
is: run `published_figures.py`, read the markdown tables it prints to stdout,
paste them into the page. Which is exactly the arrangement that failed twice
already in this repo — the `build_site.py` drift and the 19-day-stale
`figures.json` — and it has now failed a third time.

## It is not hypothetical any more: /methodology and /record disagree

`/record` renders the reliability table **from `figures.json` at runtime**
(`record.html:372`, `f.reliability_independent`). `/methodology` prints a
hand-typed copy. Today's Ridge margin change moved the model's predictions
slightly, `published_figures.py` was rerun, and only the runtime copy updated.
Every one of the nine rows now disagrees:

| band | /methodology says | `_figures.json` says |
|---|---|---|
| 0.1-0.2 | 26 · 16.70% · 26.92% · −10.22 | **27 · 16.63% · 25.93% · −9.30** |
| 0.2-0.3 | 152 · 26.16% · 28.95% · −2.79 | 152 · **26.07%** · 28.95% · **−2.88** |
| 0.3-0.4 | 270 · 36.02% · 33.70% · +2.32 | **273** · 36.02% · **33.33% · +2.68** |
| 0.4-0.5 | 419 · 45.37% · 41.29% · +4.08 | **414 · 45.32% · 42.27% · +3.05** |
| 0.5-0.6 | 569 · 54.99% · 50.26% · +4.73 | **577 · 55.04% · 49.91% · +5.12** |
| 0.6-0.7 | 593 · 64.97% · 62.39% · +2.58 | **582 · 64.93% · 62.20% · +2.73** |
| 0.7-0.8 | 440 · 74.86% · 72.95% · +1.91 | **444 · 74.88% · 73.20% · +1.68** |
| 0.8-0.9 | 190 · 83.93% · 85.26% · −1.33 | **189 · 84.00% · 85.19% · −1.19** |
| 0.9-1.0 | 12 · 91.13% · 91.67% · −0.54 | **13 · 91.17% · 92.31% · −1.14** |

And the prose reading that table is stale with it:

- "the 0.1-0.2 and 0.9-1.0 bands hold **26 and 12** games" → 27 and 13
- "0.3 through 0.8 … hold **2,291** of the 2,671 games" → 2,290
- "overconfident by between **1.9 and 4.7** percentage points" → 1.7 and 5.1
- the confidence-cap section: "the 0.9-1.0 band holds **twelve** games" → thirteen

A visitor who opens both pages sees two different calibration tables for the
same model over the same 2,671 games. On a site arguing its numbers are
reproducible, that is the worst kind of defect there is, and it is live now.

**Everything else in methodology.md checks out.** Verified against
`_figures.json` field by field: both backtest tables, the ECE table, the
selectivity table, the per-season table, the two confidence intervals, the
dog/favourite splits, and the line-provenance paragraph are all currently
correct. Only the reliability block drifted — because it is the only one whose
values changed when the margin model changed.

## Fix

Not "retype the table". Wire it, so it cannot happen a fourth time.

Add a substitution pass to `scripts/build_site.py`, run over the markdown
before it is rendered:

- `{{fig:evaluation_a.results.independent.brier}}` — dotted path into
  `_figures.json`, with a format suffix where the raw value is not what should
  be printed: `{{fig:…ats_pct|pct2}}` → `49.77%`, `{{fig:…gap|pts2}}` →
  `+2.68 pts`, `{{fig:…n|comma}}` → `2,671`.
- `{{table:reliability}}`, `{{table:backtest_a}}`, `{{table:backtest_b}}`,
  `{{table:ece}}`, `{{table:selectivity}}`, `{{table:by_season}}` — whole
  tables built from the same file, because a nine-row table is not worth 45
  separate tokens and its row count should follow the data.
- **An unresolved token is a build failure**, loudly. A page that renders
  `{{fig:typo}}` to a visitor would be worse than the hand-typed number.

`published_figures.py`'s stdout summary stays as it is — it is useful for
reading a run — but it stops being an instruction to copy anything.

## Why this is the right verification

Every figure in the file except the reliability block is currently correct. So
after substitution, rebuilding must produce a `methodology.html` that differs
from the committed one **only in the reliability table and the four prose
numbers that read it**. Any other diff is a bug in the substitution, and the
diff itself is the proof the wiring is faithful. That is the check to run
before anything else.

## Phases

1. Substitution engine in `build_site.py` + unit tests for the formats and for
   the unresolved-token failure.
2. Convert methodology.md's **correct** figures first (summary paragraph, both
   backtest tables, ECE table, selectivity, per-season, CIs, splits,
   provenance). Rebuild; require a byte-identical `methodology.html`. This
   proves the engine before it is used to change anything.
3. Convert the reliability block and its prose. Rebuild; the diff should now be
   exactly the corrections in the table above and nothing else.
4. A test asserting `methodology.md` contains no bare copy of a figure that
   `_figures.json` owns — i.e. the ATS records, Brier scores and ECEs appear
   only as tokens. Extend `tests/test_figures_published.py`, which already does
   this for `/disclaimers`.

## Scope boundary

The parameters table (`k` 20.0, `home_advantage` 48.0, …) is **not** converted.
Those are design constants that live in the model code, not measurements from
`_figures.json`; wiring them to a file that does not contain them would be
theatre. Same for the model version strings.

## Found while reading, fixed separately, not here

- `methodology.md:454` — "**One sport is Live.** NFL only. The other **eight**
  sports on this site…". The site covers five sports (`desk.js` `SPORTS`, and
  `board.json`): NFL, MLB, NBA, NHL, UFC. Four others, not eight.
- `methodology.md:450` — "**No play-level information.** The model does not use
  expected points added…" contradicts the same page's own summary ("augmented
  with opponent-aware expected-points-added form and rest") and
  `_figures.json`'s own model description ("Elo + opponent-aware EPA + rest").
  One of the two is false; the limitation bullet is the stale one.
- `site/public/trust.html`'s `.stance` block hand-types the backtest record.
  Checked today: correct, but pinned by nothing.

---

## Closure — verified 2026-09-03, overnight run

Re-opened as the night's highest-priority backlog item on the understanding
that /methodology and /record still disagreed on all nine reliability rows.
**They do not.** That was true when this file was written on 2026-08-27 and was
fixed the same evening by `05f1d479`. Measured rather than assumed:

- `site/content/_figures.json` and the served `site/public/data/figures.json`
  hold byte-identical `reliability_independent` arrays (9 rows).
- The built `site/public/methodology.html` renders all 9 rows equal to
  `_figures.json`, field by field.
- **Live**: fetched `https://sooth.bet/data/figures.json` and
  `https://sooth.bet/methodology`. The live payload `/record` fetches at
  runtime matches the repo's `_figures.json`, and all 9 rows rendered on the
  live /methodology match that live payload. The two pages agree in
  production.

All four prose numbers that read the table are tokens now, including the
spelled-out one — "the 0.9-1.0 band holds **twelve** games" is
`{{fig:reliability_independent.8.n|int}}`. The `reliability_mid` figures
(`n`, `min_gap`, `max_gap`) are derived in `build_site.py::_derive`.

The three "Found while reading" items are all fixed: methodology.md now says
"The other **four** sports", the play-level bullet now reads "The model **does**
use expected points added", and `trust.html` is pinned by
`test_the_hand_written_pages_quote_the_generated_figures` along with six other
hand-written pages.

### The guards, watched failing

A guard nobody has seen fail is not a guard, so each was made to fail before
this file was closed. Every injection was reverted immediately.

| Guard | Fault injected | Result |
|---|---|---|
| `test_methodology_does_not_type_its_figures` | typed the current ATS record `1298-1310-63` into methodology.md prose | **FAILED** correctly, naming the value |
| `test_the_served_figures_are_the_generated_figures` | changed one `n` in `site/public/data/figures.json` | **FAILED** correctly |
| `build_site.py` unresolved-token rule | replaced `{{table:reliability}}` with `{{fig:...no_such_field}}` | **raised `FigureError`**, build aborted |

### The gap that survived, and why it is not being closed tonight

`_owned_figures()` in `tests/test_figures_published.py` builds its watch-list
from the values `_figures.json` holds **right now**, and matches them as
substrings of the markdown. Two consequences:

1. It catches a figure typed in while correct — which is enough, because such a
   line can never be committed, so it can never later go stale. This is the
   sound part and it is why the bug class is genuinely closed.
2. It does **not** watch the reliability row counts or the derived
   `reliability_mid` values. Adding them would mean substring-matching bare
   integers like `27` and `2,290` against 488 lines of prose, which would fire
   on unrelated text. The fix is not obviously cheap and the plan says not to
   rewrite copy to fit a test, so this is reported, not patched.

### One unguarded worded quantity found on this page

`methodology.md` line ~307: "An earlier, larger evaluation of the raw Elo
baseline showed the opposite problem: roughly **eight** points of
overconfidence at the top of the range."

Spelled out, so no digit test sees it; and it describes a one-off historical
diagnostic that is not in `_figures.json`, so no figure test can back it. It is
the same class as "four fifths" on /props-model (see
`docs/plans/2026-09-03-four-fifths.md`) and it feeds into Task 3 of the
overnight plan. Not touched: it is a claim about a past evaluation that I
cannot verify from the published data, which makes it a report-not-rewrite
item.
