"""Elo with margin-of-victory damping - the transparent baseline.

Deliberately simple and fully explainable. Its job is not to beat the market;
its job is to be an honest, calibrated starting point that we can publish,
grade in public, and improve on during the season.

Every rating is produced walk-forward: a game's prediction only ever uses
ratings built from strictly earlier games. There is no fitting on the future.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np


@dataclass
class EloConfig:
    k: float = 20.0
    # Points of home-field advantage, expressed in Elo. ~48 Elo ~= 2 points.
    home_advantage: float = 48.0
    # Fraction of a team's rating carried into the next season.
    season_carryover: float = 0.75
    base_rating: float = 1500.0
    # Elo points per point of scoring margin, used to convert to a spread.
    elo_per_point: float = 25.0
    # Elo bonus per extra day of rest.
    rest_per_day: float = 1.5


@dataclass
class EloModel:
    config: EloConfig = field(default_factory=EloConfig)
    ratings: dict[str, float] = field(default_factory=dict)
    _last_season: int | None = None

    version: str = "elo-mov-v1"

    # -- core ------------------------------------------------------------------

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self.config.base_rating)

    def _roll_season(self, season: int) -> None:
        """Regress every rating toward the mean between seasons."""
        if self._last_season is not None and season != self._last_season:
            c = self.config
            for t, r in self.ratings.items():
                self.ratings[t] = (
                    c.base_rating + (r - c.base_rating) * c.season_carryover
                )
        self._last_season = season

    def expected(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        rest_diff: float = 0.0,
        season: int | None = None,
    ) -> float:
        """Probability the home side wins."""
        if season is not None:
            self._roll_season(season)
        c = self.config
        diff = self.rating(home) - self.rating(away)
        if not neutral:
            diff += c.home_advantage
        if np.isfinite(rest_diff):
            diff += c.rest_per_day * float(rest_diff)
        return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))

    def expected_margin(self, prob_home: float) -> float:
        """Convert a win probability back into an expected point margin."""
        prob_home = min(max(prob_home, 1e-6), 1 - 1e-6)
        elo_diff = -400.0 * np.log10(1.0 / prob_home - 1.0)
        return elo_diff / self.config.elo_per_point

    def update(
        self,
        home: str,
        away: str,
        margin: float,
        *,
        neutral: bool = False,
        rest_diff: float = 0.0,
        season: int | None = None,
    ) -> None:
        """Apply one settled result.

        The margin-of-victory multiplier is the standard log-damped form: it
        rewards big wins without letting a blowout dominate, and it corrects
        for the autocorrelation between rating gap and margin.
        """
        p_home = self.expected(
            home, away, neutral=neutral, rest_diff=rest_diff, season=season
        )
        actual = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
        c = self.config
        elo_diff = self.rating(home) - self.rating(away) + (
            0.0 if neutral else c.home_advantage
        )
        winner_diff = elo_diff if margin > 0 else -elo_diff
        mov_mult = np.log(abs(margin) + 1.0) * (2.2 / (winner_diff * 0.001 + 2.2))
        delta = c.k * mov_mult * (actual - p_home)
        self.ratings[home] = self.rating(home) + delta
        self.ratings[away] = self.rating(away) - delta
