"""Player-prop line shopping — the same product, narrower markets.

Props are where books disagree most. A strikeout total or a receiving-yards
line moves on injury news and lineup churn faster than any book can repost
every number, so the spread between the best and worst quote on the same prop
is routinely wider than on the game lines. Same arithmetic as engine.lines:
best available price per side, de-vigged median consensus as the fair line.

Comparing prices only makes sense at the SAME line, so props are grouped by
(event, market, player, line). Books quoting a different line for the same
player land in a different group. A group needs quotes from 3+ books on both
sides before we publish a consensus for it — fewer books than that is a price
list, not a market.

Credits: the events list is free; each event's prop odds cost
(markets x regions) credits. This module never exceeds --max-credits and
records what the API says we have left, because props share one monthly
budget with the game board.

    python -m engine.props --window-hours 30 --max-credits 20
    python -m engine.props --dry-run
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .lines import API, REGIONS, implied, to_american, load_key, active_sports
from .schema import canonical_book

# Markets per sport, in priority order. Keys are The Odds API market keys.
PROP_MARKETS = {
    "americanfootball_nfl": {
        "label": "NFL", "slug": "nfl",
        "markets": {
            "player_pass_yds": "Passing yards",
            "player_rush_yds": "Rushing yards",
            "player_receptions": "Receptions",
        },
    },
    "baseball_mlb": {
        "label": "MLB", "slug": "mlb",
        "markets": {
            "pitcher_strikeouts": "Pitcher strikeouts",
            "batter_total_bases": "Total bases",
            "batter_hits": "Hits",
        },
    },
    "basketball_nba": {
        "label": "NBA", "slug": "nba",
        "markets": {
            "player_points": "Points",
            "player_rebounds": "Rebounds",
            "player_assists": "Assists",
        },
    },
    "icehockey_nhl": {
        "label": "NHL", "slug": "nhl",
        "markets": {
            "player_shots_on_goal": "Shots on goal",
            "player_points": "Points",
        },
    },
}

MIN_BOOKS = 3          # fewer than this per side -> no consensus, not shown


def upcoming_events(sport_key: str, key: str, session: requests.Session,
                    window: timedelta, now: datetime) -> list[dict]:
    """Events starting inside the window. This endpoint is free."""
    r = session.get(f"{API}/sports/{sport_key}/events",
                    params={"apiKey": key}, timeout=25)
    if r.status_code != 200:
        return []
    out = []
    for g in r.json():
        try:
            starts = datetime.fromisoformat(
                g["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if now <= starts <= now + window:
            out.append(g)
    out.sort(key=lambda g: g["commence_time"])
    return out


def _event_props(sport_key: str, event: dict, key: str,
                 session: requests.Session,
                 market_labels: dict[str, str]) -> tuple[list[dict], int, int]:
    """Fetch prop odds for one event. Returns (props, spent, remaining)."""
    r = session.get(
        f"{API}/sports/{sport_key}/events/{event['id']}/odds",
        params={"apiKey": key, "regions": REGIONS,
                "markets": ",".join(market_labels), "oddsFormat": "american"},
        timeout=35)
    spent = int(r.headers.get("x-requests-last", 0) or 0)
    remaining = int(float(r.headers.get("x-requests-remaining", -1) or -1))
    if r.status_code != 200:
        return [], spent, remaining

    g = r.json()
    # (market, player, line) -> {"Over": [quotes], "Under": [quotes]}
    groups: dict[tuple, dict[str, list[dict]]] = {}
    for b in g.get("bookmakers", []):
        book = canonical_book(b.get("key", "?"))
        for m in b.get("markets", []):
            mkey = m.get("key")
            if mkey not in market_labels:
                continue
            for o in m.get("outcomes", []):
                side = o.get("name")            # "Over" / "Under"
                player = o.get("description")   # player name
                line = o.get("point")
                price = o.get("price")
                if side not in ("Over", "Under") or not player \
                        or line is None or price is None:
                    continue
                grp = groups.setdefault((mkey, player, float(line)),
                                        {"Over": [], "Under": []})
                grp[side].append({"book": book, "price": int(price)})

    props = []
    for (mkey, player, line), sides in groups.items():
        if any(len(qs) < MIN_BOOKS for qs in sides.values()):
            continue
        med = {s: statistics.median([implied(q["price"]) for q in qs])
               for s, qs in sides.items()}
        total = sum(med.values())
        if total <= 0:
            continue
        fair = {s: p / total for s, p in med.items()}

        rendered = {}
        for s, qs in sides.items():
            ranked = sorted(qs, key=lambda q: implied(q["price"]))
            best, worst = ranked[0], ranked[-1]
            fp = fair[s]
            rendered[s.lower()] = {
                "best_price": best["price"], "best_book": best["book"],
                "worst_price": worst["price"], "n_books": len(ranked),
                "gain_pts": round(
                    (implied(worst["price"]) - implied(best["price"])) * 100, 2),
                "fair_price": to_american(fp),
                "edge_vs_fair_pts": round((fp - implied(best["price"])) * 100, 2),
            }
        props.append({
            "market": mkey, "market_label": market_labels[mkey],
            "player": player, "line": line,
            "over": rendered["over"], "under": rendered["under"],
            "gain_pts": max(rendered["over"]["gain_pts"],
                            rendered["under"]["gain_pts"]),
        })
    props.sort(key=lambda p: -p["gain_pts"])
    return props, spent, remaining


def collect(window_hours: float = 30, max_credits: int = 20,
            out_dir: Path | str = "site/public/data",
            dry_run: bool = False) -> dict[str, Any]:
    key = load_key()
    session = requests.Session()
    now = datetime.now(timezone.utc)
    window = timedelta(hours=window_hours)

    live = active_sports(key, session)   # free
    spent = 0
    remaining = -1
    boards = []

    for sport_key, meta in PROP_MARKETS.items():
        if sport_key not in live:
            continue
        cost_per_event = len(meta["markets"])   # x 1 region
        events = upcoming_events(sport_key, key, session, window, now)
        rows = []
        empties = 0
        for ev in events:
            if spent + cost_per_event > max_credits:
                break
            if empties >= 2:
                # Books aren't posting props for this sport right now
                # (off-season, preseason). Stop paying to confirm it.
                break
            props, used, rem = _event_props(
                sport_key, ev, key, session, meta["markets"])
            spent += used
            if rem >= 0:
                remaining = rem
            if not props:
                empties += 1
                continue
            empties = 0
            rows.append({
                "id": ev["id"], "home": ev.get("home_team", ""),
                "away": ev.get("away_team", ""),
                "starts": ev["commence_time"], "props": props,
            })
        if rows:
            gains = [p["gain_pts"] for e in rows for p in e["props"]]
            boards.append({
                "sport": meta["slug"], "label": meta["label"],
                "n_events": len(rows),
                "n_props": sum(len(e["props"]) for e in rows),
                "avg_gain_pts": round(sum(gains) / len(gains), 2),
                "max_gain_pts": round(max(gains), 2),
                "events": rows,
            })

    doc = {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "credits_spent": spent,
        "credits_remaining": remaining,
        "note": ("Same-line player props only: best available price per side "
                 "and the de-vigged median consensus across books. A prop "
                 "needs 3+ books on both sides to appear."),
        "boards": boards,
        "totals": {
            "events": sum(b["n_events"] for b in boards),
            "props": sum(b["n_props"] for b in boards),
            "max_gain_pts": max((b["max_gain_pts"] for b in boards), default=0),
        },
    }

    if not dry_run:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        out = d / "props.json"
        if not boards and out.exists():
            # Books have pulled the slate (overnight, between slates). Keep the
            # last posted lines on the board as a labelled closing snapshot
            # rather than publishing an empty page; just record that we looked.
            try:
                prev = json.loads(out.read_text())
                if prev.get("totals", {}).get("props"):
                    prev["checked_at"] = now.isoformat()
                    prev["credits_remaining"] = remaining
                    out.write_text(json.dumps(prev, indent=1))
                    doc["kept_previous"] = True
                    return doc
            except (json.JSONDecodeError, OSError):
                pass
        (d / "props.json").write_text(json.dumps(doc, indent=1))

        # Append-only raw capture, one file per sport per UTC day, same shape
        # as the game-line capture so future backtests can replay both.
        stamp = now.strftime("%Y-%m-%d")
        for board in boards:
            cap = Path("data/capture") / f"{board['sport']}-props"
            cap.mkdir(parents=True, exist_ok=True)
            with (cap / f"{stamp}.jsonl").open("a") as fh:
                for e in board["events"]:
                    for p in e["props"]:
                        fh.write(json.dumps({
                            "observed_at": now.isoformat(),
                            "event_id": e["id"], "sport": board["sport"],
                            "kickoff": e["starts"],
                            "home": e["home"], "away": e["away"],
                            "market": p["market"], "player": p["player"],
                            "line": p["line"],
                            "over": p["over"], "under": p["under"],
                            "provenance": "own_capture",
                        }, separators=(",", ":"), sort_keys=True) + "\n")
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=float, default=30)
    ap.add_argument("--max-credits", type=int, default=20)
    ap.add_argument("--out", default="site/public/data")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = collect(a.window_hours, a.max_credits, a.out, a.dry_run)
    print(f"credits spent     : {d['credits_spent']}")
    print(f"credits remaining : {d['credits_remaining']}")
    print(f"events            : {d['totals']['events']}")
    print(f"props published   : {d['totals']['props']}")
    for b in d["boards"]:
        print(f"  {b['label']:<5} {b['n_events']:>2} events  "
              f"{b['n_props']:>3} props  avg {b['avg_gain_pts']:>5} pts  "
              f"max {b['max_gain_pts']:>5}")


if __name__ == "__main__":
    main()
