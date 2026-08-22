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
from datetime import datetime, timezone
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
    player: str               # player props only; "" for game lines
    kickoff: str              # ISO start time, "" when the capture row lacks it
    book: str
    from_price: int | None    # drift: earlier price. divergence: None.
    to_price: int
    move_pts: float           # signed, in points of implied probability
    observed_at: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_observations(pattern: str = "data/capture/*/*.jsonl",
                      include_props: bool = False) -> list[dict]:
    """Every price we watched ourselves, oldest first.

    Player props are EXCLUDED BY DEFAULT and that default is deliberate. The
    glob data/capture/*/*.jsonl also matches data/capture/mlb-props, and folding
    prop quotes into the game-line pass published pitcher-strikeout prices under
    "Books off the pack right now" and surfaced games that had finished a day
    earlier. Both causes are now fixed — not_started reads commence_time, and
    _series keys on player — but the fix is opt-in rather than automatic so no
    existing caller changes behaviour by inheriting it. engine.alert_email and
    the published moves.json both take the default and are untouched.
    """
    rows: list[dict] = []
    for path in sorted(glob.glob(pattern)):
        if not include_props and Path(path).parent.name.endswith("-props"):
            continue
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


def _series(rows: Iterable[dict],
            by_player: bool = False) -> dict[tuple, list[dict]]:
    """One price history per (event, market, selection, LINE, PLAYER, book).

    The line is part of the identity: -105 at total 47.5 and -115 at total
    48.5 are prices for different bets, and comparing them manufactures a
    juice move that never happened. A book re-posting at a new line starts a
    new series; the line move itself is visible on the board, not faked here.

    The player is part of it for the same reason, and props make it load
    bearing: both starting pitchers in one game have pitcher_strikeouts, so
    without the player two opposing starters at the same line and book share a
    key. On the data this was fixed against, 346 keys merged two or more
    different players — Michael Lorenzen and Michael McGreevy, strikeouts over
    3.5, DraftKings, among them. Comparing one pitcher's price to another's and
    publishing the difference as movement is a fabricated alert carrying a real
    player's name.

    by_player is OPT-IN so the key shape does not change under callers that
    never asked for props. engine.research and engine.timeline unpack a
    five-tuple and only ever read game-line captures; they keep exactly the key
    they had. Only the prop path asks for the sixth component.
    """
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (str(r.get("event_id")), str(r.get("market")),
               str(r.get("selection")), str(r.get("line")))
        key += ((str(r.get("player")),) if by_player else ()) + (str(r.get("book")),)
        out[key].append(r)
    for k in out:
        out[k].sort(key=lambda r: str(r.get("observed_at", "")))
    return out


def find_drift(rows: list[dict], min_move: float = DEFAULT_MIN_MOVE, by_player: bool = False) -> list[Alert]:
    """A book's own price moved between consecutive observations.

    Compares each observation to the one before it on the same series, so a
    slow walk across many small steps raises an alert on the step that crosses
    the threshold rather than never raising one at all.
    """
    # Same rule as divergence: a move on a game that has already started is
    # history, not an opportunity, and it inflates the "alerts fired in 48h"
    # count the Pro card sells against. Measured 2026-08-11: 1,798 of 1,971
    # drift alerts were for games already played.
    now = datetime.now(timezone.utc)
    rows = [r for r in rows if not_started(r, now)]

    alerts: list[Alert] = []
    for key, obs in _series(rows, by_player=by_player).items():
        event_id, market, selection, line = key[:4]
        player, book = (key[4], key[5]) if by_player else ("", key[4])
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
                line=cur.get("line"), player=str(cur.get("player") or ""),
                kickoff=str(cur.get("kickoff") or cur.get("commence_time") or ""),
                book=book,
                from_price=int(prev["price"]), to_price=int(cur["price"]),
                move_pts=round(delta, 2),
                observed_at=str(cur.get("observed_at", "")),
                detail=(f"{book} {direction} {abs(delta):.2f} pts on {selection}"
                        f"{at_line} ({prev['price']:+d} to {cur['price']:+d})"),
            ))
    return sorted(alerts, key=lambda a: -abs(a.move_pts))


def find_divergence(rows: list[dict], min_move: float = DEFAULT_MIN_MOVE, by_player: bool = False) -> list[Alert]:
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
        if not not_started(r, now):
            continue
        key = (str(r.get("event_id")), str(r.get("market")),
               str(r.get("selection")), str(r.get("line")))
        # The player belongs in the identity for the same reason the line does.
        # Both starting pitchers in one game have pitcher_strikeouts, so without
        # it two opposing starters at the same line pool into one "consensus"
        # and each is reported as diverging from the other. That is a fabricated
        # alert with a real player's name on it, and this is the function whose
        # output gets published.
        key += ((str(r.get("player")),) if by_player else ()) + (str(r.get("book")),)
        cur = latest.get(key)
        if cur is None or str(r.get("observed_at", "")) > str(cur.get("observed_at", "")):
            latest[key] = r

    by_selection: dict[tuple, list[dict]] = defaultdict(list)
    for key, r in latest.items():
        by_selection[key[:5] if by_player else key[:4]].append(r)

    alerts: list[Alert] = []
    for sel_key, quotes in by_selection.items():
        event_id, market, selection, line = sel_key[:4]
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
                line=q.get("line"), player=str(q.get("player") or ""),
                kickoff=str(q.get("kickoff") or q.get("commence_time") or ""),
                book=str(q.get("book", "")),
                from_price=None, to_price=int(q["price"]),
                move_pts=round(delta, 2),
                observed_at=str(q.get("observed_at", "")),
                detail=(f"{q.get('book')} pays {delta:.2f} pts more than the "
                        f"{len(quotes)}-book consensus on {selection}{at_line} "
                        f"({q['price']:+d})"),
            ))
    return sorted(alerts, key=lambda a: -a.move_pts)


def not_started(row: dict, now: "datetime | None" = None) -> bool:
    """True only when we can PROVE this row's game has not started yet.

    Fails closed on purpose. The old inline check ran `if kickoff:` and let a
    row through when the field was empty, so anything captured without a start
    time was advertised as a live opportunity forever. An alert we cannot date
    is not an alert we can publish under the word "now".
    """
    now = now or datetime.now(timezone.utc)
    # Game-line captures carry `kickoff`; player-prop captures carry
    # `commence_time` for the same thing. Reading only the first silently
    # excluded every prop row from drift and divergence — 3412 of 3697 rows on
    # disk at the time this was fixed — which is why moves.json carried no prop
    # markets at all. Nothing errored; the gate simply failed closed on all of
    # them, which is the correct behaviour applied to the wrong field name.
    kick = str(row.get("kickoff") or row.get("commence_time") or "")
    if not kick:
        return False
    try:
        return datetime.fromisoformat(kick.replace("Z", "+00:00")) > now
    except ValueError:
        return False


def scan(pattern: str = "data/capture/*/*.jsonl",
         min_move: float = DEFAULT_MIN_MOVE,
         include_props: bool = False) -> dict[str, Any]:
    rows = load_observations(pattern, include_props=include_props)
    drift = find_drift(rows, min_move, by_player=include_props)
    div = find_divergence(rows, min_move, by_player=include_props)
    return {
        # Every other published feed carries generated_at and the page stamps
        # itself from them; moves.json was the one exception, so 2,000+ drift
        # alerts rendered with no way to tell how old the scan was.
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
