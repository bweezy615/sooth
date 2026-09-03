"""College football adapter, backed by the cfbfastR data mirror.

Source: https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/
        schedules/csv/cfb_schedules_{season}.csv
Free, no auth, no API key, one file per season, 2016-present verified reachable.

Two properties of this source are worth stating because they are better than
the NFL feed's, and the code depends on both:

``start_date`` is an explicit UTC instant ("2025-08-23T16:00:00.000Z"). It is
NOT a local wall clock that has to be converted, which is the bug that put
every NFL kickoff four hours early (see PLAN.md). Parsing it as anything other
than UTC would reintroduce that class of error, so it is parsed as UTC and
asserted to be tz-aware.

``game_id`` is ESPN's numeric event id — the SAME id space our own odds
capture writes into data/capture/ncaaf/. HANDOFF §4.3 warns that three ID
spaces exist for the NFL and none agree; for college football the schedule and
the capture already speak the same one, so a future closing-line join needs no
team-name bridge.

TEAM NAMES DO NOT MATCH THE ODDS BOARD, and anything joining the two on name
will silently match nothing. This source names schools; the Odds API feed
behind board.json names school plus mascot, and the two disagree on accents as
well:

    this adapter          board.json
    Akron                 Akron Zips
    Massachusetts         UMass Minutemen
    San José State        San Jose State Spartans

Join on ``game_id`` where the other side carries an ESPN id (our own capture
does). A name bridge is only needed against the Odds API's own event ids,
which are hashes of its own, and it must be built and tested deliberately —
this is the mistake HANDOFF §4.3 says already bit the NFL once.

LEAKAGE NOTES (read before adding any feature)
----------------------------------------------
These columns describe the outcome or were recorded after kickoff and are
banned from ``feature_frame``:

  home_points, away_points          the result itself
  home_postgame_elo, away_postgame_elo
  home_post_win_prob, away_post_win_prob
  excitement_index                  computed from the played game
  attendance                        counted on the day
  highlights                        exists only once the game is played

``home_pregame_elo`` / ``away_pregame_elo`` ARE legitimate: the source states
them as of before kickoff. They are the only rating in this adapter, which
matters — they come from the data provider, not from us, so a model leaning on
them is not independent of the provider's opinion. That is a modelling
decision for whoever wires this into the ensemble, and it is why they are
passed through as plain features rather than folded into anything here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from ..schema import Event, Line, Result, Sport, Status
from .base import SportAdapter

SCHEDULE_URL = (
    "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/"
    "schedules/csv/cfb_schedules_{season}.csv"
)

BANNED_FEATURES = frozenset(
    {
        "home_points",
        "away_points",
        "home_postgame_elo",
        "away_postgame_elo",
        "home_post_win_prob",
        "away_post_win_prob",
        "excitement_index",
        "attendance",
        "highlights",
    }
)

# Only games between two FBS teams are modelled. College football's schedule
# is not a connected graph: FBS teams open against FCS opponents that play one
# game against the division all year, and the rest of their season is against
# teams this adapter never loads. An opponent-adjusted rating for such a team
# is not a weak estimate, it is an estimate of nothing — and the board's
# opening weekend is exactly where those games cluster, so a model that
# happily printed 92% on Bethune-Cookman at UCF would be showing its most
# confident numbers precisely where it knows least.
#
# They are therefore not predicted at all rather than predicted badly. The
# odds board still carries them: shopping a price needs no model, which is the
# whole argument of engine/lines.py.
FBS = "fbs"


class NCAAFAdapter(SportAdapter):
    sport = Sport.NCAAF

    def __init__(self, cache_dir: Path | str = "data/raw"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._seasons: dict[int, pd.DataFrame] = {}

    # -- ingest ----------------------------------------------------------------

    def fetch_season(self, season: int, force: bool = False) -> pd.DataFrame:
        """Download (or reuse) one season's schedule."""
        if not force and season in self._seasons:
            return self._seasons[season]
        path = self.cache_dir / f"ncaaf_schedule_{season}.csv"
        if force or not path.exists():
            resp = requests.get(SCHEDULE_URL.format(season=season), timeout=90)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        df = pd.read_csv(path, low_memory=False)
        df["start_time"] = pd.to_datetime(
            df["start_date"], format="ISO8601", utc=True, errors="coerce")
        self._seasons[season] = df
        return df

    def seasons(self, start_season: int, end_season: int) -> pd.DataFrame:
        frames = [self.fetch_season(s) for s in range(start_season, end_season + 1)]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _kickoff(row) -> datetime:
        """UTC kickoff, straight from the source's own UTC instant."""
        t = row["start_time"]
        if pd.isna(t):
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        t = t.to_pydatetime()
        # The source is explicitly Z-suffixed, so a naive value here means the
        # format changed underneath us. Fail loudly rather than guess a zone.
        assert t.tzinfo is not None, f"non-UTC kickoff in source: {row['start_date']}"
        return t.astimezone(timezone.utc)

    @staticmethod
    def _is_final(row) -> bool:
        return bool(row.get("completed")) and pd.notna(row.get("home_points")) \
            and pd.notna(row.get("away_points"))

    @staticmethod
    def _both_fbs(row) -> bool:
        return str(row.get("home_division")) == FBS \
            and str(row.get("away_division")) == FBS

    def _to_event(self, row) -> Event:
        return Event(
            event_id=str(row["game_id"]),
            sport=Sport.NCAAF,
            season=int(row["season"]),
            stage=str(row["week"]),
            start_time=self._kickoff(row),
            side_a=str(row["home_team"]),
            side_b=str(row["away_team"]),
            neutral_site=bool(row.get("neutral_site")),
            status=Status.FINAL if self._is_final(row) else Status.SCHEDULED,
            venue=(None if pd.isna(row.get("venue")) else str(row.get("venue"))),
            meta={
                "season_type": row.get("season_type"),
                "conference_game": row.get("conference_game"),
                "home_conference": row.get("home_conference"),
                "away_conference": row.get("away_conference"),
                "home_pregame_elo": row.get("home_pregame_elo"),
                "away_pregame_elo": row.get("away_pregame_elo"),
            },
        )

    # -- SportAdapter ----------------------------------------------------------

    def load_history(self, start_season: int, end_season: int) -> list[Event]:
        df = self.seasons(start_season, end_season)
        if df.empty:
            return []
        sub = df[df.apply(self._both_fbs, axis=1) & df.apply(self._is_final, axis=1)]
        sub = sub.sort_values(["season", "week", "start_time"])
        return [self._to_event(r) for _, r in sub.iterrows()]

    def load_results(self, events: list[Event]) -> dict[str, Result]:
        wanted = {e.event_id for e in events}
        seasons = {e.season for e in events}
        if not seasons:
            return {}
        df = self.seasons(min(seasons), max(seasons))
        sub = df[df["game_id"].astype(str).isin(wanted)]
        out: dict[str, Result] = {}
        for _, r in sub.iterrows():
            if not self._is_final(r):
                continue
            out[str(r["game_id"])] = Result(
                event_id=str(r["game_id"]),
                score_a=float(r["home_points"]),
                score_b=float(r["away_points"]),
                settled_at=self._kickoff(r),
            )
        return out

    def load_historical_lines(self, events: list[Event]) -> list[Line]:
        """No market quotes: this source carries none.

        Returning nothing is the honest answer and it has a consequence the
        caller must respect. HANDOFF §9 ships a sport as Live only where we
        hold free, verifiable closing-line history to grade against, so
        college football is In calibration until a closing-line source is
        wired up — our own data/capture/ncaaf/ is the candidate, and it joins
        on this adapter's event_id without a team-name bridge because both
        speak ESPN's ids.

        The alternative — inventing an is_closing=True line from a schedule
        feed that never claimed to hold one — is precisely what base.py warns
        silently corrupts every CLV number downstream.
        """
        return []

    def upcoming(self, now: datetime) -> list[Event]:
        now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        df = self.seasons(now.year, now.year)
        if df.empty:
            return []
        sub = df[df.apply(self._both_fbs, axis=1) & ~df.apply(self._is_final, axis=1)]
        events = [self._to_event(r) for _, r in sub.iterrows()]
        return sorted((e for e in events if e.start_time >= now),
                      key=lambda e: e.start_time)

    def current_lines(self, events: list[Event]) -> list[Line]:
        """Same source, same absence. See load_historical_lines."""
        return []

    def feature_frame(self, events: list[Event], asof: datetime):
        """Pre-game-only features.

        Rest days are computed from each team's previous kickoff, counting
        ONLY games that started before ``asof``. A team's rest is otherwise
        trivially derivable from a game that has not happened yet, which is
        the leak this argument exists to prevent.
        """
        asof = asof if asof.tzinfo else asof.replace(tzinfo=timezone.utc)

        # last kickoff per team, strictly before asof and before this game
        seen: list[tuple[datetime, str]] = []
        for e in events:
            if e.start_time < asof:
                seen.append((e.start_time, e.side_a))
                seen.append((e.start_time, e.side_b))
        seen.sort()

        def rest(team: str, kickoff: datetime) -> float | None:
            prior = [t for t, who in seen if who == team and t < kickoff]
            return (kickoff - prior[-1]).total_seconds() / 86400.0 if prior else None

        rows = []
        for e in events:
            m = e.meta
            hr, ar = rest(e.side_a, e.start_time), rest(e.side_b, e.start_time)
            rows.append({
                "event_id": e.event_id,
                "season": e.season,
                "week": pd.to_numeric(e.stage, errors="coerce"),
                "home": e.side_a,
                "away": e.side_b,
                "neutral_site": int(e.neutral_site),
                "conference_game": int(bool(m.get("conference_game"))),
                "home_rest": hr,
                "away_rest": ar,
                "rest_diff": (None if hr is None or ar is None else hr - ar),
                "home_pregame_elo": pd.to_numeric(
                    m.get("home_pregame_elo"), errors="coerce"),
                "away_pregame_elo": pd.to_numeric(
                    m.get("away_pregame_elo"), errors="coerce"),
                "is_postseason": int(str(m.get("season_type")) != "regular"),
            })
        df = pd.DataFrame(rows)
        leaked = BANNED_FEATURES & set(df.columns)
        if leaked:  # defensive: fail loudly rather than ship a fake backtest
            raise AssertionError(f"leaked post-game columns into features: {leaked}")
        return df
