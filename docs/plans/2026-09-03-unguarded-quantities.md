# Which published pages can carry an unguarded quantity?

*Task 3 of `docs/plans/2026-09-03-overnight.md`. Swept 2026-09-03, overnight.*

The question this answers, in one line: **on which pages can somebody type a
number into the copy and have the gate stay green?**

## The distinction that matters

There are two shapes of guard in this repo and they are not interchangeable.

- **Exhaustive.** Scans all the visible prose and fails on *any* quantity that
  is not generated or explicitly reviewed. A new number cannot get in.
  `test_no_hand_typed_numbers_left_in_the_prose` is the only one of these, and
  it covers one page.
- **Spot check.** Asserts that a named list of values *is present and current*.
  `test_the_hand_written_pages_quote_the_generated_figures`,
  `test_public_page_states_the_generated_figure`,
  `test_the_record_quoted_in_prose_matches_the_generated_figures`.

A spot check is strong against the failure it names — a figure going stale
after a model change — and blind to a *new* number typed anywhere on the same
page. Both failures have happened here. The 19-day-stale `figures.json` was the
first kind. "four fifths" was the second.

## The table

| page | source of truth | digits guarded by | worded quantities guarded by | gap |
|---|---|---|---|---|
| **/props-model** | hand-written HTML | **exhaustive** — `test_no_hand_typed_numbers_left_in_the_prose` | **exhaustive** — `test_no_worded_quantities_left_in_the_prose` (new tonight) | none for quantities. "four fifths" is on the reviewed list marked DISPUTED |
| **/methodology** | `site/content/methodology.md` → `build_site.py` | 42 `{{fig:}}` + 6 `{{table:}}` tokens; unresolved token **raises**; `test_methodology_does_not_type_its_figures` | the edge bar only, from tonight | `_owned_figures()` watches only values `_figures.json` holds *now*. Reliability row counts and derived `reliability_mid` values are unwatched. "roughly eight points of overconfidence" is unbacked by any file |
| **/verify** | `site/content/verify.md` | 26 `{{fig:}}` tokens; `test_verify_types_no_hash_of_its_own` (64-hex only); the walkthrough is recomputed against the committed slate | none needed — no worded quantity present | a non-hash literal typed into `verify.md` is unguarded. None present today |
| **/disclaimers** | `site/content/disclaimers.md` | spot check — was 3 values, **now 6** (fixed tonight) | none needed — none present | the six that matter are pinned; a seventh number typed in would be unguarded |
| **/index** | hand-written HTML | spot check — break-even; `test_public_page_states_the_generated_figure` | none needed — none present | new numbers unguarded. Most figures are injected from `figures.json` at runtime, which is the safer half |
| **/picks** | hand-written HTML | spot check — 4 values, plus `var EDGE_BAR` vs `EDGE_THRESHOLD` vs `_figures.json` | **the bar, from tonight** — `test_the_edge_bar_is_spelled_the_same_way_in_the_copy` | new numbers unguarded |
| **/props** | hand-written HTML | **nothing** | none needed — none present | two digits in the visible copy (`10`, `60`), neither a measurement of ours — a row cap and a refresh interval |

## Answer

**Every hand-written HTML page except /props-model can carry an unguarded
quantity.** The three markdown pages are much better placed, because a figure
there wants to be a `{{fig:}}` token and an unresolved token fails the build —
but their guards still only look for the values `_figures.json` owns today, not
for numbers in general.

That is not an argument for extending the exhaustive guard everywhere. It works
on /props-model because that page is a research note whose every figure is
generated, so the allowlist is short and stays short. On /methodology, which
carries 194 rendered digits, the allowlist would be longer than the page and
would itself be the hand-maintained artifact that goes stale — the exact
failure mode this repo has already paid for twice.

## Fixed tonight — cheap and unambiguous

1. **The edge bar, spelled out.** `picks.html` says "the bar is four points of
   disagreement with the number" and `methodology.md:236` says "the four-point
   bar". Both track `EDGE_THRESHOLD` / `selectivity.rule_threshold_pts = 4.0`
   and neither was guarded in worded form.

   This was demonstrated, not theorised. Moved the bar to 5 in all three places
   the digit test looks (`_figures.json`, `var EDGE_BAR`, `EDGE_THRESHOLD`):
   `test_the_edge_bar_is_the_same_number_in_all_three_places` **passed**, while
   both sentences still said four. The new
   `test_the_edge_bar_is_spelled_the_same_way_in_the_copy` **failed**, naming
   both files.

2. **Three more figures on /disclaimers.** The page's record sentence quotes six
   generated figures; only three were pinned. Now also pinned: the sample size
   (`2,671`), the market's Brier (`0.21038`) and the break-even (`52.38%`).
   Both new pins confirmed failing by moving the value in `_figures.json`.

## Not fixed — listed, with the reason

- **`_owned_figures()` does not watch reliability row counts or
  `reliability_mid`.** Watching them means substring-matching bare integers
  like `27` and `2,290` against 488 lines of prose. Noisy, and not obviously
  cheap.
- **"roughly eight points of overconfidence" (`methodology.md:307`).** Describes
  an earlier, larger Elo evaluation that is not in `_figures.json`. Nothing can
  back it, so no test can hold it. It is a claim about a past diagnostic — worth
  Branden deciding whether to source it or drop it, not worth an agent
  rewriting unattended.
- **"a card that plays a third of the games" (`picks.html:225`).** A worded
  fraction, but it describes what *other* services do, not a measurement of
  ours. Nothing to pin it to.
- **`/props`'s `10` and `60`.** UI constants (a row cap, a refresh interval),
  not published measurements.

## One thing to know before extending the worded guard

The `/props-model` matcher's fraction pattern matches **"a third party"** as
"a third". That is harmless where it lives — the phrase does not appear on
/props-model — but /methodology and /disclaimers both use it, so the pattern
needs an exclusion before it is pointed at either page. Recorded here so the
next person does not rediscover it by watching the gate go red.
