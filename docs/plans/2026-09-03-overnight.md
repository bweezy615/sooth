# Overnight plan — 2026-09-03

Owner: `sooth-whale-supervisor`, unattended. Branden asleep. Nothing here
needs him awake; anything that does is listed under "Do not do" and gets
written up instead.

## Safety floor (non-negotiable, applies to every task below)

1. `bash scripts/check.sh` must print `green` before ANY push. No exceptions,
   no "it's just docs".
2. `git pull --ff-only origin main` before starting; `git pull --rebase origin
   main` then RE-RUN the gate before each push. The capture bot pushes
   constantly — local main went 40 commits behind inside a day once.
3. One task per commit. The work and its write-up land together.
4. Never hand-edit `data/ledger/`. Never run `python -m engine.pipeline.weekly`
   locally (needs PRO_PAYLOAD_KEY, dies after writing a ledger version and
   leaves a half-sealed tree). Never dispatch `seal.yml` or any workflow that
   emails subscribers — that is Branden's to run.
5. Do not touch `WINDOW_THROUGH` — it was just moved to 2026-09-01 today
   (`0d36fef9`) and the alarm does not trip again until ~2026-10-01.
6. Published prose on /props-model, /verify, /methodology is the honesty
   surface. A factual error with decisive evidence may be fixed and must be
   said out loud in the commit. Anything ambiguous gets REPORTED, not quietly
   rewritten.

## Task 1 — settle "four fifths" by archaeology (highest value, decidable)

`site/public/props-model.html` says "four fifths of the effect disappears".
It is spelled in words, so `test_no_hand_typed_numbers_left_in_the_prose`
never guarded it. Two readings:

- share of the slope drop: 57% today, and already 62% before today's window
  move — never four fifths on this reading;
- share of the summed standard errors (4.6 / (4.6+0.6+0.8)): 77% today, 79%
  before — this does read as four fifths, and the surrounding paragraph
  reasons explicitly in standard errors.

Today's window move did NOT break it; it is pre-existing either way.

Decide it with evidence, not taste: `git log -S "four fifths" --patch --
site/public/props-model.html` to find the commit that introduced the
sentence, then rebuild the figures as they stood at that commit (the payload
is committed alongside, so read `props_model_note.json` at that SHA) and
compute both shares. Whichever reading was ~80% at authoring time is the
intended one.

- If the SE reading was ~80%: the sentence is correct. Leave the prose alone.
  Add a short generated figure or an explicit comment so the claim is tied to
  its numbers instead of floating, and move to Task 2.
- If NEITHER reading was ~80% at authoring: the sentence has been wrong since
  it was written. That is a correction-record item on the page that argues
  hardest for honesty. Write it up in `docs/plans/`, prepare the diff, and
  LEAVE IT FOR BRANDEN — do not push a prose correction unattended.

## Task 2 — guard worded quantities

The bug class Task 1 exposes: `test_no_hand_typed_numbers_left_in_the_prose`
only sees digits. Every spelled-out quantity on the page is unguarded.

Extend that test (or add a sibling) to catch worded quantities in the visible
prose of `/props-model` — fractions ("four fifths", "three in five", "half",
"a third"), multipliers ("twice", "double", "an order of magnitude"), and
worded counts. Same allowlist discipline the existing test uses: a quantity is
allowed if it is generated, inside `data-was`, or on an explicit reviewed list
with a stated reason.

Verify it the way this repo verifies guards: confirm the new test FAILS
against a deliberately wrong worded quantity before keeping it. A guard that
has never been seen to fail is not a guard.

## Task 3 — sweep the same lens across the other published pages

`tests/test_copy_claims.py` and `tests/test_figures_on_public_pages.py` exist;
find out what they actually cover. Then answer one question and write the
answer down: **which published pages can carry an unguarded quantity?**
Check /methodology, /verify, /disclaimers, /index, /picks, /props.

Report as a table — page, guarded by what, gap. Fix only the gaps that are
cheap and unambiguous; list the rest. Do not rewrite copy to fit a test.

## Task 4 — only if 1–3 finish

Continue the standing honesty hunt. Highest-value remaining classes, in order:

1. Any OTHER place a workflow writes an input without regenerating the
   artifact built from it. `tests/test_workflows_regenerate.py` covers
   props-model + the seal/grade pages. The 2026-09-02 sweep found no other
   instances — re-verify that conclusion against any workflow added since.
2. Any published claim whose supporting number is computed one way on the page
   and another way in the engine.
3. Fail-open error paths on published-trust surfaces (the `build_site.py`
   fail-closed fix `7da30920` is the precedent).

## Do not do

- Do not push a change to published prose that corrects a claim (Task 1's
  second branch). Write it up.
- Do not dispatch any workflow. Do not send email. Do not touch Stripe.
- Do not extend the props window again.
- Do not "improve" adjacent code. Surgical changes only.

## Handoff

Append what shipped to
`C:\Users\bkrec\.claude\projects\C--Users-bkrec\memory\sooth_end_to_end_audit_2026_08_30.md`
in the style of the existing entries: commit SHA, what moved, what was
verified BY RUNNING, and what is left open. If a task is abandoned, say why —
an honest "not done, here is the blocker" beats a plausible summary.

## Progress

- **2026-09-03 00:15** — Task 1 settled by archaeology. "four fifths" traces to a
  single commit (`b0b15fe9`, 2026-08-28) and was wrong the day it was written:
  60.5% on the reading a reader applies, 77.5% on the standard-error reading,
  57% today. NEITHER was ~80%, so this is the plan's second branch — written up
  with evidence and a gate-verified diff in `docs/plans/2026-09-03-four-fifths.md`
  and LEFT FOR BRANDEN. No published prose changed. Baseline gate green before
  and after.
- **2026-09-03 00:20** — Branden reprioritised: four backlog specs from
  `docs/plans/` (methodology-figures, ledger-nav-collision, w02-dry-run,
  research-payload-size) now run ahead of Tasks 2–4 above.
- **2026-09-03 00:35** — Backlog item 1 (`methodology-figures.md`) was already
  done: shipped 2026-08-27 in `05f1d479`. Verified live, not assumed —
  sooth.bet/methodology and the sooth.bet/data/figures.json payload /record
  fetches now agree on all nine reliability rows. Made all three guards FAIL by
  fault injection before believing them. Spec marked CLOSED with the evidence.
  Two gaps reported, not patched: `_owned_figures()` does not watch the
  reliability row counts (substring-matching bare ints would fire on unrelated
  prose), and methodology.md carries one unguarded worded quantity ("roughly
  eight points of overconfidence") describing a diagnostic not in _figures.json.
