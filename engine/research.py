"""Research — the six modules, folded into one report per matchup.

GAMES, STATS, INJURIES, ODDS, RESEARCH, TRACKING. Each already had a source on
this repo or has one now; nothing composed them into a single object a page or
a language model could read. This does that, and it does the RESEARCH module in
the one way that is defensible:

**Every number in ``facts`` is computed here, in Python, from data on disk.**

That is the whole design. A model asked to "analyse this matchup" will produce
four confident bullets containing statistics that do not exist, because prose
about a game is easy and arithmetic over a price history is not. So the
arithmetic happens first and the model is handed the answers. ``api/ask.js``
may rephrase these lines; it may not add a number to them.

Sources, and why each one:

* **Prices** come from ``data/capture/nfl/*.jsonl`` via ``alerts.load_observations``
  — which already gates to ``own_capture`` provenance and canonicalises book
  names. ESPN's ``espn_open`` rows sit in the same files and are excluded: they
  are someone else's claim about a price we did not watch.
* **Movement** uses ``alerts._series``, keyed by (event, market, selection,
  LINE, book). The line is part of the identity. Comparing -105 at 47.5 with
  -115 at 48.5 invents a juice move that never happened — the defect fixed in
  196f720, and the reason this module does not roll its own series.
* **The live board** (``board.json``) overrides capture for any game inside its
  window, because it reads eleven books at once and carries the de-vigged fair
  line. Capture covers the whole forward schedule; the board covers now.
* **Stats** from ``teamstats-nfl.json``, **injuries** from ``injuries.json``.

Games that have started are dropped. A report about a game in progress is a
scoreboard, and this is not one.

    python -m engine.research --sport nfl --limit 3 --print
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
from pathlib import Path

from .alerts import _series, load_observations
from .closing import TEAM_MAP
from .schema import american_to_prob, devig

# engine.capture writes ESPN's homeTeamOdds as side_a and awayTeamOdds as
# side_b (capture.py:217). Every display name in this module goes through here.
SIDE_LABEL = {"side_a": "home", "side_b": "away"}

# The free ESPN feed carries ONE book. That is enough to watch a number move
# and enough to strip that book's own margin, and it is not enough to say what
# the market thinks: a "consensus" of one book is that book. Anything claiming
# to be cross-book is gated on CONSENSUS_BOOKS, and the shopping edge — the
# gap between the best available number and fair — needs at least two prices
# to be a gap at all. With one book, best minus fair is the hold, and calling
# the hold an edge would invert the sign of the only claim this site makes.
MIN_BOOKS = 1
CONSENSUS_BOOKS = 3
MAX_INJURIES = 6       # per team in the report body; the rest are counted
PTS = 100.0            # implied probability expressed in points


def _line_group(market: str, line: str) -> str:
    """The key under which two sides of the same bet belong together.

    Totals share a number: over 46.5 and under 46.5 are both "46.5". Spreads do
    not — the home side is -1.5 and the away side is +1.5, one bet written from
    two ends. Grouping on the raw string therefore files each side under its
    own line, finds one side in each group, and concludes there is no market to
    price. That is why spread appeared in 1 of 48 reports and total in all 48.
    """
    if market == "spread" and line not in (None, "None"):
        try:
            return f"{abs(float(line)):g}"
        except ValueError:
            return str(line)
    return str(line)


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def upcoming_events(rows: list[dict], now: dt.datetime) -> dict[str, dict]:
    """Event metadata for every game that has not kicked off yet."""
    events: dict[str, dict] = {}
    for r in rows:
        ko = _parse(r.get("kickoff"))
        if not ko or ko <= now:
            continue
        events.setdefault(str(r.get("event_id")), {
            "event_id": str(r.get("event_id")),
            "home": r.get("home"), "away": r.get("away"),
            "kickoff": r.get("kickoff"),
            "season": r.get("season"), "week": r.get("week"),
        })
    return events


def latest_by_book(series: dict[tuple, list[dict]], event_id: str,
                   market: str) -> dict[tuple[str, str], dict[str, dict]]:
    """Most recent observation per book, grouped by (selection, line)."""
    out: dict[tuple[str, str], dict[str, dict]] = {}
    for (ev, mk, sel, line, book), rows in series.items():
        if ev != event_id or mk != market or not rows:
            continue
        out.setdefault((sel, line), {})[book] = rows[-1]
    return out


def price_block(series: dict[tuple, list[dict]], event_id: str,
                market: str) -> dict | None:
    """Best price, consensus and de-vigged fair for a market's dominant line.

    "Dominant line" means the line the most books are actually posting. A
    handful of stragglers still showing last week's number would otherwise
    split the market and hand back a fair price computed off three books.
    """
    grouped = latest_by_book(series, event_id, market)
    if not grouped:
        return None

    by_line: dict[str, dict[str, tuple[str, dict[str, dict]]]] = {}
    for (sel, line), books in grouped.items():
        by_line.setdefault(_line_group(market, line), {})[sel] = (line, books)
    key = max(by_line, key=lambda k: sum(len(b) for _, b in by_line[k].values()))
    sides = {sel: books for sel, (_, books) in by_line[key].items()}
    side_lines = {sel: ln for sel, (ln, _) in by_line[key].items()}
    if len(sides) < 2:
        return None                      # one-sided market: no fair price exists

    out_sides = {}
    raw = {}
    for sel, books in sides.items():
        prices = [(bk, int(r["price"])) for bk, r in books.items()
                  if r.get("price") is not None]
        if len(prices) < MIN_BOOKS:
            return None
        # Highest payout wins. On American odds that is the largest number for
        # a dog and the smallest magnitude for a favourite; ranking by implied
        # probability gets both cases right with no branching across ±100.
        best_book, best_price = min(prices, key=lambda p: american_to_prob(p[1]))
        worst_book, worst_price = max(prices, key=lambda p: american_to_prob(p[1]))
        consensus = statistics.median(american_to_prob(p) for _, p in prices)
        raw[sel] = consensus
        out_sides[sel] = {
            "selection": sel,
            "label": SIDE_LABEL.get(sel, sel),
            "line": (None if side_lines.get(sel) in (None, "None")
                     else float(side_lines[sel])),
            "best_price": best_price,
            "best_book": best_book,
            "worst_price": worst_price,
            "worst_book": worst_book,
            "n_books": len(prices),
            "consensus_prob": round(consensus, 4),
            "prices": dict(sorted(prices, key=lambda p: american_to_prob(p[1]))),
        }

    sels = list(out_sides)
    n_books = max(s["n_books"] for s in out_sides.values())
    try:
        fa, fb = devig(raw[sels[0]], raw[sels[1]])
    except (ValueError, KeyError):
        return None

    # The margin being removed. With one book this is that book's hold and it
    # is the honest thing to show in place of an edge.
    vig_pts = round((sum(raw.values()) - 1.0) * PTS, 2)

    for sel, fair in zip(sels, (fa, fb)):
        side = out_sides[sel]
        side["fair_prob"] = round(fair, 4)
        # What the best available number is worth against fair, in points of
        # implied probability. Only a gap when there is more than one price to
        # choose between — otherwise it is the hold wearing a different name.
        side["gain_pts"] = (
            round((american_to_prob(side["best_price"]) - fair) * PTS * -1, 2)
            if n_books >= 2 else None)

    headline = side_lines.get("side_a") or side_lines.get("over") or next(
        iter(side_lines.values()), None)
    return {
        "market": market,
        "line": None if headline in (None, "None") else float(headline),
        "n_books": n_books,
        "books": sorted({b for s in out_sides.values() for b in s["prices"]}),
        "vig_pts": vig_pts,
        "fair_basis": ("consensus of %d books" % n_books if n_books >= CONSENSUS_BOOKS
                       else "single book, margin removed" if n_books == 1
                       else "%d books" % n_books),
        "shoppable": n_books >= 2,
        "sides": out_sides,
    }


def line_history(series: dict[tuple, list[dict]], event_id: str,
                 market: str) -> dict | None:
    """Where the number itself opened and where it sits now.

    This watches the line. Watching the juice instead — the price history at a
    fixed line — is a different and equally real event, and it is published by
    engine/timeline.py: a total going 46.5 -> 47.5 is the market moving;
    -110 -> -120 at 46.5 is the book charging more for the same bet.
    """
    seen: list[tuple[str, float]] = []
    for (ev, mk, sel, ln, _book), rows in series.items():
        if ev != event_id or mk != market or ln in (None, "None"):
            continue
        # One side is enough to track the number, and mixing sides on a spread
        # would flip its sign every other row.
        if sel not in ("over", "side_a"):
            continue
        for r in rows:
            ts = r.get("observed_at")
            if ts:
                seen.append((str(ts), float(ln)))
    if len(seen) < 2:
        return None
    seen.sort()
    opened, current = seen[0][1], seen[-1][1]
    return {"opened": opened, "current": current,
            "moved": round(current - opened, 2),
            "first_seen": seen[0][0], "last_seen": seen[-1][0]}


def board_event(board: dict, home: str, away: str) -> dict | None:
    """The live board's version of this game, when it is inside the window."""
    for b in board.get("boards") or []:
        if b.get("sport") != "nfl":
            continue
        for ev in b.get("events") or []:
            if ev.get("home") == home and ev.get("away") == away:
                return ev
    return None


def team_injuries(inj: dict, team: str) -> dict:
    rows = ((inj.get("sports") or {}).get("nfl") or {}).get("teams", {}).get(team, [])
    return {
        "n": len(rows),
        "shown": rows[:MAX_INJURIES],
        "not_shown": max(0, len(rows) - MAX_INJURIES),
        "n_out": sum(1 for r in rows
                     if (r.get("status") or "").lower() in ("out", "injured reserve")),
    }


def _fmt_price(p: int) -> str:
    return f"+{p}" if p > 0 else str(p)


def build_facts(ev: dict, stats: dict, inj: dict, odds: dict,
                moves: dict, league: dict) -> list[dict]:
    """The RESEARCH module. Computed, never generated.

    Each entry carries the sentence AND the numbers behind it, so the page can
    render either and ``api/ask.js`` can be held to what is here.
    """
    facts: list[dict] = []
    home, away = ev["home"], ev["away"]
    named = {"home": home, "away": away, "over": "over", "under": "under"}

    # 1. The price gap. This is the product, so it leads — when it exists.
    best = None
    for market, blk in odds.items():
        if not blk or not blk.get("shoppable"):
            continue
        for sel, s in blk["sides"].items():
            if s.get("gain_pts") is None:
                continue
            if best is None or s["gain_pts"] > best[2]["gain_pts"]:
                best = (market, sel, s, blk)
    if best:
        market, sel, s, blk = best
        label = named.get(s.get("label"), s.get("label"))
        ln = "" if blk["line"] is None else f" {blk['line']}"
        facts.append({
            "kind": "price_gap",
            "text": (f"Best number on {label}{ln} ({market}) is "
                     f"{_fmt_price(s['best_price'])} at {s['best_book']}, against "
                     f"{_fmt_price(s['worst_price'])} at the worst of "
                     f"{s['n_books']} books — {abs(s['gain_pts']):.2f} points of "
                     f"implied probability versus the de-vigged fair price."),
            "numbers": {"best_price": s["best_price"], "best_book": s["best_book"],
                        "worst_price": s["worst_price"], "n_books": s["n_books"],
                        "gain_pts": s["gain_pts"], "market": market,
                        "line": blk["line"], "selection": label},
        })
    # No gap to report is not a finding worth a bullet on every single card.
    # It was one: 48 reports all opened with the same sentence naming the same
    # book, which reads as advertising and pushes the facts that actually
    # differ per game below the fold. The state still has to be visible, or a
    # fair price computed from one book's own margin looks like a market
    # consensus — so it lives in `market` below and in the odds panel, once,
    # unbranded, instead of leading the research every time.

    # 2. Where the number itself has gone since we first watched it.
    for market in ("spread", "total"):
        h = moves.get(f"{market}_line")
        if not h or h["moved"] == 0:
            continue
        facts.append({
            "kind": "line_move",
            "text": (f"The {market} opened {h['opened']:g} in our capture and sits at "
                     f"{h['current']:g} now ({h['moved']:+g})."),
            "numbers": h | {"market": market},
        })

    # 3. Form, with the basis season stated. An unlabelled last-season number
    #    presented as this year's form is the quiet lie in every stats panel.
    hs, as_ = stats.get(home), stats.get(away)
    if hs and as_ and hs.get("season") and as_.get("season"):
        hn = hs["season"].get("net_epa_pp")
        an = as_["season"].get("net_epa_pp")
        if hn is not None and an is not None:
            lead = home if hn > an else away
            facts.append({
                "kind": "efficiency",
                "text": (f"On {hs['basis_season']} form, {home} net "
                         f"{hn:+.3f} EPA/play and {away} net {an:+.3f} — "
                         f"{lead} by {abs(hn - an):.3f}."),
                "numbers": {"home_net": hn, "away_net": an,
                            "basis_season": hs["basis_season"],
                            "difference": round(abs(hn - an), 3)},
            })

    # 4. Pace/pass tendency against the league, which is the honest version of
    #    "pace advantage could push the total higher".
    if hs and as_ and league.get("pass_rate") is not None:
        hp = hs["season"].get("pass_rate")
        ap = as_["season"].get("pass_rate")
        if hp is not None and ap is not None:
            combined = (hp + ap) / 2
            facts.append({
                "kind": "tendency",
                "text": (f"Combined pass rate {combined:.3f} against a league "
                         f"average of {league['pass_rate']:.3f} "
                         f"({home} {hp:.3f}, {away} {ap:.3f})."),
                "numbers": {"combined": round(combined, 3),
                            "league": league["pass_rate"],
                            "home": hp, "away": ap},
            })

    # 5. Availability, stated as a count. Who is out is in the INJURIES module;
    #    what it is worth in points is a claim we cannot substantiate and will
    #    not make.
    for team in (away, home):
        t = inj.get(team) or {}
        if t.get("n_out"):
            facts.append({
                "kind": "availability",
                "text": (f"{team}: {t['n_out']} listed Out or on injured reserve, "
                         f"{t['n']} on the report."),
                "numbers": {"team": team, "n_out": t["n_out"], "n_listed": t["n"]},
            })

    # 6. How wide the market is. A market nobody agrees on is worth shopping.
    spread = odds.get("spread") or odds.get("moneyline")
    if spread and spread.get("shoppable"):
        widest = max(spread["sides"].values(),
                     key=lambda s: abs(american_to_prob(s["best_price"])
                                       - american_to_prob(s["worst_price"])))
        gap = abs(american_to_prob(widest["best_price"])
                  - american_to_prob(widest["worst_price"])) * PTS
        if gap >= 0.5:
            facts.append({
                "kind": "dispersion",
                "text": (f"{widest['n_books']} books quote "
                         f"{_fmt_price(widest['best_price'])} down to "
                         f"{_fmt_price(widest['worst_price'])} on the same side — "
                         f"{gap:.2f} points between the best and worst number."),
                "numbers": {"spread_pts": round(gap, 2),
                            "n_books": widest["n_books"]},
            })
    return facts


def league_averages(stats: dict) -> dict:
    out = {}
    for key in ("pass_rate", "net_epa_pp", "yards_pp"):
        vals = [t["season"][key] for t in stats.values()
                if t.get("season", {}).get(key) is not None]
        if vals:
            out[key] = round(statistics.mean(vals), 3)
    return out


def build(sport: str, data_dir: Path, root: Path, limit: int | None = None,
          dry_run: bool = False) -> dict:
    now = dt.datetime.now(dt.timezone.utc)

    rows = load_observations(str(root / f"data/capture/{sport}/*.jsonl"))
    series = _series(rows)
    events = upcoming_events(rows, now)

    stats_doc = load_json(data_dir / f"teamstats-{sport}.json")
    stats = stats_doc.get("teams") or {}
    # teamstats is keyed by abbreviation; every other feed here speaks full
    # club names. TEAM_MAP is the one definition of that pairing.
    by_name = {t["name"]: t for t in stats.values()}
    league = league_averages(stats)

    inj_doc = load_json(data_dir / "injuries.json")
    board = load_json(data_dir / "board.json")

    unresolved: set[str] = set()
    reports = []
    for ev in sorted(events.values(), key=lambda e: str(e["kickoff"])):
        home, away = ev["home"], ev["away"]
        for name in (home, away):
            if name not in TEAM_MAP:
                unresolved.add(name)

        odds = {m: price_block(series, ev["event_id"], m)
                for m in ("spread", "total", "moneyline")}
        odds = {m: v for m, v in odds.items() if v}
        if not odds:
            continue

        # Only the line history. A per-market consensus point series used to be
        # published here too and was 46% of research.json, read by nothing:
        # every subscript of `movement` in this repo is `{market}_line`. The
        # series it duplicated is published properly by engine/timeline.py, for
        # more events and in a tighter encoding, and both pages that load
        # research.json already load timeline.json beside it.
        # See docs/plans/research-payload-size.md.
        moves = {}
        for m in odds:
            lh = line_history(series, ev["event_id"], m)
            if lh:
                moves[f"{m}_line"] = lh

        team_stats = {n: by_name.get(n) for n in (home, away)}
        injuries = {n: team_injuries(inj_doc, n) for n in (home, away)}
        live = board_event(board, home, away)

        reports.append({
            "event_id": ev["event_id"],
            "sport": sport,
            "home": home, "away": away,
            "kickoff": ev["kickoff"],
            "season": ev["season"], "week": ev["week"],
            "records": {n: (team_stats[n] or {}).get("record") for n in (home, away)},
            "stats": {
                "basis_season": (team_stats[home] or {}).get("basis_season"),
                "metrics": stats_doc.get("metrics"),
                "home": team_stats[home], "away": team_stats[away],
                "league": league,
            },
            "injuries": {
                "updated_at": inj_doc.get("generated_at"),
                "espn_timestamp": ((inj_doc.get("sports") or {}).get(sport) or {})
                                  .get("espn_timestamp"),
                "home": injuries[home], "away": injuries[away],
            },
            "odds": odds,
            # How thin the market is, in one place the page can read without
            # parsing a sentence. shoppable is false until a second book posts.
            "market": {
                "shoppable": any(b.get("shoppable") for b in odds.values()),
                "n_books": max((b["n_books"] for b in odds.values()), default=0),
                "books": sorted({bk for b in odds.values() for bk in b["books"]}),
            },
            "movement": moves,
            # The board's own view when this game is inside its window: eleven
            # books read at once, which capture cannot match.
            "live_board": None if not live else {
                "max_gain_pts": live.get("max_gain_pts"),
                "n_books": live.get("n_books"),
                "generated_at": board.get("generated_at"),
            },
            "facts": build_facts(ev, {home: team_stats[home], away: team_stats[away]},
                                 injuries, odds, moves, league),
            "asof": now.isoformat(),
        })
        if limit and len(reports) >= limit:
            break

    doc = {
        "generated_at": now.isoformat(),
        "checked_at": now.isoformat(),
        "sport": sport,
        "n_reports": len(reports),
        "n_shoppable": sum(1 for r in reports if r["market"]["shoppable"]),
        "sources": {
            "prices": "own_capture observations (ESPN game lines)",
            "board": board.get("generated_at"),
            "teamstats": stats_doc.get("generated_at"),
            "injuries": inj_doc.get("generated_at"),
        },
        "note": ("Research only, not advice and not a pick. Every figure in "
                 "facts is computed from the data in this file."),
        # TRACKING. A report contains no pick, so there is nothing here for the
        # predictions ledger to grade and nothing is added to it — sealing
        # research as though it were a forecast would inflate the record with
        # claims we never made. What IS attestable is the price: this file is
        # committed to a public git repository on every build, so its timestamp
        # is third-party evidence that we held these numbers at that moment.
        # Same argument capture.yml makes about data/capture, and the same one
        # the ledger makes about predictions.
        "tracking": {
            "graded": False,
            "basis": ("Reports are not predictions and are not graded. The "
                      "published commit timestamp attests to when these prices "
                      "were held; model predictions are sealed separately."),
            "predictions_ledger": "/verify",
        },
        # Never silently dropped: a club name that does not resolve is a join
        # breaking, and it shows up here rather than as a missing panel.
        "unresolved_teams": sorted(unresolved),
        "reports": reports,
    }

    if not dry_run:
        data_dir.mkdir(parents=True, exist_ok=True)
        out = data_dir / "research.json"
        if not reports and out.exists():
            try:
                prev = json.loads(out.read_text())
                prev["checked_at"] = now.isoformat()
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(prev, indent=1))
                os.replace(tmp, out)
                return prev
            except (json.JSONDecodeError, OSError):
                pass
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=1))
        os.replace(tmp, out)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--data-dir", default="site/public/data")
    ap.add_argument("--root", default=".")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--print", dest="show", action="store_true",
                    help="print the first report in full")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    doc = build(a.sport, Path(a.data_dir), Path(a.root), a.limit, a.dry_run)
    print(f"{doc['n_reports']} reports ({doc['sport']})")
    if doc["unresolved_teams"]:
        print("UNRESOLVED TEAM NAMES:", ", ".join(doc["unresolved_teams"]))
    if a.show and doc["reports"]:
        r = doc["reports"][0]
        print(f"\n{r['away']} at {r['home']} — {r['kickoff']} (week {r['week']})")
        print(f"  markets: {', '.join(r['odds'])}")
        for f in r["facts"]:
            print(f"  • [{f['kind']}] {f['text']}")


if __name__ == "__main__":
    main()
