"""Timeline — the market's price history, published as data.

Everything else on the site answers "what is the price now?". This file
answers "where has it been?" — per book, per market, per upcoming game,
as a series the front end can draw without touching the capture archive.

The unit is points of implied probability, the same unit as every alert and
every gain figure on the site, and for the same reason engine.alerts refuses
American odds: -110 to -120 and +110 to +100 look like similar moves and are
not. One unit, comparable everywhere, across every market type.

Identity discipline is inherited, not reinvented: series come from
``alerts.load_observations`` (own_capture provenance only, canonical book
names) keyed by (event, market, selection, LINE, book) via ``alerts._series``,
and lines are paired with ``research._line_group`` — so a spread re-posting at
a new number starts a new series here exactly as it does everywhere else.
A book's history is only ever a history of the same bet.

One reference side per market — home for moneyline/spread, over for totals —
because two mirrored traces per book say nothing twice.

    python -m engine.timeline --sports nfl,mlb
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
from pathlib import Path

from .alerts import _series, load_observations
from .research import _line_group
from .schema import american_to_prob

WINDOW_H = 72          # how far back a trace reaches
MAX_EVENTS = 48        # slate cap, keeps the file honest about its size
PTS = 100.0


def _parse(ts):
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _is_ref(market: str, sel: str, home: str) -> bool:
    """The one side a market is charted from."""
    if market == "total":
        return sel == "over"
    return sel in ("side_a", home)      # ESPN capture speaks side_a; Odds API speaks club names


def build_sport(sport: str, root: Path, now: dt.datetime) -> list[dict]:
    rows = load_observations(str(root / f"data/capture/{sport}/*.jsonl"))
    series = _series(rows)
    horizon = now - dt.timedelta(hours=WINDOW_H)

    events: dict[str, dict] = {}
    for r in rows:
        ko = _parse(r.get("kickoff"))
        if ko and ko > now:
            events.setdefault(str(r["event_id"]), {
                "event_id": str(r["event_id"]), "sport": sport,
                "home": r.get("home"), "away": r.get("away"),
                "kickoff": r.get("kickoff"), "_ko": ko})

    out = []
    for ev in sorted(events.values(), key=lambda e: e["_ko"])[:MAX_EVENTS]:
        eid = ev.pop("_ko") and ev["event_id"]
        markets = {}
        for market in ("moneyline", "spread", "total"):
            # dominant line, by observation count — the line the market is on
            counts: dict[str, int] = {}
            for (e, mk, sel, ln, _bk), rws in series.items():
                if e != eid or mk != market:
                    continue
                g = _line_group(market, ln)
                counts[g] = counts.get(g, 0) + len(rws)
            if not counts:
                continue
            dom = max(counts, key=lambda k: counts[k])

            books: dict[str, dict[int, float]] = {}
            headline = None
            for (e, mk, sel, ln, bk), rws in series.items():
                if e != eid or mk != market or _line_group(market, ln) != dom:
                    continue
                if not _is_ref(market, str(sel), ev["home"]):
                    continue
                if headline is None and ln not in (None, "None"):
                    headline = float(ln)
                for r in rws:
                    t = _parse(r.get("observed_at"))
                    if not t or t < horizon or r.get("price") is None:
                        continue
                    bucket = int(t.timestamp() // 3600 * 3600)
                    # last observation in the hour wins — it is the freshest
                    books.setdefault(bk, {})[bucket] = round(
                        american_to_prob(int(r["price"])) * PTS, 2)

            traces = [{"book": bk, "pts": sorted(pts.items())}
                      for bk, pts in sorted(books.items()) if len(pts) >= 2]
            if not traces:
                continue
            # consensus baseline: median across books per bucket
            allb = sorted({b for tr in traces for b, _ in tr["pts"]})
            cons = []
            for b in allb:
                vals = [dict(tr["pts"]).get(b) for tr in traces]
                vals = [v for v in vals if v is not None]
                if vals:
                    cons.append([b, round(statistics.median(vals), 2)])
            markets[market] = {
                "line": headline,
                "ref": "over" if market == "total" else "home",
                "unit": "implied probability, points",
                "n_books": len(traces),
                # a consensus of one book IS that book — publishing both would
                # double the payload to draw the same trace twice
                "consensus": cons if len(traces) > 1 else [],
                "books": traces,
            }
        if markets:
            ev["markets"] = markets
            out.append(ev)
    return out


def build(sports: list[str], root: Path, out_dir: Path, dry_run=False) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    events = []
    for sp in sports:
        events += build_sport(sp, root, now)

    doc = {
        "generated_at": now.isoformat(),
        "window_hours": WINDOW_H,
        "note": ("Price history from our own capture, hourly, in points of "
                 "implied probability. One reference side per market; a line "
                 "change starts a new series and is never charted as a price move."),
        "n_events": len(events),
        "events": events,
    }
    if not dry_run:
        out = out_dir / "timeline.json"
        if not events and out.exists():
            # an empty archive is a capture problem, not a market fact —
            # keep the last real history and stamp the attempt
            try:
                prev = json.loads(out.read_text())
                prev["checked_at"] = now.isoformat()
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(prev, separators=(",", ":")))
                os.replace(tmp, out)
                return prev
            except (json.JSONDecodeError, OSError):
                pass
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, separators=(",", ":")))
        os.replace(tmp, out)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sports", default="nfl,ncaaf,mlb,nhl,nba")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out-dir", default="site/public/data")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    doc = build([s.strip() for s in a.sports.split(",") if s.strip()],
                Path(a.root), Path(a.out_dir), a.dry_run)
    for e in doc["events"][:4]:
        mks = {m: v["n_books"] for m, v in e["markets"].items()}
        print(f"  {e['away']} at {e['home']} ({e['sport']}): {mks}")
    print(f"{doc['n_events']} events, window {doc['window_hours']}h")


if __name__ == "__main__":
    main()
