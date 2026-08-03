"""Opponent-aware EPA team ratings, built strictly walk-forward.

Elo only knows who won. Expected points added knows how a team actually
played, which is a far less noisy signal in a 17-game season - a team can win
three one-score games while being comfortably outplayed, and Elo will happily
rate them up.

Source: nflverse ``stats_team_week_YYYY.csv`` (~200KB per season, no auth).
We use the aggregated weekly file rather than raw play-by-play because it is
three orders of magnitude smaller and contains the EPA totals we need.

THE LEAKAGE RULE
----------------
Every rating for a game in (season S, week W) is computed from games strictly
earlier than it. This is enforced by shifting each team's rolling series by one
game *before* it is joined onto the fixture, not by filtering afterwards. Doing
it afterwards is the classic way this goes wrong: the rolling mean has already
absorbed the current game, and the backtest looks superb.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import requests

TEAM_WEEK_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_team/stats_team_week_{season}.csv"
)

# Exponential half-life in games. ~8 games ≈ half a season, which is roughly
# where NFL team strength stops being informative about the current week.
HALFLIFE = 8.0
# Fraction of a rating carried into the next season, matching the Elo config.
SEASON_CARRYOVER = 0.75


def load_team_weeks(
    start: int = 1999,
    end: int = 2026,
    cache_dir: Path | str = "data/raw/team_weeks",
) -> pd.DataFrame:
    """Download (once) and concatenate weekly team stats."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for season in range(start, end + 1):
        path = cache / f"team_week_{season}.csv"
        if not path.exists():
            resp = requests.get(TEAM_WEEK_URL.format(season=season), timeout=60)
            if resp.status_code != 200:
                continue  # season not published yet
            path.write_bytes(resp.content)
        try:
            frames.append(pd.read_csv(path, low_memory=False))
        except pd.errors.EmptyDataError:
            continue
    if not frames:
        raise RuntimeError("no team-week data available")
    return pd.concat(frames, ignore_index=True)


def _per_play_epa(tw: pd.DataFrame) -> pd.DataFrame:
    """Collapse to one row per team-game with offensive EPA per play."""
    df = tw.copy()
    for col in ("passing_epa", "rushing_epa", "attempts", "carries",
                "sacks_suffered"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["off_epa"] = df["passing_epa"] + df["rushing_epa"]
    df["plays"] = df["attempts"] + df["carries"] + df["sacks_suffered"]
    df = df[df["plays"] >= 20]  # drop fragments; a real game has ~60 plays
    df["off_epa_pp"] = df["off_epa"] / df["plays"]

    keep = ["season", "week", "team", "opponent_team", "game_id",
            "off_epa_pp", "plays"]
    df = df[[c for c in keep if c in df.columns]].copy()

    # Defence is simply what the opponent managed against you in that game.
    opp = df[["game_id", "team", "off_epa_pp"]].rename(
        columns={"team": "opponent_team", "off_epa_pp": "def_epa_pp"}
    )
    df = df.merge(opp, on=["game_id", "opponent_team"], how="left")
    return df.sort_values(["season", "week", "team"]).reset_index(drop=True)


def build_team_ratings(tw: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per team-week ratings usable as features for THAT week's game.

    Returns columns: season, week, team, off_rating, def_rating, games_seen.
    The rating attached to (S, W) reflects only games before (S, W).
    """
    if tw is None:
        tw = load_team_weeks()
    df = _per_play_epa(tw)

    out = []
    for team, grp in df.groupby("team", sort=False):
        g = grp.sort_values(["season", "week"]).copy()

        # Shift FIRST: the value on row i must not include row i's own game.
        for src, dst in (("off_epa_pp", "off_rating"),
                         ("def_epa_pp", "def_rating")):
            prior = g[src].shift(1)
            g[dst] = prior.ewm(halflife=HALFLIFE, ignore_na=True).mean()

        g["games_seen"] = np.arange(len(g))

        # Regress toward the mean at each season boundary, so a team does not
        # start September carrying last January's rating at full weight.
        new_season = g["season"].ne(g["season"].shift(1)) & (g["games_seen"] > 0)
        for col in ("off_rating", "def_rating"):
            g.loc[new_season, col] = g.loc[new_season, col] * SEASON_CARRYOVER

        out.append(g[["season", "week", "team", "off_rating", "def_rating",
                      "games_seen"]])

    ratings = pd.concat(out, ignore_index=True)
    return ratings.sort_values(["season", "week", "team"]).reset_index(drop=True)


def attach_to_games(games: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Join home/away ratings onto a games frame and form differentials."""
    g = games.copy()
    g["week"] = pd.to_numeric(g["week"], errors="coerce")

    for side, prefix in (("home_team", "home"), ("away_team", "away")):
        r = ratings.rename(
            columns={
                "team": side,
                "off_rating": f"{prefix}_off",
                "def_rating": f"{prefix}_def",
                "games_seen": f"{prefix}_seen",
            }
        )
        g = g.merge(r, on=["season", "week", side], how="left")

    # Positive favours the home side in both cases: better offence, and an
    # opponent defence that concedes more.
    g["off_diff"] = g["home_off"] - g["away_off"]
    g["def_diff"] = g["away_def"] - g["home_def"]
    g["epa_edge"] = (g["home_off"] - g["home_def"]) - (
        g["away_off"] - g["away_def"]
    )
    return g


def carry_forward_ratings(ratings: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """Each team's most recent rating as of (season, week), carried forward.

    Needed because a fixture in a season that has not started yet has no
    team-week row of its own. Week 1 of 2026 must be predicted from ratings
    earned in 2025, regressed toward the mean exactly as the in-season
    boundary rule does - otherwise a team starts September carrying last
    January's form at full weight.
    """
    prior = ratings[
        (ratings["season"] < season)
        | ((ratings["season"] == season) & (ratings["week"] < week))
    ]
    if prior.empty:
        return pd.DataFrame(columns=["team", "off_rating", "def_rating", "games_seen"])

    latest = (
        prior.sort_values(["season", "week"])
        .groupby("team", as_index=False)
        .last()[["team", "off_rating", "def_rating", "games_seen"]]
    )
    # If the most recent rating predates this season, regress it.
    last_season = int(prior["season"].max())
    if last_season < season:
        for col in ("off_rating", "def_rating"):
            latest[col] = latest[col] * SEASON_CARRYOVER
    return latest


def attach_carry_forward(games: pd.DataFrame, ratings: pd.DataFrame,
                         season: int, week: int) -> pd.DataFrame:
    """Join carry-forward ratings onto upcoming fixtures."""
    latest = carry_forward_ratings(ratings, season, week)
    g = games.copy()
    for side, prefix in (("home_team", "home"), ("away_team", "away")):
        r = latest.rename(columns={
            "team": side, "off_rating": f"{prefix}_off",
            "def_rating": f"{prefix}_def", "games_seen": f"{prefix}_seen",
        })
        g = g.merge(r, on=side, how="left")
    g["off_diff"] = g["home_off"] - g["away_off"]
    g["def_diff"] = g["away_def"] - g["home_def"]
    g["epa_edge"] = (g["home_off"] - g["home_def"]) - (g["away_off"] - g["away_def"])
    return g
