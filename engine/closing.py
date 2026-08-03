"""Consensus closing lines from the backfill, and what they reveal.

This module answers the question the whole project rests on: when we say
"the closing line", are we using a number that actually was the close?

The backfill captured 16 books within ~5-28 minutes of each kickoff. Taking a
median across books gives a consensus close that no single operator's opinion
can skew. We then compare that consensus against nflverse's ``spread_line``,
which is what every previously published figure in this project was computed
from, and against our own model.

Median rather than mean, deliberately: one book posting a stale or erroneous
number should not move the consensus, and outliers near kickoff are common.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import american_to_prob, devig

# The Odds API uses full club names; nflverse uses abbreviations.
# Note LA (not LAR) for the Rams - nflverse's convention.
TEAM_MAP = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL", "Denver Broncos": "DEN",
    "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN", "New England Patriots": "NE",
    "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}


def load_backfill(pattern: str = "data/backfill/nfl_*.jsonl") -> pd.DataFrame:
    rows = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    if not rows:
        raise RuntimeError("no backfill data found - run engine.backfill first")
    df = pd.DataFrame(rows)
    df["home_abbr"] = df["home"].map(TEAM_MAP)
    df["away_abbr"] = df["away"].map(TEAM_MAP)
    unmapped = df[df["home_abbr"].isna() | df["away_abbr"].isna()]
    if not unmapped.empty:
        bad = sorted(set(unmapped["home"]) | set(unmapped["away"]))
        raise RuntimeError(f"unmapped team names: {bad}")
    return df


def consensus(df: pd.DataFrame) -> pd.DataFrame:
    """One consensus closing row per game."""
    key = ["season", "home_abbr", "away_abbr"]
    out = []

    for k, g in df.groupby(key, sort=False):
        season, home, away = k
        rec = {"season": season, "home_team": home, "away_team": away,
               "n_books": g["book"].nunique()}

        # Spread, stated from the home side. side_a line is the home handicap;
        # nflverse states spread_line as "home favoured by", so flip the sign.
        sp = g[(g["market"] == "spread") & (g["selection"] == "side_a")]["line"]
        rec["close_spread"] = -float(np.median(sp)) if len(sp) else np.nan

        tot = g[(g["market"] == "total") & (g["selection"] == "over")]["line"]
        rec["close_total"] = float(np.median(tot)) if len(tot) else np.nan

        # Moneyline consensus, then de-vig. Median the implied probabilities
        # rather than the prices - averaging American odds across the +/-100
        # discontinuity is meaningless.
        mh = g[(g["market"] == "moneyline") & (g["selection"] == "side_a")]["price"]
        ma = g[(g["market"] == "moneyline") & (g["selection"] == "side_b")]["price"]
        if len(mh) and len(ma):
            ph = float(np.median([american_to_prob(int(p)) for p in mh]))
            pa = float(np.median([american_to_prob(int(p)) for p in ma]))
            rec["close_p_home"], _ = devig(ph, pa)
        else:
            rec["close_p_home"] = np.nan

        out.append(rec)

    return pd.DataFrame(out)


def compare_to_nflverse(cons: pd.DataFrame, games: pd.DataFrame) -> dict:
    """Quantify how far nflverse's spread_line sits from the real close."""
    g = games[games["home_score"].notna()].copy()
    m = cons.merge(
        g[["season", "home_team", "away_team", "spread_line", "total_line",
           "home_moneyline", "away_moneyline", "home_score", "away_score"]],
        on=["season", "home_team", "away_team"], how="inner",
    )
    m["margin"] = m["home_score"] - m["away_score"]
    m["spread_delta"] = m["spread_line"] - m["close_spread"]
    m["total_delta"] = m["total_line"] - m["close_total"]

    valid = m.dropna(subset=["spread_delta"])
    return {
        "matched_games": len(m),
        "mean_abs_spread_delta": round(float(valid["spread_delta"].abs().mean()), 3),
        "median_abs_spread_delta": round(float(valid["spread_delta"].abs().median()), 3),
        "pct_spread_differs": round(float((valid["spread_delta"].abs() > 1e-9).mean()), 4),
        "pct_spread_differs_by_half_pt_or_more": round(
            float((valid["spread_delta"].abs() >= 0.5).mean()), 4),
        "pct_spread_differs_by_full_pt_or_more": round(
            float((valid["spread_delta"].abs() >= 1.0).mean()), 4),
        "frame": m,
    }
