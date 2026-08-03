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

from engine.calibrate import expected_calibration_error, reliability
from engine.closing import compare_to_nflverse, consensus, load_backfill
from engine.models.ensemble import run as ensemble_run
from engine.adapters.nfl import NFLAdapter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/content/_figures.json"

BREAKEVEN = 0.5238  # -110 both sides
EPS = 1e-6

MODELS = [
    ("elo", "elo_p", "Elo + margin-of-victory. The transparent baseline."),
    ("independent", "p_ensemble", "Elo + opponent-aware EPA + rest. Never sees the line."),
    ("consensus", "p_anchored", "The above plus the de-vigged market price."),
]


def _ats(frame: pd.DataFrame, prob, spread_col: str):
    p = np.clip(np.asarray(prob, dtype=float), EPS, 1 - EPS)
    implied_margin = np.log(p / (1 - p)) * (400 / np.log(10)) / 25.0
    spread = frame[spread_col].to_numpy(float)
    pick_home = implied_margin > spread
    cover = frame["margin"].to_numpy(float) - spread
    win = ((cover > 0) == pick_home) & (cover != 0)
    push = cover == 0
    return int(win.sum()), int((~win & ~push).sum()), int(push.sum())


def _score(frame: pd.DataFrame, prob_col: str, spread_col: str,
           market_col: str) -> dict:
    y = frame["home_won"].to_numpy(float)
    p = frame[prob_col].to_numpy(float)
    w, l, push = _ats(frame, p, spread_col)
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
    eval_a = {name: _score(a_frame, col, "spread_line", "market_p")
              for name, col, _ in MODELS}
    eval_a["market"] = _score(a_frame, "market_p", "spread_line", "market_p")

    # ---- Evaluation B: real consensus closes ------------------------------
    cons = consensus(load_backfill())
    b_frame = frame.merge(cons, on=["season", "home_team", "away_team"],
                          how="inner").dropna(subset=["close_spread", "close_p_home"])
    eval_b = {name: _score(b_frame, col, "close_spread", "close_p_home")
              for name, col, _ in MODELS}
    eval_b["market"] = _score(b_frame, "close_p_home", "close_spread", "close_p_home")

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
        "line_provenance": prov,
        "reliability_independent": rel.to_dict(orient="records"),
        "models": {name: desc for name, _, desc in MODELS},
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
    print("## line provenance")
    for k, v in prov.items():
        print(f"  {k}: {v}")
    print()
    print(f"written: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
