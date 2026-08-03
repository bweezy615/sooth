"""EPL adapter, backed by football-data.co.uk.

Source: https://www.football-data.co.uk/mmz4281/{season}/E0.csv
Free, no auth, one ~200KB file per season.

WHY THIS SPORT IS ON BETTER FOOTING THAN NFL
--------------------------------------------
This is the only source in the project whose closing odds are *documented as
closing odds* by the publisher. The `C`-infixed columns (PSCH/PSCD/PSCA =
Pinnacle Closing Home/Draw/Away) are stated to be the closing price, and
coverage is complete: 380/380 fixtures in 2024-25.

Compare NFL, where nflverse's ``spread_line`` is an undocumented periodic
snapshot we measured to disagree with a real consensus close on 32.9% of
games. EPL therefore needs no paid backfill to be gradeable.

THE THREE-WAY PROBLEM
---------------------
Football has draws, so the market is 1X2 rather than two-sided. The unified
schema was designed around ``side_a``/``side_b``, and rather than pretend a
draw is a kind of win, this adapter emits an explicit ``draw`` selection. That
is a genuine schema extension, recorded rather than hidden: any downstream
code that assumes exactly two outcomes will be wrong for this sport, and
should fail loudly rather than silently renormalise.

STATUS: In calibration. Not Live. No published claim rests on it yet.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from ..schema import Event, Line, Market, Result, Sport, Status
from .base import SportAdapter

URL = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"

# Columns documented by the publisher as CLOSING prices (the C infix).
CLOSING_COLS = {"home": "PSCH", "draw": "PSCD", "away": "PSCA"}
# Market-average closing, used when Pinnacle is missing for a fixture.
AVG_CLOSING_COLS = {"home": "AvgCH", "draw": "AvgCD", "away": "AvgCA"}


def season_code(start_year: int) -> str:
    """2024 -> '2425', matching the publisher's file naming."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def decimal_to_american(dec: float) -> int:
    """Football-data publishes decimal odds; the rest of the engine is American."""
    if dec <= 1.0:
        raise ValueError(f"invalid decimal odds: {dec}")
    return int(round((dec - 1) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1)))


class EPLAdapter(SportAdapter):
    sport = Sport.EPL

    def __init__(self, cache_dir: Path | str = "data/raw/epl"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._frames: dict[int, pd.DataFrame] = {}

    # -- ingest ---------------------------------------------------------------

    def fetch_season(self, start_year: int, force: bool = False) -> pd.DataFrame:
        path = self.cache_dir / f"E0_{start_year}.csv"
        if force or not path.exists():
            resp = requests.get(URL.format(code=season_code(start_year)), timeout=60)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        df = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")
        df["season"] = start_year
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        return df.dropna(subset=["Date", "HomeTeam", "AwayTeam"])

    def load_seasons(self, start: int, end: int) -> pd.DataFrame:
        frames = []
        for y in range(start, end + 1):
            try:
                frames.append(self.fetch_season(y))
            except requests.HTTPError:
                continue  # season not published
        if not frames:
            raise RuntimeError("no EPL seasons available")
        return pd.concat(frames, ignore_index=True).sort_values("Date")

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _event_id(row) -> str:
        d = row["Date"]
        return f"{d:%Y%m%d}_{row['HomeTeam']}_{row['AwayTeam']}".replace(" ", "")

    def _to_event(self, row) -> Event:
        played = pd.notna(row.get("FTHG")) and pd.notna(row.get("FTAG"))
        return Event(
            event_id=self._event_id(row),
            sport=Sport.EPL,
            season=int(row["season"]),
            stage="regular",
            start_time=row["Date"].to_pydatetime().replace(tzinfo=timezone.utc),
            side_a=str(row["HomeTeam"]),
            side_b=str(row["AwayTeam"]),
            status=Status.FINAL if played else Status.SCHEDULED,
            meta={"referee": row.get("Referee")},
        )

    # -- SportAdapter ---------------------------------------------------------

    def load_history(self, start_season: int, end_season: int) -> list[Event]:
        df = self.load_seasons(start_season, end_season)
        df = df[df["FTHG"].notna() & df["FTAG"].notna()]
        return [self._to_event(r) for _, r in df.iterrows()]

    def load_results(self, events: list[Event]) -> dict[str, Result]:
        wanted = {e.event_id for e in events}
        if not events:
            return {}
        df = self.load_seasons(min(e.season for e in events),
                               max(e.season for e in events))
        out: dict[str, Result] = {}
        for _, r in df.iterrows():
            eid = self._event_id(r)
            if eid not in wanted or pd.isna(r.get("FTHG")):
                continue
            out[eid] = Result(
                event_id=eid, score_a=float(r["FTHG"]), score_b=float(r["FTAG"]),
                settled_at=r["Date"].to_pydatetime().replace(tzinfo=timezone.utc))
        return out

    def load_historical_lines(self, events: list[Event]) -> list[Line]:
        """1X2 closing prices.

        ``is_closing=True`` here is a claim we can actually defend: the
        publisher documents these columns as closing prices. That is not true
        of any NFL source we have without paying for it.
        """
        wanted = {e.event_id for e in events}
        if not events:
            return []
        df = self.load_seasons(min(e.season for e in events),
                               max(e.season for e in events))
        lines: list[Line] = []
        for _, r in df.iterrows():
            eid = self._event_id(r)
            if eid not in wanted:
                continue
            when = r["Date"].to_pydatetime().replace(tzinfo=timezone.utc)
            for sel, prim in (("side_a", "home"), ("draw", "draw"),
                              ("side_b", "away")):
                dec = r.get(CLOSING_COLS[prim])
                book = "pinnacle_close"
                if pd.isna(dec):
                    dec = r.get(AVG_CLOSING_COLS[prim])
                    book = "market_avg_close"
                if pd.isna(dec) or float(dec) <= 1.0:
                    continue
                lines.append(Line(
                    event_id=eid, market=Market.MONEYLINE, selection=sel,
                    line=None, price=decimal_to_american(float(dec)),
                    book=book, captured_at=when, is_closing=True))
        return lines

    def upcoming(self, now: datetime) -> list[Event]:
        try:
            df = self.fetch_season(now.year if now.month >= 7 else now.year - 1,
                                   force=True)
        except requests.HTTPError:
            return []
        df = df[df["FTHG"].isna()]
        return sorted((self._to_event(r) for _, r in df.iterrows()),
                      key=lambda e: e.start_time)

    def current_lines(self, events: list[Event]) -> list[Line]:
        # football-data publishes post-match; live prices need another source.
        return []

    def feature_frame(self, events: list[Event], asof: datetime) -> pd.DataFrame:
        """Pre-match features only.

        Deliberately thin: fixture identity and rest. Form and expected-goals
        ratings are built walk-forward by the model, exactly as NFL's EPA
        ratings are, rather than being smuggled in here where the leakage
        boundary is enforced.
        """
        rows = [{
            "event_id": e.event_id, "season": e.season,
            "home": e.side_a, "away": e.side_b,
            "kickoff": e.start_time,
            "neutral_site": int(e.neutral_site),
        } for e in events if e.start_time <= asof or e.status != Status.FINAL]
        return pd.DataFrame(rows)
