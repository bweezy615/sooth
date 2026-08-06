"""Multi-sport line shopping — the product.

Books disagree on what a game is worth. Taking the best available number is
positive expected value on its own arithmetic, regardless of whether anyone's
pick is any good. That is what this module computes, and it is the one edge we
can offer honestly.

Two numbers per side:

  best price   the most generous quote we can find, and which book has it
  fair price   the de-vigged consensus across every book

The fair price is the load-bearing one, and it is why this is not just a price
comparison. A single book's line includes its margin, so it always understates
your chances. Removing the vig and taking the MEDIAN across books gives a
number no single operator can skew — that is the line we ask people to trust,
and it is computed the same way sharp bettors do it.

Median, not mean: one book posting a stale or fat-fingered price should not
move the consensus, and near kickoff that happens constantly.

Credits: each sport costs (number of markets) credits per call. We fetch only
sports that have a game starting inside the window, and the sports catalogue
call itself is free, so an idle night costs nothing.

    python -m engine.lines --window-hours 36
    python -m engine.lines --window-hours 36 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .schema import canonical_book

API = "https://api.the-odds-api.com/v4"
MARKETS = "h2h"           # 1 credit per sport per call
REGIONS = "us"

# NFL is the priority; the rest fill the calendar so the board is never empty.
SPORTS = {
    "americanfootball_nfl": {"label": "NFL", "slug": "nfl"},
    "baseball_mlb":         {"label": "MLB", "slug": "mlb"},
    "icehockey_nhl":        {"label": "NHL", "slug": "nhl"},
    "basketball_nba":       {"label": "NBA", "slug": "nba"},
    "mma_mixed_martial_arts": {"label": "UFC", "slug": "ufc"},
}

BOOK_NAMES = {
    "betus": "BetUS", "betrivers": "BetRivers", "draftkings": "DraftKings",
    "fanduel": "FanDuel", "bovada": "Bovada", "betmgm": "BetMGM",
    "lowvig": "LowVig", "betonlineag": "BetOnline", "mybookieag": "MyBookie",
    "williamhill_us": "Caesars", "espnbet": "ESPN BET", "fanatics": "Fanatics",
}


def load_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if key:
        return key
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ODDS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("ODDS_API_KEY not found")


def implied(price: int) -> float:
    """American odds -> implied probability, vig included."""
    return (-price) / ((-price) + 100.0) if price < 0 else 100.0 / (price + 100.0)


def to_american(prob: float) -> int:
    if not 0.0 < prob < 1.0:
        raise ValueError(f"probability out of range: {prob}")
    if prob > 0.5:
        return int(round(-100.0 * prob / (1.0 - prob)))
    return int(round(100.0 * (1.0 - prob) / prob))


def active_sports(key: str, session: requests.Session) -> set[str]:
    """Which sports are in season. This call is free."""
    r = session.get(f"{API}/sports/", params={"apiKey": key}, timeout=25)
    r.raise_for_status()
    return {s["key"] for s in r.json() if s.get("active")}


def _fair_prices(quotes: dict[str, list[dict]]) -> dict[str, float]:
    """De-vigged consensus probability per side.

    Take the median implied probability per side across books, then normalise
    so the sides sum to 1. The normalisation is what removes the margin: raw
    implied probabilities always sum to more than 1, and the excess is the vig.
    """
    med = {side: statistics.median([implied(q["price"]) for q in qs])
           for side, qs in quotes.items() if qs}
    total = sum(med.values())
    if not med or total <= 0:
        return {}
    return {side: p / total for side, p in med.items()}


def _one_sport(sport_key: str, key: str, session: requests.Session,
               window: timedelta, now: datetime) -> tuple[list[dict], int]:
    """Return (events, credits_spent) for one sport."""
    r = session.get(f"{API}/sports/{sport_key}/odds", params={
        "apiKey": key, "regions": REGIONS, "markets": MARKETS,
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
        quotes: dict[str, list[dict]] = {}
        for b in g.get("bookmakers", []):
            for m in b.get("markets", []):
                if m.get("key") != "h2h":
                    continue
                for o in m.get("outcomes", []):
                    name, price = o.get("name"), o.get("price")
                    if name is None or price is None:
                        continue
                    quotes.setdefault(name, []).append(
                        {"book": b.get("key", "?"), "price": int(price)})

        if len(quotes) < 2:
            continue
        fair = _fair_prices(quotes)
        if not fair:
            continue

        sides = []
        for name, qs in quotes.items():
            # BEST for a bettor = LOWEST implied probability (least juice).
            ranked = sorted(qs, key=lambda q: implied(q["price"]))
            best, worst = ranked[0], ranked[-1]
            gain = round((implied(worst["price"]) - implied(best["price"])) * 100, 2)
            assert gain >= 0, f"gain must be non-negative, got {gain}"
            fp = fair.get(name)
            sides.append({
                "name": name,
                "quotes": ranked,
                "best_price": best["price"],
                "best_book": canonical_book(best["book"]),
                "worst_price": worst["price"],
                "worst_book": canonical_book(worst["book"]),
                "n_books": len(ranked),
                "gain_pts": gain,
                "fair_prob": round(fp, 4) if fp else None,
                "fair_price": to_american(fp) if fp else None,
                # Positive when the best available price pays MORE than fair.
                "edge_vs_fair_pts": (
                    round((fp - implied(best["price"])) * 100, 2) if fp else None),
            })

        out.append({
            "id": g.get("id", ""), "home": home, "away": away,
            "starts": g["commence_time"],
            "sides": sorted(sides, key=lambda s: -(s["gain_pts"] or 0)),
            "max_gain_pts": max((s["gain_pts"] for s in sides), default=0),
            "n_books": max((s["n_books"] for s in sides), default=0),
        })
    return out, spent



def _capture_rows(sport_slug: str, events: list[dict], observed_at: str) -> list[dict]:
    """Every individual book quote, in the capture schema.

    engine/lines.py already pays for these quotes to build the board; it was
    discarding everything except the summary. Persisting them costs no extra
    credits and unlocks two things at once: divergence alerts, which need at
    least three books to have a consensus worth diverging from, and multi-book
    closing-line value, which until now had a single book behind it.

    Written with provenance ``own_capture`` because we did observe these
    ourselves, at ``observed_at``, and paid for the observation.
    """
    rows = []
    for e in events:
        for side in e.get("sides", []):
            for q in side.get("quotes", []):
                rows.append({
                    "observed_at": observed_at,
                    "event_id": e.get("id", ""),
                    "sport": sport_slug,
                    "season": None,
                    "week": None,
                    "kickoff": e.get("starts", ""),
                    "home": e.get("home", ""),
                    "away": e.get("away", ""),
                    "book": canonical_book(q.get("book", "")),
                    "market": "moneyline",
                    "selection": side.get("name", ""),
                    "line": None,
                    "price": q.get("price"),
                    "provenance": "own_capture",
                })
    return rows


def collect(window_hours: float = 36, max_credits: int = 60,
            out_dir: Path | str = "site/public/data",
            dry_run: bool = False) -> dict[str, Any]:
    key = load_key()
    session = requests.Session()
    now = datetime.now(timezone.utc)
    window = timedelta(hours=window_hours)

    live = active_sports(key, session)   # free call
    spent = 0
    boards = []

    for sport_key, meta in SPORTS.items():
        if sport_key not in live:
            continue
        if spent + len(MARKETS.split(",")) > max_credits:
            break
        events, used = _one_sport(sport_key, key, session, window, now)
        spent += used
        if not events:
            continue
        events.sort(key=lambda e: -e["max_gain_pts"])
        gains = [s["gain_pts"] for e in events for s in e["sides"]]
        boards.append({
            "sport": meta["slug"], "label": meta["label"],
            "n_events": len(events),
            "avg_gain_pts": round(sum(gains) / len(gains), 2) if gains else 0,
            "max_gain_pts": round(max(gains), 2) if gains else 0,
            "n_books": max((e["n_books"] for e in events), default=0),
            "events": events,
        })

    doc = {
        "generated_at": now.isoformat(),
        "window_hours": window_hours,
        "credits_spent": spent,
        "sports_live": sorted(SPORTS[s]["label"] for s in live if s in SPORTS),
        "note": ("Best available price per side, and the de-vigged consensus "
                 "across books. Shopping the best number is +EV on its own."),
        "boards": boards,
        "totals": {
            "events": sum(b["n_events"] for b in boards),
            "avg_gain_pts": (
                round(sum(b["avg_gain_pts"] * b["n_events"] for b in boards)
                      / max(sum(b["n_events"] for b in boards), 1), 2)),
            "max_gain_pts": max((b["max_gain_pts"] for b in boards), default=0),
        },
    }

    all_failed = spent == 0 and not boards and bool(live)
    doc["all_fetches_failed"] = all_failed
    if not dry_run:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        out = d / "board.json"
        if all_failed and out.exists():
            # Every sport call failed (API outage, bad key): a blank board is
            # worse than yesterday's board with an honest checked_at stamp.
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

        # Append-only capture, never rewritten. One file per sport per UTC day.
        stamp = now.strftime("%Y-%m-%d")
        for board in boards:
            rows = _capture_rows(board["sport"], board["events"], now.isoformat())
            if not rows:
                continue
            cap = Path("data/capture") / board["sport"]
            cap.mkdir(parents=True, exist_ok=True)
            # One buffered write per batch: two launchd jobs append to the
            # same day-file, and interleaved partial lines corrupt evidence.
            blob = "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n"
                           for r in rows)
            with (cap / f"{stamp}.jsonl").open("a") as fh:
                fh.write(blob)
            doc.setdefault("captured", {})[board["sport"]] = len(rows)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=float, default=36)
    ap.add_argument("--max-credits", type=int, default=60)
    ap.add_argument("--out", default="site/public/data")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = collect(a.window_hours, a.max_credits, a.out, a.dry_run)
    print(f"credits spent : {d['credits_spent']}")
    print(f"sports live   : {', '.join(d['sports_live']) or 'none'}")
    print(f"events        : {d['totals']['events']}")
    print(f"avg gain      : {d['totals']['avg_gain_pts']} pts")
    for b in d["boards"]:
        print(f"  {b['label']:<5} {b['n_events']:>3} events  "
              f"avg {b['avg_gain_pts']:>5} pts  max {b['max_gain_pts']:>5}  "
              f"{b['n_books']} books")


if __name__ == "__main__":
    main()
