# Put the spread play inside the Merkle commitment

Opened by `w02-dry-run.md` finding 3, held for Branden since 2026-09-02
because the fix changes what a commitment contains. Branden authorised it
2026-09-04.

## The defect

`/picks` shows a SPREAD PLAY column. `engine/pipeline/weekly.py` builds that
opinion (`ats`) and puts it in the display payload and the encrypted pro
blob — and nowhere else. The 32 sealed leaves of a slate are two moneyline
predictions per game and nothing else.

So the one claim on the page that reads most like a *pick* is the one claim we
cannot prove we made before kickoff. It could be edited, dropped, or added
after the fact and the published root would still verify. That is precisely
the property the commitment exists to deny.

## What gets committed

**Every game that has a posted spread, not only the qualified plays.**

Sealing only the qualified subset would leave "which games qualified" outside
the commitment, so the selective set would still look post-hoc. Sealing the
opinion on every game with a number lets a reader recompute qualification
themselves: `edge = predicted_margin - line`, qualified when
`abs(edge) >= EDGE_THRESHOLD`. Strictly stronger, and it costs one leaf per
game.

**No probability, because we do not have one.** The margin model is a Ridge
regression that outputs points, not a calibrated cover probability. We have
never validated a cover probability and will not mint one to fill a field —
that is the exact conflation the product exists to refuse. `probability`
becomes optional and a spread leaf carries `predicted_margin` instead.

## Consequences, stated before the code

1. **Leaf shape changes for every prediction**, moneyline included: `to_dict`
   gains `predicted_margin` (null on moneyline rows). Already-sealed slates
   are unaffected — `verify_slate` re-hashes the dicts stored in the reveal
   file, it never rebuilds a `Prediction`. So every historical root still
   verifies. W02 is the first slate whose leaves carry the new field.
2. **`n_predictions` per slate goes from 32 to ~48** (2 moneyline + 1 spread
   per game with a line). Visible on /ledger and /verify. Not a defect; say it.
3. **The spread rows grade under their own `model_version`**, so they can
   never mix into the moneyline Brier or the published 49.5% ATS figure.
4. **CLV is unavailable for spread rows** and is reported as unavailable.
   `_closing_prices` reads moneyline rows only, and spread CLV is a move in
   the number as well as the price. Out of scope; not estimated.
5. **Push is excluded from the record**, matching `ensemble._record`, which
   computes ATS percentage over wins+losses.

## Phases

1. `engine/schema.py` — `probability: float | None`, add `predicted_margin`.
2. `engine/pipeline/weekly.py` — emit one `Market.SPREAD` prediction per game
   with a line, under `MODEL_MARGIN`. Fix the count line that says
   "2 models x N games".
3. `engine/grade.py` — grade by market: cover rule for spread, existing rule
   for moneyline; Brier only where a probability exists.
4. `tests/test_spread_in_commitment.py` — the sign convention agrees with
   `ensemble.ats_frame` on the same inputs, a null-probability leaf hashes and
   verifies, and the first leaf of a slate stays a moneyline row so /verify's
   worked example keeps quoting a real probability.
5. `bash scripts/check.sh` green, then push.

## Not in this change

- Re-sealing W01. W01 is sealed at v5 and its spread play is outside that
  commitment. A v6 that includes it is legitimate (kickoff is 2026-09-09, the
  seal would still be pre-kickoff) but sealing is Branden's to run — it needs
  `PRO_PAYLOAD_KEY` and it emails subscribers. **Until he runs it, Week 1
  ships with the defect this change fixes.**
- Spread CLV.
- A cover probability. It would need building and validating first.
