# Proposal: promote EPL from "In calibration" to "Live"

**This is a proposal. Nothing has been promoted.** The charter reserves this
decision for the user.

Reproduce every figure below: `python scripts/epl_promotion_evidence.py`

---

## What "Live" means here

Live means **the sport can be graded against a closing line whose provenance we
can defend.** It is a claim about auditability, not profitability.

NFL ships Live while losing to the market. If Live meant "wins", nothing we
have would qualify and the badge would be a performance claim we cannot
substantiate.

---

## The case FOR

**1. Provenance is better than NFL's.** football-data.co.uk documents its
C-infixed columns as closing prices — PSCH/PSCD/PSCA is Pinnacle Closing
Home/Draw/Away. It is the only source in this project whose closing odds are
labelled as closing *by the publisher*. NFL needed a paid backfill to reach the
same standard.

**2. Coverage is complete.** Nine seasons, 380 fixtures each, no gaps:

```
worst season coverage : 1.0000
seasons below 100%    : 0
```

**3. Calibration is sound.** Expected calibration error **0.02010** across
3,420 fixtures. The populated middle bands sit within 1–4 points, which is the
same standard NFL ships on.

---

## The case AGAINST

**The model never once beat the market. Not in any season.**

```
season   n   model   market   delta   model_better
  2017 380 0.57334 0.55692 0.01642        False
  2018 380 0.53529 0.52077 0.01452        False
  2019 380 0.58151 0.57443 0.00708        False
  2020 380 0.61867 0.59214 0.02653        False
  2021 380 0.56894 0.55433 0.01461        False
  2022 380 0.57868 0.57118 0.00750        False
  2023 380 0.55229 0.52585 0.02644        False
  2024 380 0.58958 0.57508 0.01450        False
  2025 380 0.61820 0.60922 0.00898        False

seasons where the model beat the market: 0 of 9
```

Nine seasons, nine losses. That is more consistent than NFL, where the gap at
least varies. It is a stable, reproducible deficit rather than noise.

**A provenance wrinkle for 2025.** Pinnacle closing coverage drops to 210 of
380 fixtures in 2025; the market-average closing columns still cover all 380,
so total coverage stays at 100%. But a Live badge resting partly on
market-average rather than Pinnacle is a slightly weaker claim than the earlier
seasons support, and it appears to be trending the wrong way.

**The top band is unusable.** The 0.9–1.0 bucket holds 3 fixtures and misses by
25 points. Football has draws, so a 90%+ home win is nearly always the model
overreaching. If EPL ships, it needs a confidence cap like NFL's, and probably
a lower one.

---

## What I would want decided

1. **Promote or hold.** On the charter's own definition EPL qualifies: it is
   gradeable against a documented close with complete coverage and sound
   calibration. Holding is also defensible on the grounds that nine
   consecutive losing seasons is a poor advertisement for a Live badge, even
   when Live does not claim wins.

2. **If promoted, cap published confidence below NFL's 85%.** The top band is
   3 fixtures wide and badly wrong. Something near 75% matches where the
   evidence actually supports the model.

3. **Watch the Pinnacle coverage trend.** If 2026 continues the 2025 decline,
   the provenance argument that makes EPL attractive weakens, and the badge
   should come back off.

---

## What is NOT in question

Whether the model is good. It is not, and neither is the NFL one. The product
is the board, and it works regardless.
