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
REGIONS = "us"

# The Odds API bills one credit per market per sport per call, so the market
# list is a per-sport decision, not a global one.
#
# Moneyline alone is close to useless for college football and always was. The
# sport's defining feature is the mismatch: on 2026-09-03 the board carried
# Miami at Stanford priced -3000/+1500, UMass at Rutgers, Bethune-Cookman at
# UCF. Shopping a -3000 moneyline moves a bettor's implied probability by a
# fraction of a point and no one bets those games that way — they bet the
# number. A CFB board without spreads is a board about the wrong market.
#
# Football therefore buys all three markets and the rest stay on moneyline.
# That is 9 credits per run rather than 5. Measured burn over the cycle that
# opened 2026-09-01 was ~120 credits/day against a 20,000/month pool, so the
# increase lands near 260/day (~8k/month) with room to spare, and
# --max-credits still bounds any single run.
DEFAULT_MARKETS = ("h2h",)
LINE_MARKETS = ("h2h", "spreads", "totals")

# NFL is the priority; the rest fill the calendar so the board is never empty.
# How many future games to carry for a sport with nothing inside the window,
# so a season that has not started yet is still browsable. Small on purpose:
# this is "the season is coming and here is what it is priced at", not a
# schedule dump.
LOOKAHEAD_EVENTS = 8

# Branden's call, 2026-08-27: college football replaces UFC rather than being
# added alongside it. Both this module and engine/middles.py iterate this dict
# and pay per sport, so a swap is credit-neutral where a sixth entry would not
# have been. UFC capture history stays on disk under data/capture/ufc/ - we
# stopped publishing it, we did not delete it.
SPORTS = {
    "americanfootball_nfl":   {"label": "NFL", "slug": "nfl",
                               "markets": LINE_MARKETS},
    "americanfootball_ncaaf": {"label": "CFB", "slug": "ncaaf",
                               "markets": LINE_MARKETS},
    "baseball_mlb":           {"label": "MLB", "slug": "mlb"},
    "icehockey_nhl":          {"label": "NHL", "slug": "nhl"},
    "basketball_nba":         {"label": "NBA", "slug": "nba"},
}


def markets_for(meta: dict[str, Any]) -> tuple[str, ...]:
    """Markets to buy for one sport. Absent key means moneyline only."""
    return tuple(meta.get("markets") or DEFAULT_MARKETS)

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


def _key_line(point: float) -> float:
    """A book's number, rounded to a value that compares equal across books.

    Books post halves and the occasional quarter. Raw floats out of JSON do
    not group reliably (-7.0 and -6.999999 are the same number to a bettor and
    different keys to a dict), and a consensus computed on ungrouped floats
    silently splits one line into several one-book lines.
    """
    return round(float(point), 2)


def _consensus_line(quotes: list[dict]) -> float | None:
    """The number the market is actually on, as one side posts it.

    The MODE, not the median. Half the books on -7 and half on -7.5 has a
    median of -7.25, which is a line no book offers and no one can bet. The
    mode is always a real, shoppable number. Ties break toward the line more
    books can be compared at, then toward the bettor-friendlier number so the
    tiebreak can never quietly pick the worse of two equally-common lines.
    """
    if not quotes:
        return None
    counts: dict[float, int] = {}
    for q in quotes:
        counts[q["line"]] = counts.get(q["line"], 0) + 1
    return max(counts, key=lambda ln: (counts[ln], ln))


def _line_side(name: str, line: float, quotes: list[dict],
               better_is_higher: bool) -> dict:
    """One side of a line market: price shopping AT the consensus number,
    plus the best number available anywhere.

    These are two genuinely different edges and the board states both rather
    than blending them, because they cannot be compared without a model of
    where the game lands. Taking -105 instead of -115 on the same spread is a
    strictly better version of the same bet. Taking +7.5 where the market is
    +7 is a DIFFERENT bet — better whenever the game lands on 7 and identical
    otherwise. Collapsing the two into one "best" number would be inventing a
    cross-line equivalence we have no basis for, which is exactly the kind of
    claim this project does not make.
    """
    at_line = [q for q in quotes if q["line"] == line]
    ranked = sorted(at_line, key=lambda q: implied(q["price"]))
    out: dict[str, Any] = {
        "name": name,
        "line": line,
        "quotes": ranked,
        "n_books": len(ranked),
    }
    if ranked:
        best, worst = ranked[0], ranked[-1]
        gain = round((implied(worst["price"]) - implied(best["price"])) * 100, 2)
        assert gain >= 0, f"gain must be non-negative, got {gain}"
        out.update({
            "best_price": best["price"],
            "best_book": canonical_book(best["book"]),
            "worst_price": worst["price"],
            "worst_book": canonical_book(worst["book"]),
            "gain_pts": gain,
        })

    # The best NUMBER on offer, whatever it costs. For a spread, and for an
    # Under, a higher line is the friendlier one; for an Over, a lower one is.
    if quotes:
        pick = (max if better_is_higher else min)(
            quotes, key=lambda q: (q["line"], -implied(q["price"])))
        out["best_line"] = pick["line"]
        out["best_line_price"] = pick["price"]
        out["best_line_book"] = canonical_book(pick["book"])
        out["off_consensus"] = pick["line"] != line
    return out


def _line_market(kind: str, sides: dict[str, list[dict]],
                 better_is_higher: dict[str, bool]) -> dict | None:
    """Assemble one spread or total market for one event.

    The consensus number is taken from a single named side and the opposite
    side is read at the number that pairs with it, so the two halves always
    describe the same bet. Deriving each side's consensus independently would
    let a total publish Over 44.5 beside Under 45.5 — two different markets
    presented as one, and a de-vig across them would be meaningless.
    """
    if len(sides) != 2 or not all(sides.values()):
        return None
    first, second = list(sides)
    line = _consensus_line(sides[first])
    if line is None:
        return None
    # Spread: the sides are mirrored (home -7 pairs with away +7).
    # Total: both sides quote the same number.
    other = -line if kind == "spread" else line

    built = [_line_side(first, line, sides[first], better_is_higher[first]),
             _line_side(second, other, sides[second], better_is_higher[second])]
    if not all(s["n_books"] for s in built):
        return None

    fair = _fair_prices({s["name"]: s["quotes"] for s in built})
    for s in built:
        fp = fair.get(s["name"])
        s["fair_prob"] = round(fp, 4) if fp else None
        s["fair_price"] = to_american(fp) if fp else None
        s["edge_vs_fair_pts"] = (
            round((fp - implied(s["best_price"])) * 100, 2) if fp else None)

    return {
        "market": kind,
        "consensus_line": line,
        "n_books": max(s["n_books"] for s in built),
        "max_gain_pts": max(s.get("gain_pts", 0) for s in built),
        "sides": built,
    }


def _balance(headers) -> tuple[int, int]:
    """Account balance from a response we already paid for.

    `x-requests-remaining` rides along on every odds call, so recording it
    costs nothing extra. `x-requests-used` comes with it, and the pair matters
    more than either half: remaining alone cannot tell you the plan size, so it
    cannot tell you whether a falling balance is a month draining or a pool
    that never refills. remaining + used can. Missing headers read as -1 rather
    than 0, so "not reported" can never be mistaken for "empty".
    """
    def _n(name: str) -> int:
        try:
            return int(float(headers.get(name, -1) or -1))
        except (TypeError, ValueError):
            return -1
    return _n("x-requests-remaining"), _n("x-requests-used")


def _one_sport(sport_key: str, key: str, session: requests.Session,
               window: timedelta, now: datetime,
               markets: tuple[str, ...] = DEFAULT_MARKETS,
               ) -> tuple[list[dict], int, tuple[int, int]]:
    """Return (events, credits_spent, (balance_remaining, balance_used))."""
    r = session.get(f"{API}/sports/{sport_key}/odds", params={
        "apiKey": key, "regions": REGIONS, "markets": ",".join(markets),
        "oddsFormat": "american"}, timeout=35)
    spent = int(r.headers.get("x-requests-last", 0) or 0)
    balance = _balance(r.headers)
    if r.status_code != 200:
        return [], spent, balance

    out = []
    for g in r.json():
        try:
            starts = datetime.fromisoformat(
                g["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if starts < now:
            continue

        home, away = g.get("home_team", ""), g.get("away_team", "")
        quotes: dict[str, list[dict]] = {}
        spread: dict[str, list[dict]] = {}
        total: dict[str, list[dict]] = {}
        for b in g.get("bookmakers", []):
            book = b.get("key", "?")
            for m in b.get("markets", []):
                mkey = m.get("key")
                for o in m.get("outcomes", []):
                    name, price = o.get("name"), o.get("price")
                    if name is None or price is None:
                        continue
                    if mkey == "h2h":
                        quotes.setdefault(name, []).append(
                            {"book": book, "price": int(price)})
                        continue
                    point = o.get("point")
                    if point is None:
                        continue
                    q = {"book": book, "line": _key_line(point),
                         "price": int(price)}
                    if mkey == "spreads":
                        spread.setdefault(name, []).append(q)
                    elif mkey == "totals":
                        total.setdefault(name, []).append(q)

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

        # Spread and total ride alongside the moneyline rather than replacing
        # it. `sides` is the published contract a dozen readers already parse
        # (the desk, the game page, alerts, the X cards), and a sport we buy
        # only h2h for has no line markets at all, so `markets` is additive
        # and absent rather than empty when there is nothing to say.
        built = []
        if spread:
            m = _line_market(
                "spread",
                {home: spread.get(home, []), away: spread.get(away, [])},
                {home: True, away: True})
            if m:
                built.append(m)
        if total:
            m = _line_market(
                "total",
                {"Over": total.get("Over", []), "Under": total.get("Under", [])},
                {"Over": False, "Under": True})
            if m:
                built.append(m)

        event = {
            "id": g.get("id", ""), "home": home, "away": away,
            "starts": g["commence_time"],
            "in_window": starts <= now + window,
            "sides": sorted(sides, key=lambda s: -(s["gain_pts"] or 0)),
            "max_gain_pts": max((s["gain_pts"] for s in sides), default=0),
            "n_books": max((s["n_books"] for s in sides), default=0),
        }
        if built:
            event["markets"] = built
        out.append(event)

    chosen = _choose(out)
    return chosen, spent, balance


def _choose(events: list[dict]) -> list[dict]:
    """Which of a sport's events reach the board.

    A sport whose season has not started yet used to vanish entirely. The
    window is 36h and the NFL runs weekly, so on 2026-08-22 the next NFL
    kickoff was 430 hours out, the NHL 907 and the NBA 1409 — three of the five
    sports we cover were dark, and the phone's sport rail had nothing to offer
    for any of them.

    The odds request is not time-filtered (it returns the sport's whole
    schedule and we filter here), so carrying the soonest few games for a thin
    sport costs NOTHING extra in credits. Books post Week 1 prices months ahead
    and they are genuinely shoppable — comparing them is exactly what this
    board is for.

    The look-ahead used to be all-or-nothing: any in-window game at all
    suppressed it completely. That fails precisely at a season opening, where
    the first game to come inside 36h is the *only* one. Measured on
    2026-08-28, the eve of college football week 1: our own capture held 107
    CFB events and the API listed the whole slate, one of them (UNC at TCU) was
    33 hours out, and the board therefore published exactly one college
    football game while the sport rail read "CFB 1". The day before, with none
    in window, it had published eight.

    So the look-ahead tops the board up to LOOKAHEAD_EVENTS instead of
    replacing it. In-window games still come first and are never displaced;
    every card carries its own kickoff time and an ``upcoming`` flag, so "18
    days out" is never presented as "tonight".
    """
    live_now = [e for e in events if e.get("in_window")]
    chosen = list(live_now)
    if len(chosen) < LOOKAHEAD_EVENTS:
        have = {id(e) for e in chosen}
        for e in sorted(events, key=lambda e: e["starts"]):
            if len(chosen) >= LOOKAHEAD_EVENTS:
                break
            if id(e) not in have:
                chosen.append(e)
    for e in chosen:
        e["upcoming"] = not e.get("in_window", False)
    for e in events:
        e.pop("in_window", None)
    return chosen



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
    bal = (-1, -1)
    boards = []

    for sport_key, meta in SPORTS.items():
        if sport_key not in live:
            continue
        markets = markets_for(meta)
        if spent + len(markets) > max_credits:
            break
        events, used, balance = _one_sport(
            sport_key, key, session, window, now, markets)
        spent += used
        if balance[0] >= 0:
            bal = balance
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
        "credits_remaining": bal[0],
        "credits_used": bal[1],
        # What we actually published a board for, not what the API lists as
        # active. The API counts a sport as active whenever any market exists
        # (NBA and NHL futures trade all summer), so this read
        # "MLB, NBA, NFL, NHL, UFC" on 2026-08-11 while the file carried
        # boards for MLB and UFC alone — and engine.html renders it verbatim
        # as "sports live", board.html as "in season". Derive the claim from
        # the evidence and it cannot drift from it.
        "sports_live": sorted(b["label"] for b in boards),
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
    if d["credits_remaining"] >= 0:
        print(f"credits left  : {d['credits_remaining']} "
              f"(of {d['credits_remaining'] + d['credits_used']} this cycle)")
    print(f"sports live   : {', '.join(d['sports_live']) or 'none'}")
    print(f"events        : {d['totals']['events']}")
    print(f"avg gain      : {d['totals']['avg_gain_pts']} pts")
    for b in d["boards"]:
        print(f"  {b['label']:<5} {b['n_events']:>3} events  "
              f"avg {b['avg_gain_pts']:>5} pts  max {b['max_gain_pts']:>5}  "
              f"{b['n_books']} books")


if __name__ == "__main__":
    main()
