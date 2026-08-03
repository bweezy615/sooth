"""Historical closing-line backfill from The Odds API.

Why this exists
---------------
Our live capture (engine/capture.py) builds a closing-line series going
forward, but it cannot recover the past. This module buys that past once.

The Odds API bills 30 credits per historical snapshot and returns every game
priced at that instant across ~10 books. A snapshot taken minutes before a
kickoff window therefore yields genuine multi-book closing lines for every
game in that window - which is the grading basis nflverse cannot provide, its
``spread_line`` being an undocumented snapshot that disagrees with documented
closes on 27.8% of 2024 spreads.

Design constraints
------------------
1. **Hard credit ceiling.** Credits are finite and non-renewable within the
   billing month. Every run is capped and refuses to exceed it. A backfill
   that dies at 90% with no budget to finish is worse than one never started.
2. **Resumable.** Completed snapshots are recorded and skipped on re-run, so
   a network failure costs one call, not the whole job.
3. **Closing means closing.** A row is only written if the snapshot was taken
   within a short window BEFORE that specific game's commence_time. A
   snapshot taken at 17:00 says nothing about a game kicking off at 01:00 the
   next morning, even though the response contains it.

    python -m engine.backfill --seasons 2022-2025 --dry-run
    python -m engine.backfill --seasons 2022-2025 --max-calls 420
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .adapters.nfl import NFLAdapter

API = "https://api.the-odds-api.com/v4/historical/sports/americanfootball_nfl/odds"
CREDITS_PER_CALL = 30
ET = ZoneInfo("America/New_York")

# Snapshot this long before kickoff: late enough to be the closing number,
# early enough that the book has not pulled the line.
LEAD = timedelta(minutes=5)
# A returned game counts as "closing" only if it kicks off within this window
# after the snapshot.
WINDOW = timedelta(minutes=45)


@dataclass
class ClosingLine:
    event_id: str
    sport: str
    season: int
    week: int
    commence_time: str
    home: str
    away: str
    book: str
    market: str
    selection: str
    line: float | None
    price: int | None
    snapshot_at: str
    provenance: str = "oddsapi_historical_close"

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


def load_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ODDS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("ODDS_API_KEY not found in environment or .env")


def kickoff_slots(season: int) -> list[tuple[int, datetime]]:
    """Distinct (week, kickoff-UTC) pairs for a completed season.

    gameday + gametime in nflverse are US/Eastern. Converting properly matters:
    an hour of drift turns a closing line into a pre-game line, or misses the
    window entirely.
    """
    df = NFLAdapter().games
    sub = df[
        (df["season"] == season)
        & df["home_score"].notna()
        & df["gametime"].notna()
    ].copy()

    slots: set[tuple[int, datetime]] = set()
    for _, r in sub.iterrows():
        day = pd.to_datetime(r["gameday"], errors="coerce")
        t = str(r["gametime"])
        if pd.isna(day) or ":" not in t:
            continue
        hh, mm = t.split(":")[:2]
        try:
            local = datetime(day.year, day.month, day.day, int(hh), int(mm),
                             tzinfo=ET)
        except ValueError:
            continue
        slots.add((int(r["week"]), local.astimezone(timezone.utc)))
    return sorted(slots, key=lambda x: x[1])


def _rows_from_snapshot(payload: dict, snapshot: datetime, season: int,
                        week: int) -> list[ClosingLine]:
    rows: list[ClosingLine] = []
    for game in payload.get("data", []):
        try:
            commence = datetime.fromisoformat(
                game["commence_time"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            continue
        # Only games kicking off just after this snapshot get a closing row.
        if not (snapshot <= commence <= snapshot + WINDOW):
            continue
        home, away = game.get("home_team", ""), game.get("away_team", "")
        for bk in game.get("bookmakers", []):
            book = bk.get("key", "unknown")
            for mk in bk.get("markets", []):
                key = mk.get("key")
                market = {"h2h": "moneyline", "spreads": "spread",
                          "totals": "total"}.get(key)
                if not market:
                    continue
                for oc in mk.get("outcomes", []):
                    name = oc.get("name", "")
                    if market == "total":
                        selection = name.lower()
                    elif name == home:
                        selection = "side_a"
                    elif name == away:
                        selection = "side_b"
                    else:
                        continue
                    rows.append(ClosingLine(
                        event_id=str(game.get("id", "")),
                        sport="nfl", season=season, week=week,
                        commence_time=game["commence_time"],
                        home=home, away=away, book=book, market=market,
                        selection=selection,
                        line=oc.get("point"),
                        price=oc.get("price"),
                        snapshot_at=snapshot.isoformat(),
                    ))
    return rows


def backfill(seasons: list[int], max_calls: int, out_dir: Path | str,
             dry_run: bool = False) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    done_path = out / "_completed_snapshots.json"
    done: set[str] = set(json.loads(done_path.read_text())) if done_path.exists() else set()

    plan: list[tuple[int, int, datetime]] = []
    for season in seasons:
        for week, ko in kickoff_slots(season):
            snap = ko - LEAD
            if snap.isoformat() in done:
                continue
            plan.append((season, week, snap))

    stats = {"planned": len(plan), "calls": 0, "rows": 0, "credits": 0,
             "skipped_existing": len(done), "seasons": seasons}

    if dry_run:
        stats["estimated_credits"] = min(len(plan), max_calls) * CREDITS_PER_CALL
        return stats

    key = load_key()
    session = requests.Session()
    remaining_header = None

    for season, week, snap in plan:
        if stats["calls"] >= max_calls:
            stats["stopped"] = "max_calls reached"
            break
        try:
            resp = session.get(API, params={
                "apiKey": key, "regions": "us",
                "markets": "h2h,spreads,totals", "oddsFormat": "american",
                "date": snap.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, timeout=45)
        except requests.RequestException:
            continue

        stats["calls"] += 1
        stats["credits"] += CREDITS_PER_CALL
        remaining_header = resp.headers.get("x-requests-remaining", remaining_header)

        if resp.status_code != 200:
            stats.setdefault("errors", []).append(
                f"{snap.isoformat()} HTTP {resp.status_code}")
            if resp.status_code in (401, 429):
                stats["stopped"] = f"HTTP {resp.status_code} - halting"
                break
            continue

        rows = _rows_from_snapshot(resp.json(), snap, season, week)
        if rows:
            with (out / f"nfl_{season}.jsonl").open("a") as fh:
                for r in rows:
                    fh.write(r.to_json() + "\n")
        stats["rows"] += len(rows)
        done.add(snap.isoformat())
        done_path.write_text(json.dumps(sorted(done)))
        time.sleep(0.2)

    stats["credits_remaining_reported"] = remaining_header
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2022-2025")
    ap.add_argument("--max-calls", type=int, default=420)
    ap.add_argument("--out", default="data/backfill")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if "-" in args.seasons:
        a, b = args.seasons.split("-")
        seasons = list(range(int(a), int(b) + 1))
    else:
        seasons = [int(s) for s in args.seasons.split(",")]

    stats = backfill(seasons, args.max_calls, args.out, args.dry_run)
    for k, v in stats.items():
        print(f"{k:28}: {v}")


if __name__ == "__main__":
    main()
