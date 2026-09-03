# "four fifths" on /props-model — archaeology, verdict, and a prepared fix

Status: **NOT SHIPPED. Waiting on Branden.**
Raised by: overnight run 2026-09-03, Task 1 of `docs/plans/2026-09-03-overnight.md`.

This is a correction to published prose on the page that argues hardest for our
honesty. The overnight rule is that an agent does not push one of those
unattended. Everything needed to decide it is below, and the fix is written and
gate-verified so it is a one-command apply.

## The sentence

`site/public/props-model.html`, in the section headed WHY — AND THIS IS THE PART
THAT GENERALISES, directly under the three-row information table:

> Withhold that from the line and hand it only to the model, and the model looks
> informed. **Give it to both and four fifths of the effect disappears.** That
> single step is worth 4.6 standard errors.

"Four fifths" is 80%. It is spelled in words, so
`test_no_hand_typed_numbers_left_in_the_prose` — which only looks for digits —
has never checked it. Nothing in `scripts/props_model_note.py`, in
`site/public/data/props_model_note.json`, or in the commit that wrote the
sentence computes 80% of anything. It is a hand-typed quantity on a page whose
entire claim is that no figure on it is hand-typed.

## Where it came from

`git log -S "four fifths" -- site/public/props-model.html` returns exactly one
commit: **b0b15fe9**, "props-model: the page arguing we are honest had 44 numbers
nobody could check" (2026-08-28). The sentence is new in that commit; the
paragraph it replaced made the (since-withdrawn) selection-effect argument and
contained no fraction. So the sentence has only ever had one author and one
meaning, and today's window move (`0d36fef9`) did not create the problem.

## The two readings, computed at three points in time

Both readings were recomputed from the payload committed alongside the page at
each commit (`git show <sha>:site/public/data/props_model_note.json`), so these
are the numbers as they actually stood, not a reconstruction.

| Reading | at b0b15fe9 (authored) | before today's move | today (HEAD) |
|---|---|---|---|
| **A.** slope drop as a share of the flat-line slope — `(flat − typical) / flat` | **60.5%** | 62.2% | 57.4% |
| **B.** slope drop as a share of the whole fall to the board slope | 49.5% | 50.9% | 48.0% |
| **C.** `z_line / (z_line + z_select + z_posted)` | **77.5%** | 78.7% | 76.6% |

Underlying figures at b0b15fe9: flat `+0.4954`, typical `+0.1956`,
board `−0.1100`; `z_line 4.686`, `z_select 0.569`, `z_posted 0.793`.

**Neither reading was 80% at authoring time.** Reading A — the one a reader
actually applies, because the table giving `+0.50` and `+0.20` sits three lines
above the sentence — was 60.5%. That is three fifths, not four.

## Why reading C is not a rescue

Reading C (77.5% at authoring) is the closer of the two, and the surrounding
paragraph does reason in standard errors, so it deserves a straight answer
rather than a dismissal. Three things rule it out:

1. **It is a forward reference.** `z_select` (0.6) and `z_posted` (0.8) are not
   introduced until the *next* paragraph. A reader meeting "four fifths of the
   effect disappears" has not yet been given two of the three numbers the
   reading needs. Nobody could check the claim at the point it is made — which
   is the specific failure this page exists to not commit.
2. **"The effect" has a referent, and it is the slope.** The preceding sentence
   is "the model looks informed"; the thing that disappears is the apparent
   information, which the table quotes as a slope. Reading C measures something
   else — how the *statistical significance* of the total fall splits across
   three steps.
3. **Summed z-statistics are not a quantity you can take a share of.** They are
   not additive and the three steps are not independent, so `4.6 / 6.0` is not a
   meaningful decomposition even before you ask what it would mean.

And 77.5% is not four fifths regardless. It rounds to 78%.

## Verdict

The sentence has been wrong since it was written, on 2026-08-28. It overstates
the effect it describes: 60.5% at the time, 57% now. It has been live for six
days. It is a correction-record item, not a typo — the page keeps a public
record of its own withdrawn claims, and this is one.

Two things worth saying plainly, because they cut in our favour and should not
be dressed up as worse than they are:

- **The argument does not change.** A 57% drop from a benchmark that does not
  know who is pitching is still the largest of the three steps by far, still
  worth 4.6 standard errors, and still the reason the model's apparent edge is
  not real. Overstated, not fabricated, and the conclusion stands either way.
- **The number it overstates is our own model looking better than it does.**
  Getting this wrong made our failure sound *more* explicable, not our model
  sound better.

## The prepared fix (written, gate-verified, then reverted)

The fix is not to retype a better fraction — that would leave a second hand-typed
quantity on the same page. It is to make the sentence quote a generated figure,
so it moves when the data moves and `test_every_displayed_figure_matches_the_payload`
starts guarding it.

Verified before reverting: `PYTHONPATH=. python -m pytest
tests/test_props_model_note.py -q` → 6 passed; `bash scripts/check.sh` → `green`.
The rendered value today is `57%`.

```diff
--- a/scripts/props_model_note.py
+++ b/scripts/props_model_note.py
@@ -596,6 +596,7 @@ def build(through: str = WINDOW_THROUGH) -> dict:
                           f"{b_board + 1.96 * se_board:+.2f}",
         "slope.board_typical": f"{b_ctrl:+.2f}",
         "slope.board_typical_n": f"{len(ctrl):,}",
+        "slope.line_share": f"{(b_flat - b_typ) / b_flat * 100:.0f}%",
         "slope.z_line": f"{abs(z_line):.1f}",
         "slope.z_select": f"{abs(z_select):.1f}",
         "slope.z_posted": f"{abs(z_posted):.1f}",
--- a/site/public/props-model.html
+++ b/site/public/props-model.html
@@ -252,7 +252,8 @@
       looked like the model's information was knowing that different pitchers strike
       out at different rates, and the number a book hangs is built around exactly that.
       Withhold that from the line and hand it only to the model, and the model looks
-      informed. Give it to both and four fifths of the effect disappears. That single
+      informed. Give it to both and <span class="n" data-f="slope.line_share">57%</span>
+      of the effect disappears. That single
       step is worth <span class="n" data-f="slope.z_line">4.6</span> standard errors.</p>
```

To apply: make those two edits, then
`PYTHONPATH=. python scripts/props_model_note.py --render` (the `--render` is not
optional — without it the page and its payload diverge, which has shipped three
times), then `bash scripts/check.sh`, then commit.

### Two calls that are Branden's, not mine

1. **Wording.** `57%` in place of `four fifths` is the minimal edit. "more than
   half" would also be true and would age better, but it puts a second worded
   quantity back on the page, so I did not propose it.
2. **Whether this goes in the correction record.** The page already carries a
   THREE EXPLANATIONS WE GOT WRONG section and a note about the claim it
   withdrew against itself. A published figure that was overstated for six days
   arguably belongs there rather than being quietly swapped. That is an editorial
   judgement about our own honesty surface and I am not making it unattended.

## Guard — in, and watched failing

The reason this went six days unnoticed is that
`test_no_hand_typed_numbers_left_in_the_prose` matches `\d`, so every
spelled-out quantity on the page was unguarded — and that test's own failure
message says "or spell them out".

`tests/test_props_model_note.py::test_no_worded_quantities_left_in_the_prose`
now scans the same visible prose for worded fractions, ratios, multipliers and
counts, and fails on any phrase not on an explicitly reviewed list. Eighteen
phrases are on that list, each with the reason a human decided it may stay.
**"four fifths" is on it, marked DISPUTED, pointing at this document, with an
instruction to delete the entry when the sentence is fixed.** The gate stays
green and the debt is visible in the test file rather than nowhere.

A sibling test, `test_the_worded_quantities_that_track_a_figure_still_match`,
turns four of those allowlist reasons into actual checks — because "checked
against board.won_pct" written in a comment is not a check. It pins "an
eleven-point edge" to `board.mean_abs_delta_pts`, "fewer than half" to
`board.won_pct`, "five equal-sized buckets" to `salvage.folds`, and "three or
more books" to `method.board_filter`.

Both were confirmed failing before being kept:

| Fault injected | Result |
|---|---|
| typed "Nine tenths of the remainder is noise" into the prose | **FAILED**, naming `nine tenths` |
| typed "twice as large" into the prose | **FAILED**, naming `twice` |
| set `board.mean_abs_delta_pts` to 8.4 in the payload | **FAILED**: "the page says … 'an eleven-point edge' but board.mean_abs_delta_pts is now 8.4" |
| set `board.won_pct` to 0.61 | **FAILED**: "the page says the model won 'fewer than half' … but board.won_pct is now 0.610" |

Note what the second pair means: "an eleven-point edge" is a hand-typed worded
number sitting in the same sentence as a generated one (`80%` is a `data-f`
span). It was correct, and nothing was watching it. It is now watched.
