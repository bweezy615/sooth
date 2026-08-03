"""Walk-forward ensemble: Elo + EPA, optionally anchored to the market.

Three models are compared honestly against the same games:

  elo        the existing baseline
  ensemble   Elo + opponent-aware EPA ratings + rest, no market input
  anchored   the above, plus the de-vigged market probability as a feature

The distinction matters commercially. ``ensemble`` answers "what do we think
on our own evidence?" - it is the number worth publishing, because it is
independent of the line and can therefore disagree with it informatively.
``anchored`` answers "what is the best calibrated probability we can produce?"
- it will be better calibrated and almost entirely uninformative as a bet,
because it mostly reproduces the market.

Publishing the anchored number as though it were our own opinion would be
dishonest: it would look accurate while containing almost no independent
information. We report both and label them.

Every fit is walk-forward: the model predicting season S is trained only on
seasons before S, refit each year.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ..adapters.nfl import NFLAdapter
from ..calibrate import expected_calibration_error, reliability
from ..features import attach_to_games, build_team_ratings, load_team_weeks
from ..models.elo import EloConfig, EloModel
from ..schema import american_to_prob, devig

EPS = 1e-6

BASE_FEATURES = ["elo_logit", "epa_edge", "off_diff", "def_diff",
                 "rest_diff", "div_game", "is_playoff"]
MARKET_FEATURE = "market_logit"


def _logit(p: np.ndarray | pd.Series) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def build_frame(start_season: int = 1999, end_season: int = 2025) -> pd.DataFrame:
    """One row per completed game with every feature, all leakage-safe."""
    adapter = NFLAdapter()
    games = adapter.games
    ratings = build_team_ratings(load_team_weeks(start_season, end_season))
    g = attach_to_games(games, ratings)

    g = g[
        g["home_score"].notna()
        & g["away_score"].notna()
        & g["season"].between(start_season, end_season)
    ].sort_values(["season", "week", "gameday"]).copy()

    # --- Elo, walk-forward: predict before update -------------------------
    model = EloModel(config=EloConfig())
    elo_p, elo_spread = [], []
    for _, r in g.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        neutral = str(r.get("location", "Home")) != "Home"
        rd = pd.to_numeric(r.get("home_rest"), errors="coerce") - pd.to_numeric(
            r.get("away_rest"), errors="coerce"
        )
        rd = 0.0 if pd.isna(rd) else float(rd)
        season = int(r["season"])
        p = model.expected(home, away, neutral=neutral, rest_diff=rd, season=season)
        elo_p.append(p)
        elo_spread.append(model.expected_margin(p))
        margin = float(r["home_score"]) - float(r["away_score"])
        model.update(home, away, margin, neutral=neutral, rest_diff=rd,
                     season=season)

    g["elo_p"] = elo_p
    g["elo_spread"] = elo_spread
    g["elo_logit"] = _logit(g["elo_p"])

    # --- market, de-vigged -------------------------------------------------
    def _mkt(row):
        h, a = row.get("home_moneyline"), row.get("away_moneyline")
        if pd.isna(h) or pd.isna(a):
            return np.nan
        mh, _ = devig(american_to_prob(int(h)), american_to_prob(int(a)))
        return mh

    g["market_p"] = g.apply(_mkt, axis=1)
    g["market_logit"] = _logit(g["market_p"].fillna(0.5))

    g["margin"] = g["home_score"] - g["away_score"]
    g["home_won"] = (g["margin"] > 0).astype(int)
    g["rest_diff"] = pd.to_numeric(g["home_rest"], errors="coerce") - pd.to_numeric(
        g["away_rest"], errors="coerce"
    )
    g["div_game"] = pd.to_numeric(g["div_game"], errors="coerce").fillna(0)
    g["is_playoff"] = (g["game_type"] != "REG").astype(int)

    for c in BASE_FEATURES:
        g[c] = pd.to_numeric(g[c], errors="coerce")

    return g[g["margin"] != 0].reset_index(drop=True)


def _walk_forward(frame: pd.DataFrame, features: list[str], label: str,
                  test_from: int) -> pd.Series:
    """Refit each season on strictly prior seasons."""
    out = pd.Series(np.nan, index=frame.index, name=label)
    for season in sorted(frame.loc[frame["season"] >= test_from, "season"].unique()):
        train = frame[frame["season"] < season].dropna(subset=features + ["home_won"])
        test = frame[frame["season"] == season]
        test_ok = test.dropna(subset=features)
        if len(train) < 500 or test_ok.empty:
            continue
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(train[features], train["home_won"])
        out.loc[test_ok.index] = clf.predict_proba(test_ok[features])[:, 1]
    return out


@dataclass
class Comparison:
    table: pd.DataFrame
    frame: pd.DataFrame

    def summary(self) -> str:
        return self.table.to_string(index=False)


def _ats(frame: pd.DataFrame, prob_col: str) -> tuple[int, int, int]:
    d = frame.dropna(subset=[prob_col, "spread_line"]).copy()
    if d.empty:
        return 0, 0, 0
    # Convert probability to an implied margin via the Elo scale, then bet the
    # side the model prefers relative to the posted number.
    implied = np.log(np.clip(d[prob_col], EPS, 1 - EPS) /
                     (1 - np.clip(d[prob_col], EPS, 1 - EPS))) * (400 / np.log(10))
    implied_margin = implied / 25.0
    pick_home = implied_margin > d["spread_line"]
    cover = d["margin"] - d["spread_line"]
    win = ((cover > 0) == pick_home) & (cover != 0)
    push = cover == 0
    return int(win.sum()), int((~win & ~push).sum()), int(push.sum())


def run(test_from: int = 2016, test_to: int = 2025) -> Comparison:
    frame = build_frame(1999, test_to)

    frame["p_ensemble"] = _walk_forward(frame, BASE_FEATURES, "p_ensemble", test_from)
    frame["p_anchored"] = _walk_forward(
        frame, BASE_FEATURES + [MARKET_FEATURE], "p_anchored", test_from
    )

    test = frame[
        (frame["season"] >= test_from)
        & frame["market_p"].notna()
        & frame["p_ensemble"].notna()
        & frame["p_anchored"].notna()
    ].copy()

    y = test["home_won"].to_numpy(float)
    rows = []
    for label, col in (("elo (baseline)", "elo_p"),
                       ("ensemble (no market)", "p_ensemble"),
                       ("anchored (+market)", "p_anchored"),
                       ("market (de-vigged)", "market_p")):
        p = test[col].to_numpy(float)
        w, l, pu = _ats(test, col)
        played = w + l
        rows.append({
            "model": label,
            "n": len(p),
            "brier": round(float(np.mean((p - y) ** 2)), 5),
            "log_loss": round(float(-np.mean(
                y * np.log(np.clip(p, EPS, 1 - EPS))
                + (1 - y) * np.log(np.clip(1 - p, EPS, 1 - EPS)))), 5),
            "acc": round(float(np.mean((p > 0.5) == (y == 1))), 4),
            "ECE": round(expected_calibration_error(p, y), 5),
            "ATS": f"{w}-{l}-{pu}",
            "ATS%": round(w / played, 4) if played else float("nan"),
        })

    return Comparison(table=pd.DataFrame(rows), frame=test)


if __name__ == "__main__":
    c = run()
    print(c.summary())
    print()
    print("breakeven ATS at -110 = 0.5238")
    print()
    print("ensemble reliability (our publishable, market-independent number):")
    print(reliability(c.frame["p_ensemble"].to_numpy(float),
                      c.frame["home_won"].to_numpy(float)).to_string(index=False))
