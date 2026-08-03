"""Probability calibration.

A calibrated probability is the one honest thing we can actually promise. It
means: when we say 70%, that outcome happens about 70% of the time. It says
nothing about whether betting our picks is profitable - those are separate
claims, and conflating them is the central dishonesty of the pick-selling
industry.

The backtest showed the raw Elo model is mildly overconfident in the middle
bands. Isotonic regression fixes that shape without assuming it is a logistic
curve.

Calibration is fitted ONLY on seasons strictly before the season being
predicted, refitted each year. Fitting on the same games we then score would
manufacture a perfect-looking reliability curve that means nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression


@dataclass
class Calibrator:
    model: IsotonicRegression | None = None
    fitted_through: int | None = None

    def fit(self, probs: np.ndarray, outcomes: np.ndarray, through_season: int):
        iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
        iso.fit(probs, outcomes)
        self.model = iso
        self.fitted_through = through_season
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        if self.model is None:
            return probs
        return np.asarray(self.model.predict(probs))


def reliability(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(probs, edges) - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        rows.append(
            {
                "bucket": f"{edges[b]:.1f}-{edges[b + 1]:.1f}",
                "n": int(m.sum()),
                "predicted": round(float(probs[m].mean()), 4),
                "actual": round(float(outcomes[m].mean()), 4),
                "gap": round(float(probs[m].mean() - outcomes[m].mean()), 4),
            }
        )
    return pd.DataFrame(rows)


def expected_calibration_error(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """Weighted mean absolute gap between predicted and actual. Lower is better.

    This is the single number we publish as our calibration claim, because it
    is objectively measurable and does not imply profitability.
    """
    tbl = reliability(probs, outcomes, bins)
    if tbl.empty:
        return float("nan")
    w = tbl["n"] / tbl["n"].sum()
    return float((w * tbl["gap"].abs()).sum())


def walk_forward_calibrate(frame: pd.DataFrame) -> pd.DataFrame:
    """Refit the calibrator each season using only prior seasons.

    ``frame`` needs columns: season, p_home, home_won.
    Returns the frame with a ``p_home_cal`` column added.
    """
    out = frame.sort_values("season").copy()
    out["p_home_cal"] = np.nan
    seasons = sorted(out["season"].unique())

    for season in seasons:
        prior = out[out["season"] < season]
        cur = out["season"] == season
        if len(prior) < 500:  # not enough history yet - pass through uncalibrated
            out.loc[cur, "p_home_cal"] = out.loc[cur, "p_home"]
            continue
        cal = Calibrator().fit(
            prior["p_home"].to_numpy(dtype=float),
            prior["home_won"].to_numpy(dtype=float),
            through_season=int(season) - 1,
        )
        out.loc[cur, "p_home_cal"] = cal.transform(
            out.loc[cur, "p_home"].to_numpy(dtype=float)
        )
    return out
