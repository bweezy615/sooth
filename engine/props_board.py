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
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    ct = row.get("commence_time")
    if not ct:
        return True
    try:
        start = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
    except ValueError:
        return True
    return now - timedelta(hours=3) <= start <= now + timedelta(hours=window_hours)


def build_props(rows: list[dict], now: datetime | None = None,
                window_hours: float = 36.0) -> list[dict]:
    if now is not None:
        rows = [r for r in rows if _in_window(r, now, window_hours)]
    latest = _newest_quotes(rows)

    # group latest quotes by prop (event, player, market, line) then by side
    props: dict[tuple, dict[str, list[dict]]] = {}
    for (event_id, player, market, line, selection, _book), r in latest.items():
        prop = props.setdefault((event_id, player, market, line),
                                {"over": [], "under": []})
        if selection in prop:
            prop[selection].append(r)

    out: list[dict] = []
    for (event_id, player, market, line), sides in props.items():
        summ = {s: _side_summary(qs) for s, qs in sides.items()}
        over, under = summ.get("over"), summ.get("under")

        # de-vig: normalise the two sides' raw implied probs to sum to 1.
        # one-sided props keep their raw implied (nothing to strip against).
        fair = {}
        if over and under:
            tot = over["raw_implied"] + under["raw_implied"]
            fair["over"] = over["raw_implied"] / tot
            fair["under"] = under["raw_implied"] / tot
        else:
            if over:
                fair["over"] = over["raw_implied"]
            if under:
                fair["under"] = under["raw_implied"]

        _rep = sides.get("over") or sides.get("under") or []
        any_row = _rep[0] if _rep else None
        for side, s in (("Over", over), ("Under", under)):
            key = side.lower()
            if not s:
                continue
            fp = fair[key]
            best_ip = implied_prob(s["best_price"])
            out.append({
                "event_id": event_id,
                "player": player,
                "team": any_row.get("home") if any_row else "",
                "market": market,
                "line": line,
                "side": side,
                "commence_time": any_row.get("commence_time", "") if any_row else "",
                "quotes": s["quotes"],
                "best_price": s["best_price"],
                "best_book": s["best_book"],
                "fair_prob": round(fp, 4),
                # points of implied probability the best price saves vs fair.
                # positive = the best number is cheaper than fair = value.
                "edge_pts": round((fp - best_ip) * 100, 2),
            })

    out.sort(key=lambda p: p["edge_pts"], reverse=True)
    return out


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
    props = build_props(rows, now=datetime.now(timezone.utc),
                        window_hours=args.window_hours)
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sport": "mlb",
        "market": "pitcher_strikeouts",
        "note": "Best available price per prop side across books, "
                "and the de-vigged fair line. Shopping the best number is +EV.",
        "n_props": len(props),
        "props": props,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out}  ({len(props)} prop sides from {len(rows)} observations)")


if __name__ == "__main__":
    main()
