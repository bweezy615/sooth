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
from sklearn.linear_model import LogisticRegression, Ridge

from ..adapters.nfl import NFLAdapter
from ..calibrate import expected_calibration_error, reliability
from ..features import attach_to_games, build_team_ratings, load_team_weeks
from ..models.elo import EloConfig, EloModel
from ..schema import american_to_prob, devig

EPS = 1e-6

BASE_FEATURES = ["elo_logit", "epa_edge", "off_diff", "def_diff",
                 "rest_diff", "div_game", "is_playoff"]
MARKET_FEATURE = "market_logit"

# How far our predicted margin must sit from the posted number before we are
# willing to say anything. Measured, not chosen for roundness — see
# ``selectivity()`` and docs/plans/pick-engine-selectivity.md. Below this the
# model's disagreement with the line is inside its own error bar.
EDGE_THRESHOLD = 4.0


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


def _wf_margin(frame: pd.DataFrame, features: list[str], label: str,
               test_from: int) -> pd.Series:
    """Walk-forward regression predicting the actual margin, in points.

    The probability models above answer "who wins". A spread is a question
    about BY HOW MUCH, and until 2026-08 this file answered it by pushing a
    win probability through ``logit(p) * 400/ln(10) / 25``. That divisor is
    the Elo points-per-rating-point scale; a scikit-learn logit is on no such
    scale, so the conversion shifted every pick's threshold against the number
    by an arbitrary factor. Regressing on ``margin`` asks the question
    directly and needs no conversion at all.
    """
    out = pd.Series(np.nan, index=frame.index, name=label)
    for season in sorted(frame.loc[frame["season"] >= test_from, "season"].unique()):
        train = frame[frame["season"] < season].dropna(subset=features + ["margin"])
        test_ok = frame[frame["season"] == season].dropna(subset=features)
        if len(train) < 500 or test_ok.empty:
            continue
        reg = Ridge(alpha=1.0).fit(train[features], train["margin"])
        out.loc[test_ok.index] = reg.predict(test_ok[features])
    return out


def wilson(wins: int, played: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval on a win rate. Published beside every rate we quote.

    A selective record is a small record, and a small record without its
    interval is the thing this site exists to argue against.
    """
    if played <= 0:
        return (float("nan"), float("nan"))
    p, n = wins / played, played
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (float((c - m) / d), float((c + m) / d))


@dataclass
class Comparison:
    table: pd.DataFrame
    frame: pd.DataFrame

    def summary(self) -> str:
        return self.table.to_string(index=False)


def ats_frame(frame: pd.DataFrame, margin_col: str,
              spread_col: str = "spread_line") -> pd.DataFrame:
    """Grade one predicted-margin column against one posted number.

    ``spread_line`` is on the home basis and positive when the home side is
    laying points, so ``edge = predicted margin - spread`` is positive exactly
    when we like the home side, and its absolute size is how far we sit from
    the number in points. That single quantity drives the pick, the
    selectivity threshold and the underdog flag.
    """
    d = frame.dropna(subset=[margin_col, spread_col, "margin"]).copy()
    if d.empty:
        return d.assign(edge=[], pick_home=[], underdog=[], win=[], push=[])
    d["edge"] = d[margin_col] - d[spread_col]
    d["pick_home"] = d["edge"] > 0
    d["underdog"] = np.where(d["pick_home"], d[spread_col] < 0, d[spread_col] > 0)
    cover = d["margin"] - d[spread_col]
    d["push"] = cover == 0
    d["win"] = ((cover > 0) == d["pick_home"]) & ~d["push"]
    return d


def _ats(frame: pd.DataFrame, margin_col: str,
         spread_col: str = "spread_line") -> tuple[int, int, int]:
    d = ats_frame(frame, margin_col, spread_col)
    if d.empty:
        return 0, 0, 0
    return (int(d["win"].sum()), int((~d["win"] & ~d["push"]).sum()),
            int(d["push"].sum()))


def _record(d: pd.DataFrame) -> dict:
    w = int(d["win"].sum())
    p = int(d["push"].sum())
    losses = int(len(d) - w - p)
    played = w + losses
    lo, hi = wilson(w, played)
    return {"n": int(len(d)), "record": f"{w}-{losses}-{p}",
            "pct": round(w / played, 4) if played else None,
            "ci95": [round(lo, 4), round(hi, 4)] if played else None,
            "per_season": (round(played / max(d["season"].nunique(), 1), 1)
                           if played else 0.0)}


def selectivity(frame: pd.DataFrame, margin_col: str,
                spread_col: str = "spread_line",
                thresholds=(0.0, 2.0, 3.0, 4.0, 5.0)) -> dict:
    """ATS record as a function of how much we are allowed to say.

    The engine's worst habit is having an opinion on all sixteen games. This
    is the measurement of what happens when it is allowed to stay quiet: each
    row is the record over games where the model sits at least ``edge`` points
    off the posted number, split by whether the resulting play is the dog or
    the favourite.
    """
    d = ats_frame(frame, margin_col, spread_col)
    out = {"thresholds": [], "by_season": {}}
    for t in thresholds:
        sel = d[d["edge"].abs() >= t]
        out["thresholds"].append({
            "edge": t,
            "all": _record(sel),
            "underdog": _record(sel[sel["underdog"]]),
            "favourite": _record(sel[~sel["underdog"]]),
        })
    # The underdog column is reported, NOT filtered on, and the reason is the
    # whole argument for running two evaluations. On nflverse lines the dog
    # side at this threshold looks much the better half (54.8% vs 48.6%). On
    # real captured closes the split reverses (52.4% dog vs 56.0% favourite).
    # A split that flips sign when the line provenance improves is a property
    # of the line source, not of football, and gating on it would be fitting
    # the shipped rule to the worse of our two datasets. The THRESHOLD holds on
    # both (53.2% and 53.6%), so the threshold is what ships.
    live = d[d["edge"].abs() >= EDGE_THRESHOLD]
    for season, chunk in live.groupby("season"):
        out["by_season"][str(int(season))] = _record(chunk)
    out["rule"] = f"absolute edge >= {EDGE_THRESHOLD} points"
    out["live"] = _record(live)
    return out


def run(test_from: int = 2016, test_to: int = 2025) -> Comparison:
    frame = build_frame(1999, test_to)

    frame["p_ensemble"] = _walk_forward(frame, BASE_FEATURES, "p_ensemble", test_from)
    frame["p_anchored"] = _walk_forward(
        frame, BASE_FEATURES + [MARKET_FEATURE], "p_anchored", test_from
    )

    # Each model's own answer to "by how many points". Elo already has one of
    # its own; the market's comes from a fitted regression on its de-vigged
    # price rather than the Elo constant this file used to borrow.
    frame["m_ensemble"] = _wf_margin(frame, BASE_FEATURES, "m_ensemble", test_from)
    frame["m_anchored"] = _wf_margin(
        frame, BASE_FEATURES + [MARKET_FEATURE], "m_anchored", test_from)
    frame["m_market"] = _wf_margin(frame, [MARKET_FEATURE], "m_market", test_from)

    test = frame[
        (frame["season"] >= test_from)
        & frame["market_p"].notna()
        & frame["p_ensemble"].notna()
        & frame["p_anchored"].notna()
    ].copy()

    y = test["home_won"].to_numpy(float)
    rows = []
    for label, col, mcol in (("elo (baseline)", "elo_p", "elo_spread"),
                             ("ensemble (no market)", "p_ensemble", "m_ensemble"),
                             ("anchored (+market)", "p_anchored", "m_anchored"),
                             ("market (de-vigged)", "market_p", "m_market")):
        p = test[col].to_numpy(float)
        w, l, pu = _ats(test, mcol)
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
    sel = selectivity(c.frame, "m_ensemble")
    print("what happens when the engine is allowed to stay quiet:")
    print(f"{'edge':>5} {'all':>18} {'underdog':>18} {'favourite':>18}")
    for t in sel["thresholds"]:
        def cell(r):
            return "-" if r["pct"] is None else f"{r['record']} {r['pct']:.4f}"
        print(f"{t['edge']:>5} {cell(t['all']):>18} {cell(t['underdog']):>18} "
              f"{cell(t['favourite']):>18}")
    print()
    live = sel["live"]
    print(f"shipped rule: {sel['rule']}")
    print(f"  {live['record']}  {live['pct']}  95% CI {live['ci95']}  "
          f"~{live['per_season']} plays/season")
    print("  per season: " + ", ".join(
        f"{s} {r['record']}" for s, r in sorted(sel["by_season"].items())))
    print()
    print("ensemble reliability (our publishable, market-independent number):")
    print(reliability(c.frame["p_ensemble"].to_numpy(float),
                      c.frame["home_won"].to_numpy(float)).to_string(index=False))
