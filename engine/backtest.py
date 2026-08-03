"""Walk-forward backtest and honest scoring.

The whole point of this file is to be hard to fool. It reports what the model
actually does, including the comparison that matters most: are we better than
the de-vigged market? If the answer is no, that is the finding, and we publish
it rather than tuning until the number looks good.

Metrics
-------
Brier score   - mean squared error of probabilities. Lower is better.
Log loss      - punishes confident errors harder. Lower is better.
Calibration   - do 70%-confidence picks actually win ~70% of the time?
ATS record    - against the spread, the only record a bettor cares about.
Market delta  - our Brier minus the de-vigged market's Brier. Negative = we win.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .adapters.nfl import NFLAdapter
from .models.elo import EloConfig, EloModel
from .schema import american_to_prob, devig


@dataclass
class BacktestReport:
    n: int
    brier: float
    log_loss: float
    accuracy: float
    market_brier: float
    market_log_loss: float
    market_accuracy: float
    ats_wins: int
    ats_losses: int
    ats_pushes: int
    calibration: pd.DataFrame
    frame: pd.DataFrame

    @property
    def brier_delta(self) -> float:
        """Negative means we beat the de-vigged market."""
        return self.brier - self.market_brier

    @property
    def ats_pct(self) -> float:
        played = self.ats_wins + self.ats_losses
        return self.ats_wins / played if played else float("nan")

    def summary(self) -> str:
        beat = "BEATS" if self.brier_delta < 0 else "LOSES TO"
        return "\n".join(
            [
                f"games graded          : {self.n}",
                "",
                f"model  Brier          : {self.brier:.5f}",
                f"market Brier (devig)  : {self.market_brier:.5f}",
                f"delta                 : {self.brier_delta:+.5f}  -> model {beat} market",
                "",
                f"model  log loss       : {self.log_loss:.5f}",
                f"market log loss       : {self.market_log_loss:.5f}",
                "",
                f"model  SU accuracy    : {self.accuracy:.4f}",
                f"market SU accuracy    : {self.market_accuracy:.4f}",
                "",
                f"ATS record            : {self.ats_wins}-{self.ats_losses}-{self.ats_pushes}"
                f"  ({self.ats_pct:.4f})",
                f"ATS breakeven at -110 : 0.5238",
                "",
                "calibration (model):",
                self.calibration.to_string(index=False),
            ]
        )


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        rows.append(
            {
                "bucket": f"{edges[b]:.1f}-{edges[b + 1]:.1f}",
                "n": int(m.sum()),
                "predicted": round(float(p[m].mean()), 4),
                "actual": round(float(y[m].mean()), 4),
                "gap": round(float(p[m].mean() - y[m].mean()), 4),
            }
        )
    return pd.DataFrame(rows)


def run(
    start_season: int = 1999,
    train_through: int = 2015,
    test_from: int = 2016,
    test_to: int = 2025,
    config: EloConfig | None = None,
) -> BacktestReport:
    """Walk forward through history, predicting each game before grading it."""
    adapter = NFLAdapter()
    df = adapter.games
    df = df[
        df["home_score"].notna()
        & df["away_score"].notna()
        & df["season"].between(start_season, test_to)
    ].sort_values(["season", "week", "gameday"])

    model = EloModel(config=config or EloConfig())
    records: list[dict] = []

    for _, r in df.iterrows():
        season = int(r["season"])
        home, away = str(r["home_team"]), str(r["away_team"])
        margin = float(r["home_score"]) - float(r["away_score"])
        neutral = str(r.get("location", "Home")) != "Home"
        rest_diff = pd.to_numeric(r.get("home_rest"), errors="coerce") - pd.to_numeric(
            r.get("away_rest"), errors="coerce"
        )
        rest_diff = 0.0 if pd.isna(rest_diff) else float(rest_diff)

        # PREDICT FIRST - using only ratings built from earlier games.
        p_home = model.expected(
            home, away, neutral=neutral, rest_diff=rest_diff, season=season
        )

        if season >= test_from and margin != 0:
            hml, aml = r.get("home_moneyline"), r.get("away_moneyline")
            spread = r.get("spread_line")
            rec = {
                "season": season,
                "week": r["week"],
                "game_id": r["game_id"],
                "home": home,
                "away": away,
                "p_home": p_home,
                "home_won": 1 if margin > 0 else 0,
                "margin": margin,
                "model_spread": model.expected_margin(p_home),
                "spread_line": float(spread) if pd.notna(spread) else np.nan,
            }
            if pd.notna(hml) and pd.notna(aml):
                mh, ma = devig(american_to_prob(int(hml)), american_to_prob(int(aml)))
                rec["market_p_home"] = mh
            else:
                rec["market_p_home"] = np.nan
            records.append(rec)

        # THEN grade and update.
        model.update(
            home, away, margin, neutral=neutral, rest_diff=rest_diff, season=season
        )

    frame = pd.DataFrame(records)
    graded = frame.dropna(subset=["market_p_home"]).copy()

    y = graded["home_won"].to_numpy(dtype=float)
    p = graded["p_home"].to_numpy(dtype=float)
    mp = graded["market_p_home"].to_numpy(dtype=float)

    # Against the spread: we bet the side our model likes vs the posted number.
    ats = graded.dropna(subset=["spread_line"]).copy()
    # nflverse spread_line is home-favoured-by, so home covers when
    # margin > spread_line.
    ats["home_cover_margin"] = ats["margin"] - ats["spread_line"]
    ats["pick_home"] = ats["model_spread"] > ats["spread_line"]
    ats["result"] = np.where(
        ats["home_cover_margin"] == 0,
        "push",
        np.where(
            (ats["home_cover_margin"] > 0) == ats["pick_home"], "win", "loss"
        ),
    )
    counts = ats["result"].value_counts()

    return BacktestReport(
        n=len(graded),
        brier=float(np.mean((p - y) ** 2)),
        log_loss=_log_loss(y, p),
        accuracy=float(np.mean((p > 0.5) == (y == 1))),
        market_brier=float(np.mean((mp - y) ** 2)),
        market_log_loss=_log_loss(y, mp),
        market_accuracy=float(np.mean((mp > 0.5) == (y == 1))),
        ats_wins=int(counts.get("win", 0)),
        ats_losses=int(counts.get("loss", 0)),
        ats_pushes=int(counts.get("push", 0)),
        calibration=_calibration(y, p),
        frame=graded,
    )


if __name__ == "__main__":
    print(run().summary())
