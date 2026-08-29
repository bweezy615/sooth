"""College football adapter, backed by cfbfastR-data public releases.

Source: https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/
        schedules/csv/cfb_schedules_{season}.csv
Free, no auth, one file per season, 2002-2025 verified present on 2026-08-29.

``docs/plans/college-football.md`` Phase 3 named ``cfbfastR-data`` and the
CollegeFootballData API as the two candidates. cfbfastR-data is chosen because
it needs no API key, which keeps the backtest reproducible by a reader who has
nothing but this repo — the same property nflverse gives ``adapters/nfl.py``.

WHAT THIS SOURCE DOES NOT HAVE, AND WHY IT DECIDES EVERYTHING
------------------------------------------------------------
**There are no betting lines in it at all.** No spread, no total, no
moneyline, opening or closing. Verified column-by-column against the 2024
file: 31 columns, none of them a market quote.

Three consequences, none of them optional:

1. ``load_historical_lines`` returns an empty list. It does not fabricate a
   number, and it does not borrow one from a live feed and backdate it. A
   sport with no line archive has no line archive.
2. No closing-line value, and no against-the-spread record, can be computed
   for college football from this source. ``EDGE_THRESHOLD`` in
   ``models/ensemble.py`` is an NFL measurement made against nflverse spreads;
   there is nothing here to measure a college equivalent against, and
   inheriting the NFL number would be exactly the fabrication the plan warns
   about.
3. College football is therefore **in calibration** in the sense
   /disclaimers §7 already promises, and cannot become "live" on this data.
   The README's rule — a sport is Live only with free, verifiable
   closing-line history to grade against — resolves to "not Live" here, by
   the data rather than by choice.

Our own capture (``data/capture/ncaaf/*.jsonl``, running since 2026-08-28) is
the series that will eventually grade college football. It is two days old, so
it grades nothing yet. ``current_lines`` reads it; ``load_historical_lines``
deliberately does not, because a two-day archive is not history and quietly
returning it would let a backtest appear to have market data.

LEAKAGE NOTES (read before adding any feature)
----------------------------------------------
These columns are NOT knowable before kickoff and are banned from
``feature_frame``:

  home_points, away_points        the outcome itself
  home_post_win_prob,             computed from the game that was played
  away_post_win_prob
  home_postgame_elo,              the rating AFTER the result is folded in
  away_postgame_elo
  excitement_index                a function of the in-game win-probability path
  attendance                      counted at the game, not before it
  highlights                      a post-game video link

``home_pregame_elo`` / ``away_pregame_elo`` are a harder case and are
**deliberately excluded** rather than banned. The name says pre-game and the
value plausibly is, but it is a third party's rating published in a file that
is rebuilt historically, and we cannot demonstrate from the file that any given
row was computed from strictly prior games. ``base.py`` requires that every
feature column be justifiable as knowable at ``asof``; "probably, judging by
the column name" does not meet that bar, and a rating with future information
folded in is precisely the defect that produces a beautiful backtest and a
losing model. Both columns are carried in ``Event.meta`` so a later session can
audit them, and neither reaches the feature frame. Our own Elo
(``models/elo.py``) is built walk-forward from results and has no such
ambiguity.

Legitimately pre-game and used as features:
  season, week, neutral_site, conference_game, division matchup, and rest
  days, which are derived here from each team's own previous kickoff date.

SCOPE AND THE FCS PROBLEM
-------------------------
The season files carry every division: the 2024 file is 3,801 rows, of which
920 have an FBS home side. D-II and D-III games are dropped. Games where an FBS
team plays an FCS team are KEPT, because they are real FBS results that move a
real FBS rating and dropping them would silently delete a chunk of most teams'
Septembers — but the FCS side is pooled into one synthetic opponent per
division rather than given a per-team rating. There are hundreds of FCS
programs that appear once or twice a decade against FBS opposition; rating them
individually produces ratings built on one game.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from ..schema import Event, Line, Market, Result, Sport, Status
from .base import SportAdapter

SCHEDULE_URL = (
    "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/"
    "schedules/csv/cfb_schedules_{season}.csv"
)

# Verified present on 2026-08-29 by HEAD request. 2026 does not exist yet; the
# fetch tolerates a missing tail season rather than failing the whole range,
# because the current season's file appears only once it has games in it.
FIRST_SEASON = 2002
LAST_VERIFIED_SEASON = 2025

# Columns that describe the outcome or were measured at/after kickoff.
BANNED_FEATURES = frozenset(
    {
        "home_points",
        "away_points",
        "home_post_win_prob",
        "away_post_win_prob",
        "home_postgame_elo",
        "away_postgame_elo",
        "excitement_index",
        "attendance",
        "highlights",
    }
)

# Excluded from features for a different reason than the set above - see the
# module docstring. Present in meta, never in the feature frame.
UNVERIFIABLE_PREGAME = frozenset({"home_pregame_elo", "away_pregame_elo"})

# One pooled opponent per non-FBS division, so a team that plays an FCS side
# updates against a stable bucket instead of a program with one rated game.
POOLED = {"fcs": "__FCS__", "ii": "__DII__", "iii": "__DIII__"}


def pooled_name(team: str, division: str | None) -> str:
    """The rating key for one side: itself if FBS, otherwise its division pool."""
    d = str(division).strip().lower()
    return POOLED.get(d, team)


class NCAAFAdapter(SportAdapter):
    sport = Sport.NCAAF

    def __init__(self, cache_dir: Path | str = "data/raw",
                 capture_dir: Path | str = "data/capture/ncaaf"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.capture_dir = Path(capture_dir)
        self._games: pd.DataFrame | None = None

    # -- ingest ----------------------------------------------------------------

    def fetch(self, start_season: int = FIRST_SEASON,
              end_season: int = LAST_VERIFIED_SEASON,
              force: bool = False) -> pd.DataFrame:
        """Download (or reuse) one CSV per season and concatenate.

        A season whose file 404s is skipped with no error: the in-progress
        season has no file until it has games. A season that fails for any
        other reason is raised, because silently returning a short frame is
        how a backtest ends up quietly missing three years.
        """
        frames = []
        for season in range(start_season, end_season + 1):
            path = self.cache_dir / f"cfb_schedules_{season}.csv"
            if force or not path.exists():
                resp = requests.get(SCHEDULE_URL.format(season=season), timeout=60)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                path.write_bytes(resp.content)
            frames.append(pd.read_csv(path, low_memory=False))
        if not frames:
            raise RuntimeError(
                f"no cfbfastR schedule files for {start_season}-{end_season}")
        df = pd.concat(frames, ignore_index=True)
        self._games = self._prepare(df)
        return self._games

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        """Normalise types, restrict to FBS, and derive rest days."""
        df = df.copy()
        df["start_date"] = pd.to_datetime(df["start_date"], utc=True,
                                          errors="coerce", format="ISO8601")
        for c in ("neutral_site", "conference_game", "completed"):
            df[c] = df[c].astype(str).str.upper().eq("TRUE")
        for c in ("home_division", "away_division"):
            df[c] = df[c].astype(str).str.strip().str.lower()

        # At least one FBS side. Keeps FBS-vs-FCS, drops DII/DIII fixtures.
        df = df[(df["home_division"] == "fbs") | (df["away_division"] == "fbs")]

        df["home_key"] = [pooled_name(t, d) for t, d
                          in zip(df["home_team"], df["home_division"])]
        df["away_key"] = [pooled_name(t, d) for t, d
                          in zip(df["away_team"], df["away_division"])]

        df = df.sort_values(["season", "week", "start_date"]).reset_index(drop=True)
        return NCAAFAdapter._attach_rest(df)

    @staticmethod
    def _attach_rest(df: pd.DataFrame) -> pd.DataFrame:
        """Days since each side's previous game, within the same season.

        Derived from kickoff dates alone, which are published when the schedule
        is. The first game of a team's season has no previous game and gets NaN
        rather than an invented number; pooled opponents get NaN too, since
        "the FCS" does not have a rest day.

        The pass runs in KICKOFF order, not the frame's (season, week, date)
        order, and that distinction is not cosmetic. College week numbers are
        not chronological — a game labelled week 2 can be played before one
        labelled week 1, which is routine around the season opener. Walking the
        frame in week order therefore recorded some teams' "previous" game as
        one that had not been played yet and produced 157 negative rest values
        across 2002-2025. Sorting by date removes them by construction; the
        assertion below keeps it that way.
        """
        order = df["start_date"].argsort(kind="stable")
        last: dict[tuple[int, str], pd.Timestamp] = {}
        home_rest_by_pos: dict[int, float] = {}
        away_rest_by_pos: dict[int, float] = {}
        for pos in order:
            r = df.iloc[pos]
            out = []
            for team, division in ((r.home_team, r.home_division),
                                   (r.away_team, r.away_division)):
                if str(division).strip().lower() != "fbs":
                    out.append(float("nan"))
                    continue
                prev = last.get((int(r.season), team))
                out.append(float("nan") if prev is None or pd.isna(r.start_date)
                           else (r.start_date - prev).total_seconds() / 86400.0)
            home_rest_by_pos[pos] = out[0]
            away_rest_by_pos[pos] = out[1]
            for team, division in ((r.home_team, r.home_division),
                                   (r.away_team, r.away_division)):
                if str(division).strip().lower() == "fbs" and not pd.isna(r.start_date):
                    last[(int(r.season), team)] = r.start_date
        df = df.copy()
        df["home_rest"] = [home_rest_by_pos[i] for i in range(len(df))]
        df["away_rest"] = [away_rest_by_pos[i] for i in range(len(df))]
        for col in ("home_rest", "away_rest"):
            bad = pd.to_numeric(df[col], errors="coerce")
            assert not (bad < 0).any(), (
                f"{col} went negative: the rest pass is out of kickoff order")
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
        d = row["start_date"]
        if pd.isna(d):
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        return d.to_pydatetime().astimezone(timezone.utc)

    @staticmethod
    def _is_final(row) -> bool:
        return pd.notna(row.get("home_points")) and pd.notna(row.get("away_points"))

    def _to_event(self, row) -> Event:
        return Event(
            event_id=str(row["game_id"]),
            sport=Sport.NCAAF,
            season=int(row["season"]),
            stage=str(row["week"]),
            start_time=self._kickoff(row),
            side_a=str(row["home_team"]),
            side_b=str(row["away_team"]),
            neutral_site=bool(row.get("neutral_site", False)),
            status=Status.FINAL if self._is_final(row) else Status.SCHEDULED,
            venue=(None if pd.isna(row.get("venue")) else str(row.get("venue"))),
            meta={
                "season_type": row.get("season_type"),
                "conference_game": bool(row.get("conference_game", False)),
                "home_conference": row.get("home_conference"),
                "away_conference": row.get("away_conference"),
                "home_division": row.get("home_division"),
                "away_division": row.get("away_division"),
                "home_key": row.get("home_key"),
                "away_key": row.get("away_key"),
                "home_rest": row.get("home_rest"),
                "away_rest": row.get("away_rest"),
                # Carried for audit, deliberately NOT features. See docstring.
                "home_pregame_elo": row.get("home_pregame_elo"),
                "away_pregame_elo": row.get("away_pregame_elo"),
            },
        )

    # -- SportAdapter ----------------------------------------------------------

    def load_history(self, start_season: int, end_season: int) -> list[Event]:
        df = self.games
        mask = (
            df["season"].between(start_season, end_season)
            & df["home_points"].notna()
            & df["away_points"].notna()
        )
        sub = df.loc[mask]
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
                score_a=float(r["home_points"]),
                score_b=float(r["away_points"]),
                settled_at=self._kickoff(r),
            )
        return out

    def load_historical_lines(self, events: list[Event]) -> list[Line]:
        """Empty, and that is the honest answer for this source.

        cfbfastR-data schedules carry no market quotes of any kind. Returning
        [] means every downstream closing-line-value and against-the-spread
        computation for college football correctly finds nothing to grade,
        instead of grading against a number we invented or backdated.

        Our own capture is NOT returned here. It began 2026-08-28 and is a live
        series, not an archive; surfacing it through the historical path would
        let a backtest over 2002-2025 appear to have market data for two days
        in 2026 and none of it labelled. ``current_lines`` is where it belongs.
        """
        return []

    def upcoming(self, now: datetime) -> list[Event]:
        df = self.games
        sub = df[df["home_points"].isna() & df["away_points"].isna()]
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        events = [self._to_event(r) for _, r in sub.iterrows()]
        return sorted((e for e in events if e.start_time >= now),
                      key=lambda e: e.start_time)

    def current_lines(self, events: list[Event]) -> list[Line]:
        """Our own captured moneylines for these events, if we have any.

        Reads ``data/capture/ncaaf/*.jsonl`` — the append-only series written
        by ``engine/capture.py``. Two properties are load-bearing:

        ``is_closing`` is always False. The capture is a poll, and a poll is
        not a close; ``engine/capture.py`` makes the same point at length about
        why nobody else's "closing line" label is trusted either.

        Rows join to events by normalised team name, because the capture keys
        events by a hash of its own and carries ESPN's full team names
        ("North Dakota State Bison") while cfbfastR carries the short form
        ("North Dakota State"). Equality alone therefore matches nothing at
        all — the first cut of this method used it and silently returned an
        empty list for every game, which is indistinguishable from "no prices
        captured yet". The schedule name is instead required to be a PREFIX of
        the captured name, on BOTH sides of the same event at once.

        A bare prefix rule is not enough, and the reason was measured rather
        than guessed: of 108 real captured pairings checked against the 230
        team names in the 2025 schedule, **18 captured home names prefix more
        than one team**, and the collision is systematic rather than
        occasional — "Ohio State Buckeyes" prefixes both `Ohio` and
        `Ohio State`, and the same holds for Michigan, Florida, Georgia,
        Iowa, Kansas, Colorado, Arizona and New Mexico.

        That is a wrong-match risk, not just an ambiguous one: in a week where
        `Ohio` plays and `Ohio State` does not, a captured Ohio State row
        prefix-matches `Ohio` uniquely and would be filed against the wrong
        game with nothing reporting it. So the remainder after the prefix must
        look like a mascot: if it begins with a school qualifier
        (``QUALIFIERS``) the match is rejected. Ties on specificity are
        dropped, and both sides must resolve to the same event. A moneyline
        filed against the wrong game is worse than a moneyline we do not have.
        """
        if not self.capture_dir.exists():
            return []
        keyed = [(_norm(e.side_a), _norm(e.side_b), e) for e in events]

        lines: list[Line] = []
        seen: set[tuple] = set()
        for path in sorted(self.capture_dir.glob("*.jsonl")):
            for raw in path.read_text().splitlines():
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                if row.get("provenance") != "own_capture":
                    continue
                if row.get("market") != "moneyline":
                    continue
                home, away = _norm(row.get("home", "")), _norm(row.get("away", ""))
                event = _resolve(keyed, home, away)
                if event is None:
                    continue
                # Sided against the CAPTURE row's own names, not the event's:
                # the two sources spell teams differently and the row is
                # internally consistent.
                sel = _norm(row.get("selection", ""))
                if sel == home:
                    selection = "side_a"
                elif sel == away:
                    selection = "side_b"
                else:
                    continue
                price = row.get("price")
                if price is None:
                    continue
                key = (event.event_id, row.get("book"), selection,
                       row.get("observed_at"))
                if key in seen:
                    continue
                seen.add(key)
                lines.append(Line(
                    event_id=event.event_id,
                    market=Market.MONEYLINE,
                    selection=selection,
                    line=None,
                    price=int(price),
                    book=str(row.get("book", "unknown")),
                    captured_at=datetime.fromisoformat(row["observed_at"]),
                    is_closing=False,
                ))
        return lines

    def feature_frame(self, events: list[Event], asof: datetime) -> pd.DataFrame:
        """Pre-game-only features.

        Every column is knowable when the schedule is published, except the
        rest columns, which are knowable from earlier kickoff dates in the same
        season. Nothing here reads a score, a post-game rating, an attendance
        count, or a third-party Elo we cannot audit.
        """
        rows = []
        for e in events:
            m = e.meta
            hr = pd.to_numeric(m.get("home_rest"), errors="coerce")
            ar = pd.to_numeric(m.get("away_rest"), errors="coerce")
            rows.append(
                {
                    "event_id": e.event_id,
                    "season": e.season,
                    "week": pd.to_numeric(e.stage, errors="coerce"),
                    "home": e.side_a,
                    "away": e.side_b,
                    "neutral_site": int(e.neutral_site),
                    "home_rest": hr,
                    "away_rest": ar,
                    "rest_diff": hr - ar,
                    "conference_game": int(bool(m.get("conference_game"))),
                    # An FBS side hosting or visiting a lower division. Kept as
                    # a feature because it is the single largest talent gap in
                    # the sport and it is known the day the schedule drops.
                    "cross_division": int(
                        str(m.get("home_division")) != str(m.get("away_division"))),
                    "is_postseason": int(str(m.get("season_type")) != "regular"),
                }
            )
        df = pd.DataFrame(rows)
        leaked = (BANNED_FEATURES | UNVERIFIABLE_PREGAME) & set(df.columns)
        if leaked:  # defensive: fail loudly rather than ship a fake backtest
            raise AssertionError(f"leaked post-game columns into features: {leaked}")
        return df


def _norm(name: str) -> str:
    """Loose team-name key for joining capture rows to schedule rows.

    Lowercased alphanumerics only. Deliberately not a fuzzy matcher: no edit
    distance, no token soup. Either the schedule name prefixes the captured
    one or the row is dropped.
    """
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


# Words that begin a DIFFERENT school rather than a mascot. If stripping a
# schedule name off a captured name leaves one of these at the front, the
# prefix matched the wrong institution: "Ohio State Buckeyes" minus "ohio"
# leaves "statebuckeyes", and the row belongs to Ohio State, not Ohio.
QUALIFIERS = ("state", "tech", "southern", "northern", "eastern", "western",
              "central", "international", "atlantic", "christian", "am")


def _prefixes(schedule_name: str, captured_name: str) -> bool:
    """Does this schedule name open this captured name, as the same school?"""
    if not schedule_name or not captured_name.startswith(schedule_name):
        return False
    remainder = captured_name[len(schedule_name):]
    return not remainder.startswith(QUALIFIERS)


def _resolve(keyed: list[tuple[str, str, Event]], home: str,
             away: str) -> Event | None:
    """The one event this captured pairing names, or None.

    Exact matches win outright. Otherwise both sides must prefix-match the
    same event under ``_prefixes``, and the winner must be strictly more
    specific than any other candidate — a tie means two schools fit equally
    well and we say nothing.
    """
    if not home or not away:
        return None
    for a, b, event in keyed:
        if a == home and b == away:
            return event
    hits = [(len(a) + len(b), e) for a, b, e in keyed
            if _prefixes(a, home) and _prefixes(b, away)]
    if not hits:
        return None
    hits.sort(key=lambda t: -t[0])
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return None
    return hits[0][1]
