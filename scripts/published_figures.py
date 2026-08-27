"""Regenerate every performance figure the website publishes.

One command, one source of truth:

    python scripts/published_figures.py

Why this exists
---------------
A number on a marketing page that nobody can regenerate is a claim, not a
measurement. Our whole position is that ours are measurements, so every figure
we publish must come out of this script, and this script must be runnable by
anyone who clones the repo.

It produces TWO evaluations of the same models, and both are published:

  A. nflverse lines, 2016-2025, n=2,671
     Large sample. But nflverse's ``spread_line`` is an undocumented periodic
     snapshot, not a documented close - measured to differ from a real
     consensus close on 32.9% of games (mean 0.217 pts).

  B. Real consensus closes, 2023-2025, n=854
     Smaller sample, far better provenance: median across ~11-17 books
     captured 5-28 minutes before each kickoff, from our own paid backfill.

Neither supersedes the other and we do not quietly swap one for the other.
A is the larger sample; B is the better evidence. Publishing both with their
sample sizes is the honest presentation, and the two agree: nothing beats the
52.38% break-even.

Output: site/content/_figures.json (consumed by the site build) plus a
markdown summary printed to stdout for pasting into methodology.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.linear_model import Ridge

from engine.calibrate import expected_calibration_error, reliability
from engine.closing import compare_to_nflverse, consensus, load_backfill
from engine.models.ensemble import EDGE_THRESHOLD, _ats, _logit, selectivity
from engine.models.ensemble import run as ensemble_run
from engine.adapters.nfl import NFLAdapter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/content/_figures.json"

BREAKEVEN = 0.5238  # -110 both sides
EPS = 1e-6

MODELS = [
    ("elo", "elo_p", "elo_spread",
     "Elo + margin-of-victory. The transparent baseline."),
    ("independent", "p_ensemble", "m_ensemble",
     "Elo + opponent-aware EPA + rest. Never sees the line."),
    ("consensus", "p_anchored", "m_anchored",
     "The above plus the de-vigged market price."),
]


def _market_margin(frame: pd.DataFrame, prob_col: str) -> pd.Series:
    """The market's own points estimate, fitted rather than assumed.

    Until 2026-08 this script converted a win probability into a margin with
    ``logit(p) * 400/ln(10) / 25`` — an Elo scale constant applied to numbers
    that were never on the Elo scale. The models now predict margin directly
    (see ``engine.models.ensemble._wf_margin``); only the benchmark row still
    needs a conversion, because a market moneyline is all we have for it.

    Fitting one slope in-sample cannot manufacture an edge here: this row is
    the market's moneyline graded against the market's own spread, so it sits
    at coin-flip by construction. The fit only puts it on the right scale
    instead of an invented one.
    """
    d = frame.dropna(subset=[prob_col, "margin"])
    reg = Ridge(alpha=1.0).fit(_logit(d[prob_col]).reshape(-1, 1), d["margin"])
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    ok = frame[prob_col].notna()
    out.loc[ok] = reg.predict(_logit(frame.loc[ok, prob_col]).reshape(-1, 1))
    return out


def _score(frame: pd.DataFrame, prob_col: str, margin_col: str,
           spread_col: str) -> dict:
    y = frame["home_won"].to_numpy(float)
    p = frame[prob_col].to_numpy(float)
    w, l, push = _ats(frame, margin_col, spread_col)
    played = w + l
    return {
        "n": int(len(frame)),
        "brier": round(float(np.mean((p - y) ** 2)), 5),
        "log_loss": round(float(-np.mean(
            y * np.log(np.clip(p, EPS, 1 - EPS))
            + (1 - y) * np.log(np.clip(1 - p, EPS, 1 - EPS)))), 5),
        "accuracy": round(float(np.mean((p > 0.5) == (y == 1))), 4),
        "ece": round(expected_calibration_error(p, y), 5),
        "ats_record": f"{w}-{l}-{push}",
        "ats_pct": round(w / played, 4) if played else None,
        "beats_breakeven": bool(played and (w / played) > BREAKEVEN),
    }


def main() -> None:
    print("regenerating published figures (this rebuilds the walk-forward run)...")
    comparison = ensemble_run()
    frame = comparison.frame.copy()

    # ---- Evaluation A: nflverse lines, full sample -----------------------
    a_frame = frame.dropna(subset=["spread_line", "market_p"]).copy()
    a_frame["m_benchmark"] = _market_margin(a_frame, "market_p")
    eval_a = {name: _score(a_frame, col, mcol, "spread_line")
              for name, col, mcol, _ in MODELS}
    eval_a["market"] = _score(a_frame, "market_p", "m_benchmark", "spread_line")

    # ---- Evaluation B: real consensus closes ------------------------------
    cons = consensus(load_backfill())
    b_frame = frame.merge(cons, on=["season", "home_team", "away_team"],
                          how="inner").dropna(subset=["close_spread", "close_p_home"])
    b_frame["m_benchmark"] = _market_margin(b_frame, "close_p_home")
    eval_b = {name: _score(b_frame, col, mcol, "close_spread")
              for name, col, mcol, _ in MODELS}
    eval_b["market"] = _score(b_frame, "close_p_home", "m_benchmark",
                              "close_spread")

    # ---- What selectivity buys, on both line sources ----------------------
    # The engine's shipped decision rule is a threshold, so the threshold must
    # be a measurement in this file like every other number the site quotes.
    # Both evaluations get one: A for sample size, B for provenance.
    sel = {
        "rule_threshold_pts": EDGE_THRESHOLD,
        "evaluation_a": selectivity(a_frame, "m_ensemble", "spread_line"),
        "evaluation_b": selectivity(b_frame, "m_ensemble", "close_spread"),
    }

    # ---- Line-provenance comparison ---------------------------------------
    prov = compare_to_nflverse(cons, NFLAdapter().games)
    prov.pop("frame", None)

    # ---- Calibration curve for the number we lead with --------------------
    rel = reliability(a_frame["p_ensemble"].to_numpy(float),
                      a_frame["home_won"].to_numpy(float))

    figures = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "python scripts/published_figures.py",
        "breakeven_ats": BREAKEVEN,
        "confidence_cap": 0.85,
        "evaluation_a": {
            "label": "nflverse lines, 2016-2025",
            "provenance": "nflverse spread_line - an undocumented periodic "
                          "snapshot, not a documented close",
            "seasons": "2016-2025",
            "results": eval_a,
        },
        "evaluation_b": {
            "label": "real consensus closes, 2023-2025",
            "provenance": "median across books, captured 5-28 min before each "
                          "kickoff, from our own paid backfill",
            "seasons": "2023-2025",
            "results": eval_b,
        },
        "selectivity": sel,
        "line_provenance": prov,
        "reliability_independent": rel.to_dict(orient="records"),
        "models": {name: desc for name, _, _, desc in MODELS},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(figures, indent=2))

    # ---- human-readable summary -------------------------------------------
    def table(ev, spread_label):
        rows = ["| model | n | Brier | ECE | ATS | ATS% | beats 52.38%? |",
                "|---|---|---|---|---|---|---|"]
        for key in ["elo", "independent", "consensus", "market"]:
            r = ev[key]
            rows.append(
                f"| {key} | {r['n']} | {r['brier']} | {r['ece']} | "
                f"{r['ats_record']} | {r['ats_pct']:.4f} | "
                f"{'YES' if r['beats_breakeven'] else 'no'} |")
        return "\n".join(rows)

    print()
    print(f"## A. nflverse lines ({figures['evaluation_a']['seasons']})")
    print(table(eval_a, "spread_line"))
    print()
    print(f"## B. real consensus closes ({figures['evaluation_b']['seasons']})")
    print(table(eval_b, "close_spread"))
    print()
    print(f"## selectivity — independent model, edge >= {EDGE_THRESHOLD} pts")
    for ev in ("evaluation_a", "evaluation_b"):
        s = sel[ev]
        print(f"### {ev}")
        print("| edge | all | underdog | favourite |")
        print("|---|---|---|---|")
        for t in s["thresholds"]:
            def cell(r):
                return "-" if r["pct"] is None else f"{r['record']} ({r['pct']:.4f})"
            print(f"| {t['edge']} | {cell(t['all'])} | {cell(t['underdog'])} "
                  f"| {cell(t['favourite'])} |")
        live = s["live"]
        print(f"\nrule: {s['rule']}")
        print(f"  {live['record']}  {live['pct']}  95% CI {live['ci95']}  "
              f"~{live['per_season']} plays/season")
        beats = live["ci95"] and live["ci95"][0] > BREAKEVEN
        print(f"  interval clears {BREAKEVEN} break-even: "
              f"{'YES' if beats else 'NO — cannot be claimed as an edge'}")
        print("  per season: " + ", ".join(
            f"{k} {v['record']}" for k, v in sorted(s["by_season"].items())))
        print()
    print("## line provenance")
    for k, v in prov.items():
        print(f"  {k}: {v}")
    print()
    print(f"written: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
