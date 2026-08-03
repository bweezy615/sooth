"""NFL adapter, backed by nflverse public data releases.

Source: https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv
Free, no auth, CC-licensed, 1999-present, refreshed daily in season.

LEAKAGE NOTES (read before adding any feature)
----------------------------------------------
The following columns in games.csv are NOT knowable before kickoff and are
therefore banned from ``feature_frame``:

  temp, wind        - recorded at/after the game, not a forecast
  away_score, home_score, result, total, overtime  - the outcome itself

``spread_line`` / ``total_line`` / moneylines are overwritten in place as the
market moves. For a FINAL game the stored value is the last observed line and
is treated as closing. For a SCHEDULED game it is a current/lookahead quote
and is marked ``is_closing=False``. We never grade closing-line value against
a number we cannot prove was the close - validate against ESPN's explicit
open/close objects before publishing any CLV figure.

Legitimately pre-game columns used as features:
  away_rest, home_rest, div_game, roof, surface, location, week, gameday
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from ..schema import Event, Line, Market, Result, Sport, Status
from .base import SportAdapter

GAMES_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "schedules/games.csv"
)

# Columns that describe the outcome or were measured after it started.
BANNED_FEATURES = frozenset(
    {
        "temp",
        "wind",
        "away_score",
        "home_score",
        "result",
        "total",
        "overtime",
    }
)


class NFLAdapter(SportAdapter):
    sport = Sport.NFL

    def __init__(self, cache_dir: Path | str = "data/raw"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._games: pd.DataFrame | None = None

    # -- ingest ----------------------------------------------------------------

    def fetch(self, force: bool = False) -> pd.DataFrame:
        """Download (or reuse) the nflverse schedule+lines file."""
        path = self.cache_dir / "nfl_games.csv"
        if force or not path.exists():
            resp = requests.get(GAMES_URL, timeout=60)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        df = pd.read_csv(path, low_memory=False)
        df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce")
        self._games = df
        return df

    @property
    def games(self) -> pd.DataFrame:
        if self._games is None:
            self.fetch()
        assert self._games is not None
        return self._games

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _kickoff(row) -> datetime:
        """Best-effort UTC kickoff. gametime is local ET in the source."""
        day = row["gameday"]
        t = row.get("gametime")
        if pd.isna(day):
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        if isinstance(t, str) and ":" in t:
            hh, mm = t.split(":")[:2]
            # ET -> UTC, ignoring DST edge cases; refined by the live feed.
            return datetime(
                day.year, day.month, day.day, int(hh), int(mm), tzinfo=timezone.utc
            )
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)

    @staticmethod
    def _is_final(row) -> bool:
        return pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))

    def _to_event(self, row) -> Event:
        return Event(
            event_id=str(row["game_id"]),
            sport=Sport.NFL,
            season=int(row["season"]),
            stage=str(row["week"]),
            start_time=self._kickoff(row),
            side_a=str(row["home_team"]),
            side_b=str(row["away_team"]),
            neutral_site=str(row.get("location", "Home")) != "Home",
            status=Status.FINAL if self._is_final(row) else Status.SCHEDULED,
            venue=(None if pd.isna(row.get("stadium")) else str(row.get("stadium"))),
            meta={
                "game_type": row.get("game_type"),
                "roof": row.get("roof"),
                "surface": row.get("surface"),
                "div_game": row.get("div_game"),
                "home_rest": row.get("home_rest"),
                "away_rest": row.get("away_rest"),
                "home_qb": row.get("home_qb_name"),
                "away_qb": row.get("away_qb_name"),
            },
        )

    # -- SportAdapter ----------------------------------------------------------

    def load_history(self, start_season: int, end_season: int) -> list[Event]:
        df = self.games
        mask = (
            df["season"].between(start_season, end_season)
            & df["home_score"].notna()
            & df["away_score"].notna()
        )
        sub = df.loc[mask].sort_values(["season", "week", "gameday"])
        return [self._to_event(r) for _, r in sub.iterrows()]

    def load_results(self, events: list[Event]) -> dict[str, Result]:
        wanted = {e.event_id for e in events}
        df = self.games
        sub = df[df["game_id"].astype(str).isin(wanted)]
        out: dict[str, Result] = {}
        for _, r in sub.iterrows():
            if not self._is_final(r):
                continue
            out[str(r["game_id"])] = Result(
                event_id=str(r["game_id"]),
                score_a=float(r["home_score"]),
                score_b=float(r["away_score"]),
                settled_at=self._kickoff(r),
            )
        return out

    def load_historical_lines(self, events: list[Event]) -> list[Line]:
        wanted = {e.event_id for e in events}
        df = self.games
        sub = df[df["game_id"].astype(str).isin(wanted)]
        lines: list[Line] = []
        for _, r in sub.iterrows():
            eid = str(r["game_id"])
            ko = self._kickoff(r)
            final = self._is_final(r)
            # nflverse spread_line is stated from the HOME perspective:
            # positive == home favoured by that many points.
            if pd.notna(r.get("spread_line")):
                for sel, price_col, sign in (
                    ("side_a", "home_spread_odds", 1.0),
                    ("side_b", "away_spread_odds", -1.0),
                ):
                    price = r.get(price_col)
                    lines.append(
                        Line(
                            event_id=eid,
                            market=Market.SPREAD,
                            selection=sel,
                            line=sign * float(r["spread_line"]),
                            price=int(price) if pd.notna(price) else -110,
                            book="nflverse_consensus",
                            captured_at=ko,
                            is_closing=final,
                        )
                    )
            if pd.notna(r.get("home_moneyline")) and pd.notna(r.get("away_moneyline")):
                lines.append(
                    Line(eid, Market.MONEYLINE, "side_a", None,
                         int(r["home_moneyline"]), "nflverse_consensus", ko, final)
                )
                lines.append(
                    Line(eid, Market.MONEYLINE, "side_b", None,
                         int(r["away_moneyline"]), "nflverse_consensus", ko, final)
                )
            if pd.notna(r.get("total_line")):
                for sel, price_col in (("over", "over_odds"), ("under", "under_odds")):
                    price = r.get(price_col)
                    lines.append(
                        Line(eid, Market.TOTAL, sel, float(r["total_line"]),
                             int(price) if pd.notna(price) else -110,
                             "nflverse_consensus", ko, final)
                    )
        return lines

    def upcoming(self, now: datetime) -> list[Event]:
        df = self.games
        sub = df[df["home_score"].isna() & df["away_score"].isna()]
        events = [self._to_event(r) for _, r in sub.iterrows()]
        return sorted(
            (e for e in events if e.start_time >= now.replace(tzinfo=timezone.utc)),
            key=lambda e: e.start_time,
        )

    def current_lines(self, events: list[Event]) -> list[Line]:
        # Same source; is_closing is False because these are still moving.
        return [l for l in self.load_historical_lines(events) if not l.is_closing]

    def feature_frame(self, events: list[Event], asof: datetime) -> pd.DataFrame:
        """Pre-game-only features.

        Everything here is knowable the moment the schedule is published or
        the week begins. No score, no measured weather, no post-hoc line.
        """
        rows = []
        for e in events:
            m = e.meta
            rows.append(
                {
                    "event_id": e.event_id,
                    "season": e.season,
                    "week": pd.to_numeric(e.stage, errors="coerce"),
                    "home": e.side_a,
                    "away": e.side_b,
                    "neutral_site": int(e.neutral_site),
                    "home_rest": pd.to_numeric(m.get("home_rest"), errors="coerce"),
                    "away_rest": pd.to_numeric(m.get("away_rest"), errors="coerce"),
                    "rest_diff": (
                        pd.to_numeric(m.get("home_rest"), errors="coerce")
                        - pd.to_numeric(m.get("away_rest"), errors="coerce")
                    ),
                    "div_game": pd.to_numeric(m.get("div_game"), errors="coerce"),
                    "indoors": int(str(m.get("roof")) in {"dome", "closed"}),
                    "turf": int(str(m.get("surface")) not in {"grass", "nan", "None"}),
                    "is_playoff": int(str(m.get("game_type")) != "REG"),
                }
            )
        df = pd.DataFrame(rows)
        leaked = BANNED_FEATURES & set(df.columns)
        if leaked:  # defensive: fail loudly rather than ship a fake backtest
            raise AssertionError(f"leaked post-game columns into features: {leaked}")
        return df
