"""Middles — two books, two lines, and daylight between them.

A middle is the one structurally safe disagreement in this business: when one
book posts Over 44.5 and another posts Under 46.5, betting both wins BOTH bets
if the game lands 45 or 46, and loses only one side's vig otherwise. Small
risk, occasional double win. Same shape for spreads: Home -2.5 at one book,
Away +4.5 at another, and 3 or 4 wins twice.

Books drift apart on lines the same way they drift apart on prices — injury
news, sharp action on one side, a slow trader. This module reads spreads and
totals for every live sport in one bulk call each (2 credits per sport, not
per event) and reports every window where the lines genuinely overlap, plus
how many whole numbers land inside it.

No prediction here either: a middle is an observation about book disagreement,
priced at whatever the two best quotes are.

    python -m engine.middles --window-hours 36
    python -m engine.middles --dry-run
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .lines import API, REGIONS, SPORTS, load_key, active_sports
from .schema import canonical_book


def _windows(low_quotes: list[dict], high_quotes: list[dict]) -> dict | None:
    """Best middle window between two sides of a line market.

    low_quotes:  bets that win when the result lands ABOVE their line
                 (Over L, or Away +L covering when margin < L).
    high_quotes: bets that win when the result lands BELOW their line.
    The widest window is (lowest low-line, highest high-line).
    """
    if not low_quotes or not high_quotes:
        return None
    lo = min(low_quotes, key=lambda q: q["line"])
    hi = max(high_quotes, key=lambda q: q["line"])
    if hi["line"] <= lo["line"]:
        return None
    # floor/ceil, not int(): int() truncates toward zero, which for negative
    # half-point lines (home underdogs) skips real landing numbers entirely.
    inside = [n for n in range(math.floor(lo["line"]) + 1,
                               math.ceil(hi["line"]))
              if lo["line"] < n < hi["line"]]
    if not inside:
        return None
    return {
        "low_line": lo["line"], "low_price": lo["price"], "low_book": lo["book"],
        "high_line": hi["line"], "high_price": hi["price"], "high_book": hi["book"],
        "width": round(hi["line"] - lo["line"], 1),
        "numbers": inside,
    }


def _one_sport(sport_key: str, key: str, session: requests.Session,
               window: timedelta, now: datetime) -> tuple[list[dict], int]:
    r = session.get(f"{API}/sports/{sport_key}/odds", params={
        "apiKey": key, "regions": REGIONS, "markets": "spreads,totals",
        "oddsFormat": "american"}, timeout=35)
    spent = int(r.headers.get("x-requests-last", 0) or 0)
    if r.status_code != 200:
        return [], spent

    out = []
    for g in r.json():
        try:
            starts = datetime.fromisoformat(
                g["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if not (now <= starts <= now + window):
            continue
        home, away = g.get("home_team", ""), g.get("away_team", "")

        tot_over, tot_under = [], []
        sp_away_plus, sp_home_fav = [], []
        for b in g.get("bookmakers", []):
            book = canonical_book(b.get("key", "?"))
            for m in b.get("markets", []):
                for o in m.get("outcomes", []):
                    line, price = o.get("point"), o.get("price")
                    if line is None or price is None:
                        continue
                    q = {"book": book, "line": float(line), "price": int(price)}
                    if m.get("key") == "totals":
                        (tot_over if o.get("name") == "Over" else tot_under).append(q)
                    elif m.get("key") == "spreads":
                        # Normalise to the home-margin axis: home -h wins when
                        # margin > h; away +h' wins when margin < h'.
                        if o.get("name") == home:
                            sp_home_fav.append({**q, "line": -q["line"]})
                        elif o.get("name") == away:
                            sp_away_plus.append(q)

        found = []
        w = _windows(tot_over, tot_under)
        if w:
            found.append({"market": "total",
                          "low_label": f"Over {w['low_line']}",
                          "high_label": f"Under {w['high_line']}", **w})
        w = _windows(sp_home_fav, sp_away_plus)
        if w:
            # A margin of 0 is a tie; only NFL results can actually land there.
            if sport_key != "americanfootball_nfl":
                w["numbers"] = [n for n in w["numbers"] if n != 0]
            if w["numbers"]:
                found.append({"market": "spread",
                              "low_label": f"{home} {-w['low_line']:+g}",
                              "high_label": f"{away} {w['high_line']:+g}", **w})
        for f in found:
            out.append({
                "id": g.get("id", ""), "home": home, "away": away,
                "starts": g["commence_time"], **f,
            })
    return out, spent


def collect(window_hours: float = 36,
            out_dir: Path | str = "site/public/data",
            dry_run: bool = False) -> dict[str, Any]:
    key = load_key()
    session = requests.Session()
    now = datetime.now(timezone.utc)
    window = timedelta(hours=window_hours)
    live = active_sports(key, session)   # free

    spent = 0
    middles = []
    for sport_key, meta in SPORTS.items():
        if sport_key not in live:
            continue
        rows, used = _one_sport(sport_key, key, session, window, now)
        spent += used
        for r in rows:
            r["sport"] = meta["slug"]
            r["label"] = meta["label"]
        middles.extend(rows)

    middles.sort(key=lambda m: (-len(m["numbers"]), -m["width"]))
    doc = {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "credits_spent": spent,
        "note": ("Line windows where one book's Over/favorite line sits below "
                 "another book's Under/dog line. Landing on a number inside "
                 "the window wins both sides."),
        "middles": middles,
        "totals": {"middles": len(middles)},
    }
    doc["all_fetches_failed"] = spent == 0 and not middles and bool(live)
    if not dry_run:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        out = d / "middles.json"
        if doc["all_fetches_failed"] and out.exists():
            # API trouble, not an empty market: keep the previous board.
            try:
                prev = json.loads(out.read_text())
                prev["checked_at"] = now.isoformat()
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(prev, indent=1))
                os.replace(tmp, out)
                return doc
            except (json.JSONDecodeError, OSError):
                pass
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=1))
        os.replace(tmp, out)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=float, default=36)
    ap.add_argument("--out", default="site/public/data")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = collect(a.window_hours, a.out, a.dry_run)
    print(f"credits spent : {d['credits_spent']}")
    print(f"middles found : {d['totals']['middles']}")
    for m in d["middles"][:8]:
        print(f"  {m['label']} {m['away']} @ {m['home']:<24} {m['market']:<7} "
              f"{m['low_label']} ({m['low_book']}) x {m['high_label']} "
              f"({m['high_book']})  window {m['numbers']}")


if __name__ == "__main__":
    main()
