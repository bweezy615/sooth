"""MLB pitcher-strikeout prop capture — Subsystem 1 of the props engine.

Why this exists
---------------
The props engine forecasts a player outcome and takes a position against the
book's prop line. Before any model can be trusted, we must prove it beats the
closing prop line — and you cannot measure beat-close without weeks of
captured prop closes. So this runs from day one, before any model exists.

Same evidence discipline as ``engine/capture.py``: append-only JSONL, one file
per UTC day, committed to git so commit timestamps attest we held a given price
at a given time. Provenance is ``own_capture`` — we watched it, timestamped it.

Budget
------
The Odds API bills the per-event odds endpoint by (markets x regions). We fetch
one market (``pitcher_strikeouts``) in one region, so **1 credit per game**.
Listing events is free. A hard ``max_credits`` ceiling refuses to overspend the
free tier — the same non-negotiable rule as the historical backfill.

Closing means closing
---------------------
Like the backfill, a game is only fetched if its first pitch is inside a short
window after "now". A snapshot hours before a game says nothing about its close.
Run this cron in the pre-first-pitch window (games stagger, so it fetches only
the handful about to start) and the last row per game is that game's close.

    python -m engine.props_capture --max-credits 15
    python -m engine.props_capture --max-credits 15 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .schema import canonical_book

EVENTS = "https://api.the-odds-api.com/v4/sports/baseball_mlb/events"
ODDS = "https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{eid}/odds"
MARKET = "pitcher_strikeouts"
TIMEOUT = 20

# A game is "about to close" only if first pitch is within this window of now.
# Sized to equal the cron cadence (30 min): each staggered start is caught by
# ~one tick, so we spend ~1 credit per game — the whole free-tier budget math.
# Listing events is free, so idle ticks with no game in-window cost 0 credits.
# ponytail: 30/30 = ~1 catch/game. A game starting exactly on a tick can be
# caught twice (both bounds inclusive); append-only + last-before-pitch grading
# absorb the rare dup. Tighten to strict-less only if credits actually bite.
WINDOW = timedelta(minutes=30)


@dataclass
class PropObservation:
    """One pitcher-strikeout prop price, from one book, at one observed moment."""

    observed_at: str  # UTC, when WE saw it
    event_id: str
    sport: str
    commence_time: str
    home: str
    away: str
    player: str  # the pitcher the prop is on
    book: str
    market: str  # pitcher_strikeouts
    selection: str  # over | under
    line: float | None  # the strikeout number
    price: int | None  # American odds
    provenance: str  # own_capture

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


def load_key() -> str:
    # ponytail: inlined (not imported from backfill) so this module needs only
    # `requests` — backfill drags pandas, which the cron shouldn't install.
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ODDS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("ODDS_API_KEY not found in environment or .env")


def _rows_from_event(payload: dict, observed_at: str) -> list[PropObservation]:
    """Parse one /events/{id}/odds response into over/under rows per pitcher."""
    rows: list[PropObservation] = []
    home, away = payload.get("home_team", ""), payload.get("away_team", "")
    commence = payload.get("commence_time", "")
    event_id = str(payload.get("id", ""))
    for bk in payload.get("bookmakers", []):
        # Canonical, like every other capture path (lines, props, middles,
        # capture). The raw API key spells one operator several ways
        # (williamhill_us/caesars, barstool/espnbet), and schema.py spells out
        # the cost: "one operator counted as two books can manufacture a
        # consensus that does not exist" — which is exactly what a prop's
        # de-vigged fair line is built from.
        book = canonical_book(bk.get("key", "unknown"))
        for mk in bk.get("markets", []):
            if mk.get("key") != MARKET:
                continue
            for oc in mk.get("outcomes", []):
                sel = oc.get("name", "").lower()  # "Over" / "Under"
                if sel not in ("over", "under"):
                    continue
                rows.append(PropObservation(
                    observed_at=observed_at,
                    event_id=event_id,
                    sport="mlb",
                    commence_time=commence,
                    home=home, away=away,
                    player=oc.get("description", ""),  # props nest player here
                    book=book,
                    market=MARKET,
                    selection=sel,
                    line=oc.get("point"),
                    price=oc.get("price"),
                    provenance="own_capture",
                ))
    return rows


def _closing_events(events: list[dict], now: datetime) -> list[dict]:
    """Events whose first pitch is inside the pre-close window after now."""
    out = []
    for ev in events:
        try:
            commence = datetime.fromisoformat(
                ev["commence_time"].replace("Z", "+00:00")
            )
        except (KeyError, ValueError):
            continue
        if now <= commence <= now + WINDOW:
            out.append(ev)
    return out


def capture_props(
    now: datetime,
    max_credits: int,
    out_dir: Path | str = "data/capture",
    dry_run: bool = False,
) -> list[PropObservation]:
    """Capture closing pitcher-K prop lines for MLB games about to start.

    Refuses to exceed ``max_credits`` per-event calls (1 credit each). Listing
    events is free and always happens so a dry run can report the true plan.
    """
    key = load_key()
    session = requests.Session()
    observed_at = now.isoformat()

    resp = session.get(EVENTS, params={"apiKey": key}, timeout=TIMEOUT)
    resp.raise_for_status()
    events = _closing_events(resp.json(), now)

    if dry_run:
        planned = min(len(events), max_credits)
        print(f"planned games: {len(events)}  credits if run: {planned}")
        return []

    rows: list[PropObservation] = []
    spent = 0
    for ev in events:
        if spent >= max_credits:  # hard ceiling — never overspend the tier
            break
        try:
            r = session.get(
                ODDS.format(eid=ev["id"]),
                params={"apiKey": key, "regions": "us",
                        "markets": MARKET, "oddsFormat": "american"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
        except (requests.HTTPError, KeyError):
            continue
        spent += 1
        rows.extend(_rows_from_event(r.json(), observed_at))

    if rows:
        out = Path(out_dir) / "mlb-props"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{now:%Y-%m-%d}.jsonl"
        with path.open("a") as fh:  # append-only. We never rewrite history.
            for row in rows:
                fh.write(row.to_json() + "\n")

    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-credits", type=int, default=15,
                    help="hard ceiling on per-event Odds API calls (1 credit each)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = capture_props(datetime.now(timezone.utc), args.max_credits,
                         dry_run=args.dry_run)
    if args.dry_run:
        return
    books = sorted({r.book for r in rows})
    players = sorted({r.player for r in rows})
    print(f"observations : {len(rows)}")
    print(f"pitchers     : {len(players)}")
    print(f"books        : {', '.join(books) if books else 'none'}")
    for r in rows[:6]:
        print(f"  {r.player:22} {r.selection:5} {r.line} @ {r.price} [{r.book}]")


if __name__ == "__main__":
    main()
