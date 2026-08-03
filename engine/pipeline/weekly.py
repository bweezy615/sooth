"""Weekly slate: predict, calibrate, cap, commit, publish.

Run this BEFORE the first kickoff of a slate. It is deliberately impossible to
run it usefully afterwards - `commit_slate` records the time and the earliest
kickoff, and the published record shows both, so a late commitment is visibly
late rather than silently accepted.

    python -m engine.pipeline.weekly --season 2026 --week 1

Outputs
-------
data/ledger/<slate>.commitment.json   published immediately (root hash only)
data/ledger/<slate>.reveal.json       published after settlement
site/public/data/<slate>.json         what the website renders
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..adapters.nfl import NFLAdapter
from ..calibrate import Calibrator
from ..commit import commit_slate
from ..models.elo import EloConfig, EloModel
from ..schema import Market, Prediction, Sport, american_to_prob, devig, prob_to_american

# Our top confidence band is measurably overconfident (94.5% predicted vs
# 86.7% actual). We cap rather than publish a number we know is inflated, and
# we say so on the methodology page.
CONFIDENCE_CAP = 0.85
MODEL_VERSION = "elo-mov-v1+iso"


def _train_through(adapter: NFLAdapter, season: int, week: int):
    """Fit Elo on every game strictly before this slate, plus a calibrator."""
    df = adapter.games
    done = df[df["home_score"].notna() & df["away_score"].notna()].sort_values(
        ["season", "week", "gameday"]
    )
    prior = done[
        (done["season"] < season)
        | ((done["season"] == season) & (pd.to_numeric(done["week"], errors="coerce") < week))
    ]

    model = EloModel(config=EloConfig())
    rows = []
    for _, r in prior.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        margin = float(r["home_score"]) - float(r["away_score"])
        neutral = str(r.get("location", "Home")) != "Home"
        rd = pd.to_numeric(r.get("home_rest"), errors="coerce") - pd.to_numeric(
            r.get("away_rest"), errors="coerce"
        )
        rd = 0.0 if pd.isna(rd) else float(rd)
        s = int(r["season"])
        p = model.expected(home, away, neutral=neutral, rest_diff=rd, season=s)
        if margin != 0:
            rows.append({"p": p, "y": 1.0 if margin > 0 else 0.0})
        model.update(home, away, margin, neutral=neutral, rest_diff=rd, season=s)

    hist = pd.DataFrame(rows)
    cal = Calibrator().fit(
        hist["p"].to_numpy(float), hist["y"].to_numpy(float), through_season=season - 1
    )
    return model, cal, len(hist)


def build_slate(season: int, week: int, out_root: Path | str = ".") -> dict:
    root = Path(out_root)
    adapter = NFLAdapter(cache_dir=root / "data/raw")
    adapter.fetch(force=True)  # always pull the freshest lines before committing

    model, cal, n_train = _train_through(adapter, season, week)

    df = adapter.games
    slate = df[
        (df["season"] == season)
        & (pd.to_numeric(df["week"], errors="coerce") == week)
        & df["home_score"].isna()
    ].copy()

    if slate.empty:
        raise SystemExit(
            f"no unplayed games for {season} week {week} - already settled, or "
            f"the schedule is not published yet"
        )

    now = datetime.now(timezone.utc)
    predictions: list[Prediction] = []
    display: list[dict] = []

    for _, r in slate.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        neutral = str(r.get("location", "Home")) != "Home"
        rd = pd.to_numeric(r.get("home_rest"), errors="coerce") - pd.to_numeric(
            r.get("away_rest"), errors="coerce"
        )
        rd = 0.0 if pd.isna(rd) else float(rd)

        raw = model.expected(home, away, neutral=neutral, rest_diff=rd, season=season)
        p_home = float(cal.transform(np.array([raw]))[0])

        # Pick the side we favour, then cap the published confidence.
        pick_home = p_home >= 0.5
        conf = p_home if pick_home else 1.0 - p_home
        capped = min(conf, CONFIDENCE_CAP)

        hml, aml = r.get("home_moneyline"), r.get("away_moneyline")
        mkt_home = np.nan
        if pd.notna(hml) and pd.notna(aml):
            mh, _ = devig(american_to_prob(int(hml)), american_to_prob(int(aml)))
            mkt_home = mh

        ref_price = (
            int(hml) if pick_home and pd.notna(hml)
            else int(aml) if pd.notna(aml) else None
        )

        kickoff = adapter._kickoff(r)
        predictions.append(
            Prediction(
                event_id=str(r["game_id"]),
                sport=Sport.NFL,
                market=Market.MONEYLINE,
                selection="side_a" if pick_home else "side_b",
                line=None,
                probability=round(capped, 4),
                model_version=MODEL_VERSION,
                created_at=kickoff,
                reference_price=ref_price,
                reference_line=(
                    float(r["spread_line"]) if pd.notna(r.get("spread_line")) else None
                ),
                rationale=(
                    f"elo {model.rating(home):.0f} vs {model.rating(away):.0f}, "
                    f"rest diff {rd:+.0f}"
                ),
            )
        )

        display.append(
            {
                "game_id": str(r["game_id"]),
                "kickoff": kickoff.isoformat(),
                "home": home,
                "away": away,
                "pick": home if pick_home else away,
                "our_prob": round(capped, 4),
                "our_fair_odds": prob_to_american(round(capped, 4)),
                "market_prob": (None if pd.isna(mkt_home) else round(
                    float(mkt_home if pick_home else 1 - mkt_home), 4)),
                "market_price": ref_price,
                "spread_line": (
                    float(r["spread_line"]) if pd.notna(r.get("spread_line")) else None
                ),
                "disagrees_with_market": (
                    None if pd.isna(mkt_home) else bool((mkt_home >= 0.5) != pick_home)
                ),
            }
        )

    slate_id = f"{season}-W{week:02d}-nfl"
    commitment = commit_slate(
        slate_id, "nfl", predictions, out_dir=root / "data/ledger"
    )

    payload = {
        "slate_id": slate_id,
        "sport": "nfl",
        "season": season,
        "week": week,
        "status": "committed",
        "model_version": MODEL_VERSION,
        "trained_on_games": n_train,
        "confidence_cap": CONFIDENCE_CAP,
        "merkle_root": commitment.root,
        "committed_at": commitment.committed_at.isoformat(),
        "earliest_kickoff": commitment.earliest_kickoff.isoformat(),
        "games": display,
        "disclaimer": (
            "Predictions are published for analysis and entertainment. We do "
            "not accept wagers. Our backtest does not beat the closing market "
            "- see /methodology."
        ),
    }

    site_dir = root / "site/public/data"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / f"{slate_id}.json").write_text(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()

    p = build_slate(args.season, args.week)
    print(f"slate        : {p['slate_id']}")
    print(f"games        : {len(p['games'])}")
    print(f"trained on   : {p['trained_on_games']} games")
    print(f"merkle root  : {p['merkle_root']}")
    print(f"committed at : {p['committed_at']}")
    print(f"1st kickoff  : {p['earliest_kickoff']}")
    print()
    hdr = f"{'matchup':<12} {'pick':<5} {'ours':>6} {'mkt':>6} {'spread':>7}  vs mkt"
    print(hdr)
    print("-" * len(hdr))
    for g in p["games"]:
        mp = "  n/a" if g["market_prob"] is None else f"{g['market_prob']:.3f}"
        sp = "    n/a" if g["spread_line"] is None else f"{g['spread_line']:+.1f}"
        flag = "DISAGREE" if g["disagrees_with_market"] else ""
        print(
            f"{g['away']+' @ '+g['home']:<12} {g['pick']:<5} "
            f"{g['our_prob']:.3f} {mp:>6} {sp:>7}  {flag}"
        )


if __name__ == "__main__":
    main()
