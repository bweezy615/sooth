"""Odds capture — the most time-sensitive component in the system.

Why this exists
---------------
ESPN publishes an ``open`` and a ``current`` odds block for games that have not
started. Once a game is finished, the odds block is gone. There is no archive
and no backfill. That means **a closing line we did not capture is a closing
line we can never obtain.** Every hour this cron is not running is evidence
permanently lost.

Adversarial verification of nine sports produced one dominant finding: almost
no freely available "closing line" is a documented close. nflverse's
``spread_line`` is an undocumented periodic snapshot that disagrees with the
only self-documenting NFL source on 27.8% of 2024 spreads. ESPN's ``close``
object, when it appears, is simply the last poll it happened to take.

So we stop trusting other people's labels and build our own series:

    The archive is for backtesting. Our own capture is for grading.

``provenance`` is therefore a first-class field on every row, never a comment.
A public closing-line-value claim may only be computed from rows whose
provenance we control. Everything else grades on results and says so.

Storage is append-only JSONL, one file per UTC day. We never rewrite a row.
The files are committed to git, so GitHub's commit timestamps become a
third-party attestation that we held a given price at a given time - the same
role the Merkle root plays for predictions.

Usage
-----
    python -m engine.capture --weeks 2
    python -m engine.capture --weeks 2 --dry-run
    python -m engine.capture --sport ncaaf --weeks 2
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests

from .adapters.nfl import NFLAdapter
from .schema import canonical_book

ESPN = "http://sports.core.api.espn.com/v2/sports"

# One entry per sport we capture. Every number here was checked against the
# live endpoint on 2026-08-28 rather than carried over from the NFL, because
# neither field generalises:
#
#   weeks   ESPN's regular-season (``types/2``) week numbering. The NFL runs
#           weeks 1-18. College football runs 1-15 and puts the bowls under a
#           different season type (``types/3``), which we do not capture.
#           College week 1 is also not a week: it spans 2026-08-22 to
#           2026-09-08, so one "week ahead" is a fortnight of games.
#   groups  ESPN's competition-group filter, and the reason this table exists.
#           Omitting it is silently wrong for college football: the unfiltered
#           week-1 endpoint returns 25 curated "featured" games, while the same
#           week with ``groups=80`` (FBS) returns 99. Nothing in the response
#           says the 25 is a selection. groups=90 would be all of Division I.
LEAGUES: dict[str, dict[str, Any]] = {
    "nfl": {
        "path": "football/leagues/nfl",
        "weeks": range(1, 19),
        "groups": None,
    },
    "ncaaf": {
        "path": "football/leagues/college-football",
        "weeks": range(1, 16),
        "groups": "80",
    },
}

UA = "sooth-odds-capture/1.0 (+https://sooth.co)"
TIMEOUT = 20
PAUSE = 0.25  # be a polite guest on an undocumented free endpoint
PAGE = 200    # ESPN honours this; week_event_ids pages until the count matches


def core(sport: str) -> str:
    return f"{ESPN}/{LEAGUES[sport]['path']}"


@dataclass
class Observation:
    """One price, from one book, at one moment, with its origin recorded."""

    observed_at: str  # UTC, when WE saw it
    event_id: str
    sport: str
    season: int
    week: int
    kickoff: str
    home: str
    away: str
    book: str
    market: str  # spread | total | moneyline
    selection: str  # side_a | side_b | over | under
    line: float | None
    price: int | None
    # espn_open   - ESPN's stated opening number, useful but not ours
    # own_capture - we observed this ourselves at observed_at. Gradeable.
    # espn_close  - ESPN's close block, if it ever appears. Not authoritative.
    provenance: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


class CaptureError(RuntimeError):
    pass


def _get(url: str, session: requests.Session) -> dict[str, Any]:
    r = session.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.json()


def _american(node: Any) -> int | None:
    """ESPN nests American odds under differently-named keys by market."""
    if not isinstance(node, dict):
        return None
    for key in ("american", "alternateDisplayValue", "displayValue"):
        v = node.get(key)
        if isinstance(v, str):
            v = v.replace("+", "").strip()
            if v.lstrip("-").isdigit():
                return int(v)
        elif isinstance(v, (int, float)) and key == "american":
            return int(v)
    return None


def _number(node: Any) -> float | None:
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, dict):
        for key in ("american", "alternateDisplayValue", "displayValue", "value"):
            v = node.get(key)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                v = v.replace("+", "").strip()
                try:
                    return float(v)
                except ValueError:
                    continue
    if isinstance(node, str):
        try:
            return float(node.replace("+", "").strip())
        except ValueError:
            return None
    return None



def minutes_to_next_kickoff(season: int, now: datetime) -> float | None:
    """Minutes until the next unplayed kickoff, from LOCAL data only.

    Deliberately does no HTTP. The 15-minute workflow fires ~96 times a day
    and would otherwise hammer an undocumented free endpoint around the clock
    to discover that the next game is four days away. nflverse gametime is
    US/Eastern; converting it properly matters, because an hour of drift turns
    a closing-line capture into a mid-afternoon one.
    """
    from zoneinfo import ZoneInfo
    import pandas as _pd

    et = ZoneInfo("America/New_York")
    df = NFLAdapter().games
    sub = df[(df["season"] == season) & df["home_score"].isna()
             & df["gametime"].notna()]
    best = None
    for _, r in sub.iterrows():
        day = _pd.to_datetime(r["gameday"], errors="coerce")
        t = str(r["gametime"])
        if _pd.isna(day) or ":" not in t:
            continue
        hh, mm = t.split(":")[:2]
        try:
            ko = datetime(day.year, day.month, day.day, int(hh), int(mm),
                          tzinfo=et).astimezone(timezone.utc)
        except ValueError:
            continue
        if ko < now:
            continue
        delta = (ko - now).total_seconds() / 60.0
        if best is None or delta < best:
            best = delta
    return best


def weeks_with_events(sport: str = "nfl") -> list[int]:
    """Regular-season weeks that exist for this sport."""
    return list(LEAGUES[sport]["weeks"])


def week_event_ids(season: int, week: int, session: requests.Session,
                   sport: str = "nfl") -> tuple[list[str], int]:
    """Every event id in one week, and how many ESPN says the week holds.

    Both, because the gap between them is the bug this function exists to make
    impossible. The previous version asked for ``limit=50`` and returned
    whatever came back. Against the NFL that is harmless - 16 games a week.
    Against college football it is not: on 2026-08-28 ESPN reported 99 FBS
    events in 2026 week 1 across two pages, so a limit of 50 drops 49 games
    with no error and no missing field to notice. A dropped game is a closing
    line that nobody, us included, can ever obtain again.

    So: page until ESPN's own ``pageCount`` is exhausted, and hand the caller
    the ``count`` it declared so a shortfall can be reported rather than
    averaged away.
    """
    cfg = LEAGUES[sport]
    base = f"{core(sport)}/seasons/{season}/types/2/weeks/{week}/events"
    suffix = f"&groups={cfg['groups']}" if cfg["groups"] else ""
    ids: list[str] = []
    expected = 0
    page = 1
    while True:
        try:
            data = _get(f"{base}?limit={PAGE}&page={page}{suffix}", session)
        except requests.HTTPError:
            break
        expected = int(data.get("count") or 0)
        items = data.get("items") or []
        for item in items:
            ref = item.get("$ref", "")
            if "/events/" in ref:
                ids.append(ref.split("/events/")[1].split("?")[0])
        if not items or page >= int(data.get("pageCount") or 1):
            break
        page += 1
        time.sleep(PAUSE)
    # ESPN can list the same event on two pages; ids must be unique but stable.
    seen: set[str] = set()
    uniq = [i for i in ids if not (i in seen or seen.add(i))]
    return uniq, expected


def _extract(
    odds_item: dict[str, Any],
    *,
    meta: dict[str, Any],
    observed_at: str,
    sport: str = "nfl",
) -> Iterator[Observation]:
    """Pull every market we care about out of one provider's odds block."""
    book = canonical_book(odds_item.get("provider", {}).get("name", "unknown"))

    def emit(market, selection, line, price, provenance):
        yield Observation(
            observed_at=observed_at,
            event_id=meta["event_id"],
            sport=sport,
            season=meta["season"],
            week=meta["week"],
            kickoff=meta["kickoff"],
            home=meta["home"],
            away=meta["away"],
            book=book,
            market=market,
            selection=selection,
            line=line,
            price=price,
            provenance=provenance,
        )

    # ``current`` is the block we own: we observed it at observed_at.
    # ``open`` is ESPN's claim about the past - recorded, but labelled.
    for block, provenance in (("current", "own_capture"), ("open", "espn_open"),
                              ("close", "espn_close")):
        for side_key, selection in (("homeTeamOdds", "side_a"),
                                    ("awayTeamOdds", "side_b")):
            side = odds_item.get(side_key, {})
            node = side.get(block) if isinstance(side, dict) else None
            if not isinstance(node, dict):
                continue
            spread = _number(node.get("pointSpread"))
            spread_price = _american(node.get("spread"))
            if spread is not None:
                yield from emit("spread", selection, spread, spread_price, provenance)
            ml = _american(node.get("moneyLine"))
            if ml is not None:
                yield from emit("moneyline", selection, None, ml, provenance)

        ev = odds_item.get(block)
        if isinstance(ev, dict):
            total = _number(ev.get("total")) or _number(odds_item.get("overUnder"))
            for key, selection in (("over", "over"), ("under", "under")):
                price = _american(ev.get(key))
                if price is not None:
                    yield from emit("total", selection, total, price, provenance)

    # Top-level fallback: some events expose only flat fields.
    if not odds_item.get("current") and odds_item.get("spread") is not None:
        sp = _number(odds_item.get("spread"))
        if sp is not None:
            yield from emit("spread", "side_a", sp, None, "own_capture")
        ou = _number(odds_item.get("overUnder"))
        if ou is not None:
            yield from emit("total", "over", ou, _american(odds_item.get("overOdds")),
                            "own_capture")
            yield from emit("total", "under", ou, _american(odds_item.get("underOdds")),
                            "own_capture")


def capture(
    season: int,
    weeks_ahead: int = 2,
    out_dir: Path | str = "data/capture",
    dry_run: bool = False,
    sport: str = "nfl",
) -> tuple[list[Observation], list[str]]:
    """Capture odds for the next unplayed weeks.

    We poll the earliest weeks that still contain future games, which before
    the season means Week 1 - exactly the lines we most want a long series on.

    Returns ``(rows, shortfalls)``. A shortfall is a week where ESPN declared
    more events than we managed to list. The rows are still returned and still
    written - partial evidence beats none - but the caller is expected to make
    the run fail loudly afterwards, because a shortfall nobody is told about is
    precisely the failure this module exists to prevent.
    """
    session = requests.Session()
    now = datetime.now(timezone.utc)
    observed_at = now.isoformat()
    rows: list[Observation] = []
    shortfalls: list[str] = []
    weeks_done = 0
    base = core(sport)

    for week in weeks_with_events(sport):
        if weeks_done >= weeks_ahead:
            break
        ids, expected = week_event_ids(season, week, session, sport)
        if expected and len(ids) < expected:
            shortfalls.append(
                f"{sport} {season} week {week}: listed {len(ids)} of the "
                f"{expected} events ESPN reports")
        if not ids:
            continue

        week_has_future = False
        for eid in ids:
            try:
                ev = _get(f"{base}/events/{eid}", session)
            except requests.HTTPError:
                continue
            time.sleep(PAUSE)

            kickoff = str(ev.get("date", ""))
            try:
                ko = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ko <= now:
                continue  # already started - odds are gone or meaningless
            week_has_future = True

            comps = ev.get("competitions", [{}])
            comp_id = comps[0].get("id", eid) if comps else eid
            name = str(ev.get("name", ""))
            away, home = ("", "")
            if " at " in name:
                away, home = name.split(" at ", 1)

            meta = {
                "event_id": eid,
                "season": season,
                "week": week,
                "kickoff": kickoff,
                "home": home.strip(),
                "away": away.strip(),
            }

            try:
                odds = _get(
                    f"{base}/events/{eid}/competitions/{comp_id}/odds", session
                )
            except requests.HTTPError:
                continue
            time.sleep(PAUSE)

            for item in odds.get("items", []):
                rows.extend(_extract(item, meta=meta, observed_at=observed_at,
                                     sport=sport))

        if week_has_future:
            weeks_done += 1

    if not dry_run and rows:
        out = Path(out_dir) / sport
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{now:%Y-%m-%d}.jsonl"
        with path.open("a") as fh:  # append-only. We never rewrite history.
            for r in rows:
                fh.write(r.to_json() + "\n")

    return rows, shortfalls


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--weeks", type=int, default=2)
    ap.add_argument("--sport", default="nfl", choices=sorted(LEAGUES))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--within-minutes", type=float, default=None,
                    help="only capture if a kickoff is within N minutes; "
                         "otherwise exit doing nothing (NFL only)")
    args = ap.parse_args()

    if args.within_minutes is not None:
        # minutes_to_next_kickoff reads the nflverse schedule. Letting another
        # sport through would silently gate its capture on the NFL calendar.
        if args.sport != "nfl":
            raise SystemExit("--within-minutes is NFL-only: it reads the "
                             "nflverse schedule and knows no other sport")
        mins = minutes_to_next_kickoff(args.season, datetime.now(timezone.utc))
        if mins is None or mins > args.within_minutes:
            nxt = "none scheduled" if mins is None else f"{mins:.0f} min away"
            print(f"skip: next kickoff {nxt}, window is "
                  f"{args.within_minutes:.0f} min")
            return

    rows, shortfalls = capture(args.season, args.weeks,
                               dry_run=args.dry_run, sport=args.sport)
    books = sorted({r.book for r in rows})
    events = sorted({r.event_id for r in rows})
    by_prov: dict[str, int] = {}
    for r in rows:
        by_prov[r.provenance] = by_prov.get(r.provenance, 0) + 1

    print(f"sport        : {args.sport}")
    print(f"observations : {len(rows)}")
    print(f"events       : {len(events)}")
    print(f"books        : {', '.join(books) if books else 'none'}")
    print(f"by provenance: {by_prov}")
    if args.dry_run:
        print("(dry run - nothing written)")
    for r in rows[:6]:
        print(f"  {r.away} @ {r.home} {r.market:9} {r.selection:6} "
              f"line={r.line} price={r.price} [{r.provenance}]")

    # Everything above has already been written. Only now do we fail, so a
    # shortfall costs us a red run and not the evidence we did manage to get.
    if shortfalls:
        for s in shortfalls:
            print(f"SHORTFALL: {s}")
        raise SystemExit(
            f"{len(shortfalls)} week(s) returned fewer events than ESPN "
            f"reported - games may be uncaptured. Rows already written.")


if __name__ == "__main__":
    main()
