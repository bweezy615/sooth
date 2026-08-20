"""Team form — the comparison panel, built from data we already compute.

Every matchup report opens with two columns of team numbers. This module
produces them. It is deliberately thin: the hard part (opponent-aware,
strictly walk-forward EPA ratings) already exists in ``engine.features`` and is
the same code the prediction model trains on. Recomputing it here with a
different half-life would give the site one set of numbers and the model
another, and the first person to notice would be right to stop trusting both.

Two kinds of number live in the output and they must not be confused:

**rating** — the forward-looking EWMA from ``features.build_team_ratings()``,
shifted so a team's rating for week W contains nothing from week W. This is a
feature. It is what the model sees.

**season / last5** — plain descriptive rates over games already played. These
are a record, not a forecast, and the panel labels them that way. A record
cannot leak, because it never claims to be about the future.

Both are per-play, never per-game: a team that runs 70 plays is not better at
football than one that ran 55, and totals reward the wrong side of pace.

Source is nflverse ``stats_team_week_<season>.csv``, cached under
``data/raw/team_weeks`` by ``features.load_team_weeks`` and shared with the
model. No auth, ~200KB a season.

    python -m engine.teamstats --sport nfl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd

from .closing import TEAM_MAP
from .features import build_team_ratings, carry_forward_ratings, load_team_weeks

# abbreviation -> full club name, the direction this module needs. TEAM_MAP is
# the single definition of the pairing (engine.closing) and stays that way.
ABBR_TO_NAME = {v: k for k, v in TEAM_MAP.items()}

# What the panel shows, in display order. ``better`` says which direction is
# good, so the page can highlight a column without hardcoding football.
METRICS = [
    {"key": "off_epa_pp", "label": "Off EPA/play", "better": "high", "dp": 3},
    {"key": "def_epa_pp", "label": "Def EPA/play", "better": "low", "dp": 3},
    {"key": "net_epa_pp", "label": "Net EPA/play", "better": "high", "dp": 3},
    {"key": "yards_pp", "label": "Yards/play", "better": "high", "dp": 2},
    {"key": "pass_rate", "label": "Pass rate", "better": None, "dp": 3},
    {"key": "cpoe", "label": "CPOE", "better": "high", "dp": 2},
    {"key": "first_down_rate", "label": "1st downs/play", "better": "high", "dp": 3},
    {"key": "explosive_rate", "label": "Explosive/play", "better": "high", "dp": 3},
    {"key": "turnover_rate", "label": "Giveaways/play", "better": "low", "dp": 4},
]

LAST_N = 5


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def per_game_rates(tw: pd.DataFrame) -> pd.DataFrame:
    """One row per team-game of descriptive per-play rates.

    Defence is not a separate feed: it is what the opponent managed against you
    in that same game, joined back on ``game_id``. That is how
    ``features._per_play_epa`` derives it and the two must agree.
    """
    df = tw.copy()
    plays = _num(df, "attempts") + _num(df, "carries") + _num(df, "sacks_suffered")
    df = df.assign(plays=plays)
    df = df[df["plays"] >= 20].copy()          # drop fragments, same floor as features

    p = df["plays"]
    df["off_epa_pp"] = (_num(df, "passing_epa") + _num(df, "rushing_epa")) / p
    df["yards_pp"] = (_num(df, "passing_yards") + _num(df, "rushing_yards")
                      - _num(df, "sack_yards_lost")) / p
    df["pass_rate"] = (_num(df, "attempts") + _num(df, "sacks_suffered")) / p
    df["cpoe"] = _num(df, "passing_cpoe")
    df["first_down_rate"] = (_num(df, "passing_first_downs")
                             + _num(df, "rushing_first_downs")) / p
    df["explosive_rate"] = (_num(df, "passing_20") + _num(df, "rushing_20")) / p
    df["turnover_rate"] = (_num(df, "passing_interceptions")
                           + _num(df, "sack_fumbles_lost")
                           + _num(df, "rushing_fumbles_lost")) / p

    keep = ["season", "week", "team", "opponent_team", "game_id", "plays",
            *[m["key"] for m in METRICS if m["key"] not in ("def_epa_pp", "net_epa_pp")]]
    df = df[[c for c in keep if c in df.columns]].copy()

    opp = df[["game_id", "team", "off_epa_pp"]].rename(
        columns={"team": "opponent_team", "off_epa_pp": "def_epa_pp"})
    df = df.merge(opp, on=["game_id", "opponent_team"], how="left")
    df["def_epa_pp"] = df["def_epa_pp"].fillna(0.0)
    df["net_epa_pp"] = df["off_epa_pp"] - df["def_epa_pp"]
    return df.sort_values(["season", "week", "team"]).reset_index(drop=True)


def _summarise(g: pd.DataFrame) -> dict:
    out = {}
    for m in METRICS:
        if m["key"] in g.columns:
            out[m["key"]] = round(float(g[m["key"]].mean()), m["dp"])
    out["games"] = int(len(g))
    return out


def records(games_csv: Path, season: int) -> dict[str, dict]:
    """W-L-T per team from completed games this season."""
    if not games_csv.exists():
        return {}
    g = pd.read_csv(games_csv, low_memory=False)
    g = g[(g["season"] == season) & g["result"].notna()]
    rec: dict[str, dict] = {}
    for _, row in g.iterrows():
        margin = float(row["result"])          # home score - away score
        for team, sign in ((row["home_team"], 1), (row["away_team"], -1)):
            r = rec.setdefault(team, {"w": 0, "l": 0, "t": 0})
            m = margin * sign
            r["w" if m > 0 else "l" if m < 0 else "t"] += 1
    for team, r in rec.items():
        r["display"] = (f"{r['w']}-{r['l']}" if not r["t"]
                        else f"{r['w']}-{r['l']}-{r['t']}")
    return rec


def build(season: int, week: int, out_dir: Path,
          root: Path = Path("."), dry_run: bool = False) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    tw = load_team_weeks(cache_dir=root / "data/raw/team_weeks")
    rates = per_game_rates(tw)
    ratings = build_team_ratings(tw)
    latest = carry_forward_ratings(ratings, season, week).set_index("team")
    rec = records(root / "data/raw/nfl_games.csv", season)

    teams: dict[str, dict] = {}
    for team, g in rates.groupby("team", sort=True):
        # nflverse carries historical abbreviations forever: JAC (pre-2016),
        # OAK, SD and STL all still appear in the frame and each one arrives
        # here with a "most recent season" of its own. Left alone they render
        # as four extra clubs in a 32-team league.
        #
        # Filtered, not renamed. Mapping OAK->LV would give the panel a longer
        # franchise history than features.build_team_ratings() gives the model,
        # and this file exists to keep those two answers identical. TEAM_MAP is
        # the roster of clubs that exist now; anything else is not a team.
        if team not in ABBR_TO_NAME:
            continue
        g = g.sort_values(["season", "week"])
        this_season = g[g["season"] == season]
        # Before Week 1 there is no current-season sample. Falling back to the
        # most recent completed season is honest as long as the panel says so,
        # which is what basis_season is for — an unlabelled 2025 number
        # presented as 2026 form is exactly the failure this file avoids.
        basis = this_season if len(this_season) else g[g["season"] == g["season"].max()]
        if basis.empty:
            continue
        r = latest.loc[team] if team in latest.index else None
        teams[team] = {
            "abbr": team,
            "name": ABBR_TO_NAME.get(team, team),
            "record": (rec.get(team) or {}).get("display"),
            "basis_season": int(basis["season"].iloc[-1]),
            "season": _summarise(basis),
            f"last{LAST_N}": _summarise(basis.tail(LAST_N)),
            "rating": None if r is None else {
                "off": round(float(r["off_rating"]), 4),
                "def": round(float(r["def_rating"]), 4),
                "net": round(float(r["off_rating"] - r["def_rating"]), 4),
                "games_seen": int(r["games_seen"]),
            },
        }

    doc = {
        "generated_at": now.isoformat(),
        "sport": "nfl",
        "season": season,
        "week": week,
        "last_n": LAST_N,
        "source": "nflverse stats_team_week",
        "note": ("Ratings are walk-forward and contain no game they are used to "
                 "describe. Season and last-5 columns are a record of games "
                 "already played, not a forecast."),
        "metrics": METRICS,
        "n_teams": len(teams),
        "teams": teams,
    }

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "teamstats-nfl.json"
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=1))
        os.replace(tmp, out)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", default="nfl", choices=["nfl"],
                    help="NBA arrives with its own metric list; the file shape does not change")
    ap.add_argument("--season", type=int, default=dt.date.today().year)
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--out-dir", default="site/public/data")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    doc = build(a.season, a.week, Path(a.out_dir), Path(a.root), a.dry_run)
    rated = sum(1 for t in doc["teams"].values() if t["rating"])
    print(f"{doc['n_teams']} teams, {rated} with carry-forward ratings "
          f"(season {a.season} week {a.week})")
    for abbr in list(doc["teams"])[:3]:
        t = doc["teams"][abbr]
        print(f"  {abbr} {t['record'] or '-':<6} basis {t['basis_season']} "
              f"off {t['season']['off_epa_pp']:+.3f} def {t['season']['def_epa_pp']:+.3f}")


if __name__ == "__main__":
    main()
