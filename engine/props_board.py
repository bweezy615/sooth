"""Aggregate captured MLB prop prices into the site's props.json.

Mirrors ``engine/props_board``'s sibling on the moneyline side: read the
append-only capture, take the newest price per (prop, book), then for each
prop publish the best available price per side and the de-vigged fair
probability. Shopping the best number is +EV on its own — same core claim as
the board, applied to player props.

    python -m engine.props_board
    python -m engine.props_board --in data/capture/mlb-props --out site/public/data/props.json

No data yet is not an error: an empty ``props`` list ships and the page shows
its empty state until the capture cron fills it.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schema import canonical_book

DEFAULT_IN = "data/capture/mlb-props"
DEFAULT_OUT = "site/public/data/props.json"


def implied_prob(american: int | float) -> float:
    """American odds -> implied probability (with the book's vig still in)."""
    p = float(american)
    return 100.0 / (p + 100.0) if p > 0 else -p / (-p + 100.0)


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


# Human labels for the site. Unknown markets prettify from the snake_case id
# so a new market never renders as a raw token.
MARKET_LABELS = {"pitcher_strikeouts": "Strikeouts"}


def market_label(market: str) -> str:
    return MARKET_LABELS.get(market, str(market).replace("_", " ").title())


def fair_american(prob: float) -> int:
    """Fair probability -> American odds. The de-vigged price a book would post
    with no margin; the grid shows it beside the real price so the gap is legible.
    """
    prob = min(max(prob, 1e-6), 1 - 1e-6)
    return -round(100 * prob / (1 - prob)) if prob >= 0.5 else round(100 * (1 - prob) / prob)


def _newest_quotes(rows: list[dict]) -> dict:
    """Keep the newest observation per (prop, side, book).

    Key: (event_id, player, market, line, selection, book) -> row with the
    latest observed_at. Append-only history means the same book appears many
    times; only its last price before we stopped watching counts.
    """
    latest: dict[tuple, dict] = {}
    for r in rows:
        key = (r.get("event_id"), r.get("player"), r.get("market"),
               r.get("line"), r.get("selection"), r.get("book"))
        prev = latest.get(key)
        if prev is None or r.get("observed_at", "") > prev.get("observed_at", ""):
            latest[key] = r
    return latest


def _side_summary(quotes: list[dict]) -> dict | None:
    """Best price + book and the raw median implied prob for one prop side."""
    priced = [q for q in quotes if q.get("price") is not None]
    if not priced:
        return None
    best = max(priced, key=lambda q: q["price"])  # highest American = best payout
    return {
        "quotes": [{"book": q["book"], "price": q["price"]} for q in priced],
        "best_price": best["price"],
        "best_book": best["book"],
        "raw_implied": median([implied_prob(q["price"]) for q in priced]),
    }


def _in_window(row: dict, now: datetime, window_hours: float) -> bool:
    """Keep upcoming/live games; drop ones that finished hours ago.

    props_capture appends forever, so without this the grid would accumulate
    every game ever captured. Mirror the board's forward-window idea: a game is
    current from a few hours before we'd stop watching until ``window_hours``
    ahead. A row with no parseable start is kept (fail open, never hide data).
    """
    # props_capture names this commence_time; every other capture path in the
    # repo names it kickoff. Read either rather than silently failing open on
    # a row that does carry a start time under the other name.
    ct = row.get("commence_time") or row.get("kickoff")
    if not ct:
        return True
    try:
        start = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
    except ValueError:
        return True
    return now - timedelta(hours=3) <= start <= now + timedelta(hours=window_hours)


def _side_out(summary: dict | None, fair_prob: float | None) -> dict | None:
    """One prop side, ready for the grid: best price + book, the de-vigged fair
    price, how many points the best number beats fair by, and every book's quote.
    """
    if not summary or fair_prob is None:
        return None
    return {
        "quotes": summary["quotes"],
        "n_books": len(summary["quotes"]),
        "best_price": summary["best_price"],
        "best_book": summary["best_book"],
        "fair_prob": round(fair_prob, 4),
        "fair_price": fair_american(fair_prob),
        # points of implied probability the best price saves vs fair.
        # positive = the best number is cheaper than fair = value.
        "edge_vs_fair_pts": round((fair_prob - implied_prob(summary["best_price"])) * 100, 2),
    }


def build_props(rows: list[dict], now: datetime | None = None,
                window_hours: float = 36.0) -> list[dict]:
    """Pivoted props: one record per (event, player, market, line), carrying
    BOTH sides. The site renders a prop as one row with Over and Under side by
    side, so the two sides must travel together — flattening them apart is what
    left the grid unable to render.
    """
    # Only rows this module actually understands. engine.props used to append
    # its own nested shape ({"over": {...}, "under": {...}}, start time under
    # "kickoff") into the same data/capture/mlb-props directory props_capture
    # owns. Those rows have no top-level selection/price, so they never became
    # quotes — but they DID reach `rep` below and could win the representative
    # slot for a prop, handing it starts="". The page filters on
    # `new Date(starts) > Date.now()`, and Invalid Date is never greater, so a
    # correctly priced prop silently vanished from every view. Capture is
    # append-only evidence and is never rewritten, so the historical rows stay
    # on disk; we simply stop reading what was never ours.
    rows = [r for r in rows
            if r.get("selection") is not None and r.get("price") is not None]

    # Normalise book identity on READ as well as on write, the same way
    # alerts.py does and for the same reason: data/capture is append-only
    # evidence and is never rewritten, so every row captured before
    # props_capture started canonicalising still carries the raw API slug
    # (betonlineag, williamhill_us). Two spellings of one operator would both
    # count toward n_books and toward the median that becomes the fair line.
    rows = [dict(r, book=canonical_book(r.get("book", ""))) for r in rows]
    if now is not None:
        rows = [r for r in rows if _in_window(r, now, window_hours)]
    latest = _newest_quotes(rows)

    # group latest quotes by prop (event, player, market, line) then by side,
    # keeping one representative row per prop for the event fields (home/away).
    props: dict[tuple, dict[str, list[dict]]] = {}
    rep: dict[tuple, dict] = {}
    for (event_id, player, market, line, selection, _book), r in latest.items():
        pk = (event_id, player, market, line)
        prop = props.setdefault(pk, {"over": [], "under": []})
        if selection in prop:
            prop[selection].append(r)
        rep.setdefault(pk, r)

    out: list[dict] = []
    for (event_id, player, market, line), sides in props.items():
        over, under = _side_summary(sides["over"]), _side_summary(sides["under"])

        # de-vig: normalise the two sides' raw implied probs to sum to 1.
        # one-sided props keep their raw implied (nothing to strip against).
        fo = fu = None
        if over and under:
            tot = over["raw_implied"] + under["raw_implied"]
            fo, fu = over["raw_implied"] / tot, under["raw_implied"] / tot
        elif over:
            fo = over["raw_implied"]
        elif under:
            fu = under["raw_implied"]

        o, u = _side_out(over, fo), _side_out(under, fu)
        # The grid renders Over AND Under on one row and reads both unconditionally,
        # so a prop needs both priced to show. This also drops the idle-tick marker
        # rows (selection/price None) that props_capture writes on empty slates.
        # ponytail: one-sided props are dropped — books post both sides on pitcher
        # strikeouts, so in practice this only removes the phantoms.
        if not (o and u):
            continue
        r = rep[(event_id, player, market, line)]
        gain = max(o["edge_vs_fair_pts"], u["edge_vs_fair_pts"])
        out.append({
            "event_id": event_id,
            "player": player,
            "market": market,
            "market_label": market_label(market),
            "line": line,
            "home": r.get("home", ""),
            "away": r.get("away", ""),
            "starts": r.get("commence_time", ""),
            "over": o,
            "under": u,
            "gain_pts": round(gain, 2),
        })

    out.sort(key=lambda p: p["gain_pts"], reverse=True)
    return out


def build_document(rows: list[dict], now: datetime | None = None,
                   window_hours: float = 36.0) -> dict:
    """The full props.json: pivoted props grouped into the boards[] -> events[]
    -> props[] shape every page reads (same nesting as board.json). One board
    for now (MLB pitcher strikeouts); the structure holds more without change.
    """
    props = build_props(rows, now=now, window_hours=window_hours)

    events: dict[str, dict] = {}
    for p in props:
        ev = events.setdefault(p["event_id"], {
            "id": p["event_id"], "home": p["home"], "away": p["away"],
            "starts": p["starts"], "props": []})
        ev["props"].append(p)
    ev_list = sorted(events.values(), key=lambda e: e["starts"])

    boards = [{"sport": "mlb", "label": "MLB", "n_props": len(props),
               "events": ev_list}] if props else []
    return {
        "sport": "mlb",
        "market": "pitcher_strikeouts",
        "note": "Best available price per prop side across books, "
                "and the de-vigged fair line. Shopping the best number is +EV.",
        "n_props": len(props),
        "boards": boards,
    }


def read_rows(in_dir: Path) -> list[dict]:
    rows: list[dict] = []
    if not in_dir.exists():
        return rows
    for f in sorted(in_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", default=DEFAULT_IN)
    ap.add_argument("--out", dest="out", default=DEFAULT_OUT)
    ap.add_argument("--window-hours", type=float, default=36.0,
                    help="forward window; games past this (or finished >3h ago) drop off")
    args = ap.parse_args()

    rows = read_rows(Path(args.in_dir))
    doc = build_document(rows, now=datetime.now(timezone.utc),
                         window_hours=args.window_hours)
    doc = {"generated_at": datetime.now(timezone.utc).isoformat(), **doc}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic, like lines.py/props.py/middles.py/best_lines.py. A bare
    # write_text can leave a half-written props.json if the process dies
    # mid-write, and a reader that hits truncated JSON has no good options.
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, out)
    print(f"wrote {out}  ({doc['n_props']} props from {len(rows)} observations)")


if __name__ == "__main__":
    main()
