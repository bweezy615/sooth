"""Line-movement detection over our own capture history.

Two things are worth telling a bettor about, and they are not the same thing:

**Drift** — a single book's own price moved between two of our observations.
That is the book changing its mind, and if it moved *toward* you after you bet,
you beat the close.

**Divergence** — a book's price right now sits away from the cross-book
consensus. That is the one that pays immediately: it means a better number is
sitting there while the rest of the market disagrees.

Both are measured in **points of implied probability**, never in American odds.
American odds are non-linear and discontinuous across ±100: -110 to -120 and
+110 to +100 look like similar moves and are not. Comparing them directly is
how a move detector ends up firing on nothing and missing everything.

Provenance gate, same discipline as closing-line value: only ``own_capture``
rows count. ``espn_open`` and ``espn_close`` are someone else's claim about a
price we did not watch, and an alert built on them is a guess with a timestamp.

    python -m engine.alerts --min-move 1.5
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from .schema import canonical_book

# Only prices we watched ourselves may raise an alert.
ALERT_PROVENANCE = frozenset({"own_capture"})

# Points of implied probability. A typical two-sided market carries 4-5 points
# of vig in total, so 1.5 points is a real move rather than a tick.
DEFAULT_MIN_MOVE = 1.5


def implied(price: int) -> float:
    """American odds -> implied probability, vig included."""
    return (-price) / ((-price) + 100.0) if price < 0 else 100.0 / (price + 100.0)


@dataclass
class Alert:
    kind: str                 # "drift" | "divergence"
    sport: str
    event_id: str
    home: str
    away: str
    market: str
    selection: str
    line: float | None        # spread/total line the price was quoted at
    kickoff: str              # ISO start time, "" when the capture row lacks it
    book: str
    from_price: int | None    # drift: earlier price. divergence: None.
    to_price: int
    move_pts: float           # signed, in points of implied probability
    observed_at: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_observations(pattern: str = "data/capture/*/*.jsonl") -> list[dict]:
    """Every price we watched ourselves, oldest first."""
    rows: list[dict] = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("provenance") in ALERT_PROVENANCE and r.get("price") is not None:
                    # Normalise identity on READ as well as on write. Rows
                    # captured before canonical_book existed still carry the
                    # source's spelling, and data/capture is append-only
                    # evidence that must never be rewritten to fix them. One
                    # operator counted as two books can manufacture a consensus
                    # that does not exist.
                    r["book"] = canonical_book(r.get("book", ""))
                    rows.append(r)
    rows.sort(key=lambda r: str(r.get("observed_at", "")))
    return rows


def _series(rows: Iterable[dict]) -> dict[tuple, list[dict]]:
    """One price history per (event, market, selection, LINE, book).

    The line is part of the identity: -105 at total 47.5 and -115 at total
    48.5 are prices for different bets, and comparing them manufactures a
    juice move that never happened. A book re-posting at a new line starts a
    new series; the line move itself is visible on the board, not faked here.
    """
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (str(r.get("event_id")), str(r.get("market")),
               str(r.get("selection")), str(r.get("line")), str(r.get("book")))
        out[key].append(r)
    for k in out:
        out[k].sort(key=lambda r: str(r.get("observed_at", "")))
    return out


def find_drift(rows: list[dict], min_move: float = DEFAULT_MIN_MOVE) -> list[Alert]:
    """A book's own price moved between consecutive observations.

    Compares each observation to the one before it on the same series, so a
    slow walk across many small steps raises an alert on the step that crosses
    the threshold rather than never raising one at all.
    """
    alerts: list[Alert] = []
    for (event_id, market, selection, line, book), obs in _series(rows).items():
        for prev, cur in zip(obs, obs[1:]):
            delta = (implied(int(cur["price"])) - implied(int(prev["price"]))) * 100
            if abs(delta) < min_move:
                continue
            direction = "shortened" if delta > 0 else "drifted out"
            at_line = f" at {line}" if line not in ("None", "") else ""
            alerts.append(Alert(
                kind="drift", sport=str(cur.get("sport", "")), event_id=event_id,
                home=str(cur.get("home", "")), away=str(cur.get("away", "")),
                market=market, selection=selection,
                line=cur.get("line"), kickoff=str(cur.get("kickoff", "")),
                book=book,
                from_price=int(prev["price"]), to_price=int(cur["price"]),
                move_pts=round(delta, 2),
                observed_at=str(cur.get("observed_at", "")),
                detail=(f"{book} {direction} {abs(delta):.2f} pts on {selection}"
                        f"{at_line} ({prev['price']:+d} to {cur['price']:+d})"),
            ))
    return sorted(alerts, key=lambda a: -abs(a.move_pts))


def find_divergence(rows: list[dict], min_move: float = DEFAULT_MIN_MOVE) -> list[Alert]:
    """A book's latest price sits away from the cross-book consensus.

    Consensus is the median across books on the same selection at the latest
    observation each book has. Median rather than mean so one stale book cannot
    drag the reference it is being measured against.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    latest: dict[tuple, dict] = {}
    for r in rows:
        # A price on a game that has started is not an opportunity.
        kick = str(r.get("kickoff", ""))
        if kick:
            try:
                if datetime.fromisoformat(kick.replace("Z", "+00:00")) <= now:
                    continue
            except ValueError:
                pass
        key = (str(r.get("event_id")), str(r.get("market")),
               str(r.get("selection")), str(r.get("line")), str(r.get("book")))
        cur = latest.get(key)
        if cur is None or str(r.get("observed_at", "")) > str(cur.get("observed_at", "")):
            latest[key] = r

    by_selection: dict[tuple, list[dict]] = defaultdict(list)
    for (event_id, market, selection, line, _), r in latest.items():
        by_selection[(event_id, market, selection, line)].append(r)

    alerts: list[Alert] = []
    for (event_id, market, selection, line), quotes in by_selection.items():
        # Stale quotes may no longer be offered: only books observed within
        # two capture cycles of the freshest observation join the consensus.
        newest = max(str(q.get("observed_at", "")) for q in quotes)
        try:
            cutoff = (datetime.fromisoformat(newest.replace("Z", "+00:00"))
                      - timedelta(hours=7))
            quotes = [q for q in quotes
                      if datetime.fromisoformat(
                          str(q.get("observed_at", "")).replace("Z", "+00:00")) >= cutoff]
        except ValueError:
            pass
        if len(quotes) < 3:      # a consensus of two books is not a consensus
            continue
        probs = [implied(int(q["price"])) for q in quotes]
        consensus = statistics.median(probs)
        for q, p in zip(quotes, probs):
            delta = (consensus - p) * 100   # positive: this book pays MORE than consensus
            if delta < min_move:
                continue
            at_line = f" at {line}" if line not in ("None", "") else ""
            alerts.append(Alert(
                kind="divergence", sport=str(q.get("sport", "")), event_id=event_id,
                home=str(q.get("home", "")), away=str(q.get("away", "")),
                market=market, selection=selection,
                line=q.get("line"), kickoff=str(q.get("kickoff", "")),
                book=str(q.get("book", "")),
                from_price=None, to_price=int(q["price"]),
                move_pts=round(delta, 2),
                observed_at=str(q.get("observed_at", "")),
                detail=(f"{q.get('book')} pays {delta:.2f} pts more than the "
                        f"{len(quotes)}-book consensus on {selection}{at_line} "
                        f"({q['price']:+d})"),
            ))
    return sorted(alerts, key=lambda a: -a.move_pts)


def scan(pattern: str = "data/capture/*/*.jsonl",
         min_move: float = DEFAULT_MIN_MOVE) -> dict[str, Any]:
    rows = load_observations(pattern)
    drift = find_drift(rows, min_move)
    div = find_divergence(rows, min_move)
    return {
        "observations": len(rows),
        "min_move_pts": min_move,
        "drift": [a.to_dict() for a in drift],
        "divergence": [a.to_dict() for a in div],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-move", type=float, default=DEFAULT_MIN_MOVE)
    ap.add_argument("--pattern", default="data/capture/*/*.jsonl")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    res = scan(a.pattern, a.min_move)
    print(f"observations   : {res['observations']}")
    print(f"threshold      : {res['min_move_pts']} pts of implied probability")
    print(f"drift alerts   : {len(res['drift'])}")
    print(f"divergence     : {len(res['divergence'])}")
    for a_ in res["drift"][:6]:
        print(f"  DRIFT  {a_['away']} at {a_['home']:<22} {a_['detail']}")
    for a_ in res["divergence"][:6]:
        print(f"  DIVERGE {a_['away']} at {a_['home']:<22} {a_['detail']}")
    if a.out:
        tmp = Path(a.out + ".tmp")
        tmp.write_text(json.dumps(res, indent=1))
        os.replace(tmp, a.out)
        print(f"written: {a.out}")


if __name__ == "__main__":
    main()
