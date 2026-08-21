"""Replay a settled 2025 week and grade it end to end.

Week 1 2026 has not been played, so the grading pipeline cannot be tested on
it. This replays a past week using the SAME walk-forward probabilities the
backtest produces (fitted only on prior seasons), seals them, and grades the
result against real outcomes and our own closing lines.

Written to data/replay/, never data/ledger — a replay slate on the public
ledger would misrepresent it as a real, pre-kickoff commitment.

    python scripts/replay_grade.py --season 2025 --week 5
"""
from __future__ import annotations

import argparse, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.commit import commit_slate
from engine.grade import grade_slate
from engine.models.ensemble import run as ensemble_run
from engine.schema import Market, Prediction, Sport

MODELS = [("p_ensemble", "elo+epa-v1"), ("p_anchored", "elo+epa+market-v1")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--week", type=int, default=5)
    ap.add_argument("--publish", action="store_true",
                    help="also write the public graded artifact (rehearsal)")
    args = ap.parse_args()

    frame = ensemble_run().frame
    wk = frame[(frame["season"] == args.season)
               & (pd.to_numeric(frame["week"], errors="coerce") == args.week)]
    if wk.empty:
        raise SystemExit(f"no walk-forward rows for {args.season} W{args.week}")

    preds = []
    for _, r in wk.iterrows():
        for col, version in MODELS:
            p = float(r[col])
            pick_home = p >= 0.5
            preds.append(Prediction(
                event_id=str(r["game_id"]), sport=Sport.NFL,
                market=Market.MONEYLINE,
                selection="side_a" if pick_home else "side_b", line=None,
                probability=round(max(p, 1 - p), 4), model_version=version,
                created_at=datetime.now(timezone.utc),
                reference_price=(int(r["home_moneyline"]) if pick_home
                                 and pd.notna(r.get("home_moneyline"))
                                 else int(r["away_moneyline"])
                                 if pd.notna(r.get("away_moneyline")) else None),
            ))

    slate_id = f"REPLAY-{args.season}-W{args.week:02d}-nfl"
    out = Path("data/replay")
    c = commit_slate(slate_id, "nfl", preds, out_dir=out)
    print(f"replayed slate : {slate_id}")
    print(f"predictions    : {c.n_predictions}  root {c.root[:16]}...")
    print()
    grade = grade_slate(slate_id, ledger_dir=out, out_dir=out)
    print(grade.summary())
    if args.publish:
        from engine.grade import publish
        names = {str(r["game_id"]): {"home": str(r["home_team"]),
                                     "away": str(r["away_team"]),
                                     "kickoff": str(r.get("gameday", ""))}
                 for _, r in wk.iterrows()}
        print(f"published      : {publish(grade, names=names)}")


if __name__ == "__main__":
    main()
