"""NFL spread and total board, built from our own capture.

    python -m engine.nflboard
    python -m engine.nflboard --dry-run
    python -m engine.nflboard --selfcheck

WHY THIS EXISTS
---------------
``board.json`` is moneyline-only because engine/lines.py asks the Odds API for
``h2h`` — one credit per sport instead of three. But a board that shows only
moneylines is not the board anybody reads: spread and total are how football is
actually priced and discussed.

We already hold both. engine/capture.py has been logging ESPN's odds block
hourly, which carries ``pointSpread`` and ``total`` alongside the moneyline,
and it logs the ``open`` block next to the ``current`` one. So this module
spends no credits — it re-reads evidence already on disk.

TWO THINGS IT MUST NOT GET WRONG
--------------------------------
1. **Sides.** capture.py maps ``homeTeamOdds -> side_a`` and
   ``awayTeamOdds -> side_b`` (see its ``_extract``). Getting that backwards
   inverts every spread on every card that reads this feed, silently and
   plausibly. HOME_SIDE/AWAY_SIDE are named constants and _selfcheck asserts
   the mapping rather than trusting a comment.

2. **"Consensus".** ESPN publishes ONE provider, which is DraftKings. A single
   book's number is not a consensus and this feed never calls it one — every
   spread and total carries the book that quoted it. Only the moneyline, which
   engine/lines.py collects across ten books, gets a de-vigged fair price.

The open-to-current move is the interesting half: it is a real line move
measured in points of spread, which is what people actually argue about, rather
than the points of implied probability the earlier cards led with.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

from .lines import implied, to_american
from .schema import canonical_book

CAPTURE_GLOB = "data/capture/nfl/*.jsonl"
OUT = "site/public/data/nflboard.json"

# capture.py: ("homeTeamOdds", "side_a"), ("awayTeamOdds", "side_b")
HOME_SIDE, AWAY_SIDE = "side_a", "side_b"

LIVE = "own_capture"      # we observed it
OPEN = "espn_open"        # ESPN's claim about the past, labelled as such

DAYS_BACK = 8             # a game priced last week is still on the board


def _iso(s: str):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


def read_rows(days: int = DAYS_BACK, now: datetime | None = None) -> list[dict]:
    """Every capture row from the last `days` files, oldest first."""
    now = now or datetime.now(timezone.utc)
    keep = {(now - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days + 1)}
    rows = []
    for path in sorted(glob.glob(CAPTURE_GLOB)):
        if os.path.basename(path)[:-6] not in keep:
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue          # a half-written line is not a reason to stop
    rows.sort(key=lambda r: r.get("observed_at") or "")
    return rows


def game_key(r: dict) -> tuple | None:
    """Identity of a fixture, independent of who assigned the id.

    The capture file holds the SAME game under two id schemes: ESPN's numeric
    event id (which carries the spread and total) and the Odds API's hash
    (which carries the ten-book moneyline). Keyed on event_id they become two
    half-empty records — one with a spread and one book, one with no spread and
    ten. Keyed on the fixture they are one complete game.

    Date, not timestamp: the two sources disagree about kickoff by a few
    minutes (00:15 vs 00:20 on the opener). Two NFL teams do not meet twice in
    a day, so the date is identity enough.
    """
    ko = _iso(r.get("kickoff"))
    if not ko or not r.get("home") or not r.get("away"):
        return None
    return (r["home"], r["away"], ko.date().isoformat())


def build(rows: list[dict], now: datetime | None = None) -> list[dict]:
    """One record per upcoming game, with whatever markets we actually hold."""
    now = now or datetime.now(timezone.utc)

    # rows are sorted oldest-first, so a plain overwrite leaves the latest —
    # except for the open block, where the FIRST sighting is the honest one
    live: dict[tuple, dict] = {}
    series: dict[tuple, list] = {}
    opens: dict[tuple, dict] = {}
    ml_books: dict[tuple, dict] = {}
    meta: dict[tuple, dict] = {}

    for r in rows:
        gk, mk, sel = game_key(r), r.get("market"), r.get("selection")
        if not gk or not mk:
            continue
        m = meta.setdefault(gk, {"away": r.get("away"), "home": r.get("home"),
                                 "kickoff": r.get("kickoff"), "season": r.get("season"),
                                 "week": r.get("week"), "event_id": r.get("event_id")})
        # prefer ESPN's numeric id: it is the one our own capture is keyed on
        if str(r.get("event_id") or "").isdigit():
            m["event_id"] = r["event_id"]
            m["kickoff"] = r.get("kickoff") or m["kickoff"]
        prov = r.get("provenance")
        if prov == LIVE:
            live[(gk, mk, sel)] = r
            if mk == "spread" and sel == HOME_SIDE and r.get("line") is not None:
                # the home number over time. A spread series is what a line
                # move actually looks like; implied probability is the same
                # fact in a unit nobody argues in.
                series.setdefault(gk, []).append([r["observed_at"], r["line"]])
            # the multi-book moneyline rows name the team instead of a side
            if mk == "moneyline" and sel not in (HOME_SIDE, AWAY_SIDE):
                ml_books[(gk, sel, r.get("book"))] = r
        elif prov == OPEN:
            opens.setdefault((gk, mk, sel), r)

    out = []
    for gk, m in meta.items():
        ko = _iso(m.get("kickoff"))
        if not ko or ko <= now:
            continue                                   # the board is forward-looking

        game = {"event_id": m["event_id"], "away": m["away"], "home": m["home"],
                "kickoff": m["kickoff"], "season": m["season"], "week": m["week"]}

        sp_h = live.get((gk, "spread", HOME_SIDE))
        if sp_h and sp_h.get("line") is not None:
            sp_a = live.get((gk, "spread", AWAY_SIDE)) or {}
            op = opens.get((gk, "spread", HOME_SIDE)) or {}
            home_line = sp_h["line"]
            game["spread"] = {
                "book": sp_h.get("book"),
                "home": home_line,
                "away": sp_a.get("line", -home_line if home_line is not None else None),
                "home_price": sp_h.get("price"),
                "away_price": sp_a.get("price"),
                "favourite": m["home"] if home_line < 0 else m["away"],
                # the favourite's OWN number, so a card never has to work out
                # which column it is reading and flip the sign itself
                "favourite_line": home_line if home_line < 0 else -home_line,
                "open_home": op.get("line"),
                "move_pts": (round(home_line - op["line"], 1)
                             if op.get("line") is not None else None),
                "observed_at": sp_h.get("observed_at"),
                "history": _thin(series.get(gk) or []),
            }

        tot = live.get((gk, "total", "over"))
        if tot and tot.get("line") is not None:
            und = live.get((gk, "total", "under")) or {}
            op = opens.get((gk, "total", "over")) or {}
            game["total"] = {
                "book": tot.get("book"),
                "line": tot["line"],
                "over_price": tot.get("price"),
                "under_price": und.get("price"),
                "open_line": op.get("line"),
                "move_pts": (round(tot["line"] - op["line"], 1)
                             if op.get("line") is not None else None),
                "observed_at": tot.get("observed_at"),
            }

        ml = _moneyline(gk, m, ml_books, live)
        if ml:
            game["moneyline"] = ml

        META_KEYS = 6                                  # event_id..week
        if len(game) > META_KEYS:                      # any market at all
            out.append(game)

    out.sort(key=lambda g: g["kickoff"])
    return out


def _thin(points: list, cap: int = 72) -> list:
    """Keep the shape, drop the volume. Evenly spaced so the first and last
    readings — the ones the card prints as open and current — always survive."""
    if len(points) <= cap:
        return points
    step = (len(points) - 1) / (cap - 1)
    return [points[round(i * step)] for i in range(cap)]


def _moneyline(gk, m, ml_books, live) -> dict | None:
    """Best price per side plus a de-vigged fair line, when several books quote.

    Falls back to the single ESPN book so a game is not dropped for having one
    quote — but n_books tells the reader which of the two they are looking at,
    and a one-book 'fair' price would be a lie, so it is omitted below two.
    """
    sides: dict[str, list[dict]] = {}
    for (k, sel, _bk), r in ml_books.items():
        if k == gk and isinstance(r.get("price"), (int, float)):
            sides.setdefault(sel, []).append(r)
    if not sides:
        for sel, name in ((HOME_SIDE, m["home"]), (AWAY_SIDE, m["away"])):
            r = live.get((gk, "moneyline", sel))
            if r and isinstance(r.get("price"), (int, float)):
                sides.setdefault(name, []).append(r)
    if len(sides) < 2:
        return None

    out = {"n_books": max(len(v) for v in sides.values()), "sides": {}}
    fair = {}
    for name, quotes in sides.items():
        best = max(quotes, key=lambda r: r["price"] if r["price"] > 0
                   else 1.0 / abs(r["price"]))
        out["sides"][name] = {"best_price": best["price"],
                              "best_book": canonical_book(best.get("book") or ""),
                              "n_books": len(quotes)}
        fair[name] = statistics.median(implied(q["price"]) for q in quotes)

    # de-vig: scale the two medians back onto 1.0. Median first, then remove the
    # margin — one stale quote should not move the number (engine/lines.py).
    tot = sum(fair.values())
    if tot > 0 and out["n_books"] >= 2:
        for name, p in fair.items():
            out["sides"][name]["fair_prob"] = round(p / tot, 4)
            out["sides"][name]["fair_price"] = to_american(p / tot)
    return out


def publish(games: list[dict], path: str = OUT) -> dict:
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sport": "nfl",
        "source": "own_capture (ESPN odds block, hourly) — no API credits spent",
        "note": ("Spread and total are ONE book's number, named on every row: "
                 "ESPN publishes a single provider. Only the moneyline, which we "
                 "collect across several books, carries a de-vigged fair price. "
                 "Opening numbers are ESPN's claim about the past and are "
                 "labelled as such; the move is current minus open."),
        "n_games": len(games),
        "n_with_spread": sum(1 for g in games if g.get("spread")),
        "n_with_total": sum(1 for g in games if g.get("total")),
        "games": games,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=False)
        fh.write("\n")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--days", type=int, default=DAYS_BACK)
    a = ap.parse_args()
    if a.selfcheck:
        return _selfcheck()

    games = build(read_rows(a.days))
    if not games:
        print("no upcoming NFL games in the capture window", file=sys.stderr)
        return 0
    if a.dry_run:
        for g in games[:6]:
            sp, to = g.get("spread") or {}, g.get("total") or {}
            print(f"{g['away']} at {g['home']}  {g['kickoff'][:16]}  "
                  f"{sp.get('favourite', '—')} {sp.get('favourite_line', '')}  "
                  f"O/U {to.get('line', '—')}  ({sp.get('book', 'n/a')})")
        print(f"... {len(games)} games")
        return 0
    doc = publish(games)
    print(f"wrote {OUT}: {doc['n_games']} games, "
          f"{doc['n_with_spread']} with a spread, {doc['n_with_total']} with a total")
    return 0


def _selfcheck() -> int:
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ko = "2026-09-13T17:00Z"
    base = {"event_id": "401872656", "sport": "nfl", "season": 2026, "week": 1,
            "kickoff": ko, "home": "Cincinnati Bengals", "away": "Tampa Bay Buccaneers",
            "book": "DraftKings"}

    def row(market, selection, line, price, prov, at):
        return dict(base, market=market, selection=selection, line=line,
                    price=price, provenance=prov, observed_at=at)

    rows = [
        # open: home -3.5. current: home -6.5. that is a 3-point move TOWARD home.
        row("spread", HOME_SIDE, -3.5, -110, OPEN, "2026-08-20T00:00:00Z"),
        row("spread", AWAY_SIDE, 3.5, -110, OPEN, "2026-08-20T00:00:00Z"),
        row("spread", HOME_SIDE, -6.5, -105, LIVE, "2026-08-25T00:00:00Z"),
        row("spread", AWAY_SIDE, 6.5, -115, LIVE, "2026-08-25T00:00:00Z"),
        row("total", "over", 47.5, -110, OPEN, "2026-08-20T00:00:00Z"),
        row("total", "over", 51.5, -110, LIVE, "2026-08-25T00:00:00Z"),
        row("total", "under", 51.5, -110, LIVE, "2026-08-25T00:00:00Z"),
        # a stale earlier reading must NOT win over the later one
        row("spread", HOME_SIDE, -9.5, -110, LIVE, "2026-08-21T00:00:00Z"),
    ]
    # multi-book moneyline, named by team the way engine/lines.py writes it
    for bk, hp, ap_ in (("draftkings", -260, 210), ("fanduel", -250, 205),
                        ("betmgm", -270, 215)):
        rows.append(dict(base, book=bk, market="moneyline",
                         selection="Cincinnati Bengals", line=None, price=hp,
                         provenance=LIVE, observed_at="2026-08-25T00:00:00Z"))
        rows.append(dict(base, book=bk, market="moneyline",
                         selection="Tampa Bay Buccaneers", line=None, price=ap_,
                         provenance=LIVE, observed_at="2026-08-25T00:00:00Z"))
    rows.sort(key=lambda r: r["observed_at"])

    g = build(rows, now=now)
    assert len(g) == 1, g
    sp = g[0]["spread"]

    # THE assertion this module exists for: side_a is the home team
    assert sp["home"] == -6.5, f"home spread wrong: {sp}"
    assert sp["away"] == 6.5, f"away spread wrong: {sp}"
    assert sp["favourite"] == "Cincinnati Bengals", sp
    assert sp["open_home"] == -3.5 and sp["move_pts"] == -3.0, sp
    assert sp["favourite_line"] == -6.5, sp
    # the series carries every live reading, oldest first, ends on the current one
    assert [pt[1] for pt in sp["history"]] == [-9.5, -6.5], sp["history"]

    # a ROAD favourite: home line is positive, so the favourite is the away team
    # and its own number is the negative one. This is the case that reads
    # backwards if favourite_line is taken straight off the home column.
    road = [dict(r, line=-r["line"] if r.get("line") is not None else None)
            for r in rows if r["market"] == "spread"]
    rsp = build(road, now=now)[0]["spread"]
    assert rsp["favourite"] == "Tampa Bay Buccaneers", rsp
    assert rsp["favourite_line"] == -6.5, rsp

    to = g[0]["total"]
    assert to["line"] == 51.5 and to["open_line"] == 47.5 and to["move_pts"] == 4.0, to

    ml = g[0]["moneyline"]
    assert ml["n_books"] == 3, ml
    cin = ml["sides"]["Cincinnati Bengals"]
    assert cin["best_price"] == -250 and cin["best_book"] == "FanDuel", cin
    probs = [s["fair_prob"] for s in ml["sides"].values()]
    assert abs(sum(probs) - 1.0) < 1e-6, probs      # de-vig actually removed the vig
    assert cin["fair_prob"] > 0.5, cin

    # a game already kicked off is not "today's board"
    past = [dict(r, kickoff="2026-08-30T17:00Z") for r in rows]
    assert build(past, now=now) == [], "started games must drop out"

    # one book quoting is not a consensus, so no fair price is invented
    solo = [r for r in rows if r["market"] == "moneyline" and r["book"] == "draftkings"]
    solo += [r for r in rows if r["market"] == "spread"]
    one = build(solo, now=now)
    assert "fair_prob" not in one[0]["moneyline"]["sides"]["Cincinnati Bengals"], one

    # the same fixture under two id schemes must merge into ONE game carrying
    # both the spread (ESPN) and the multi-book moneyline (Odds API)
    espn = [r for r in rows if r["market"] in ("spread", "total")]
    api = [dict(r, event_id="9f3ac0deadbeef", kickoff="2026-09-13T17:05Z")
           for r in rows if r["market"] == "moneyline"]
    merged = build(sorted(espn + api, key=lambda r: r["observed_at"]), now=now)
    assert len(merged) == 1, f"fixture split across id schemes: {len(merged)} records"
    assert merged[0]["spread"]["home"] == -6.5, merged
    assert merged[0]["moneyline"]["n_books"] == 3, merged
    assert str(merged[0]["event_id"]).isdigit(), merged[0]["event_id"]

    print("nflboard.selfcheck: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
