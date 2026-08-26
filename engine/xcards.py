"""The ten Sooth post types, each composed from numbers already published.

    python -m engine.xpost --kind board --preview /tmp/cards
    python -m engine.xpost --kind signal

WHAT THIS IS
------------
A modular broadcast graphics package. Every card wears the same furniture from
engine/xkit.py — lit edge, eyebrow, date stamp, wordmark — and every card
composes its own layout. A table, a head-to-head, a single figure and a
dashboard should not be the same rectangle with different words in it.

WHAT IT WILL NOT DO
-------------------
Nothing here invents a number. Each composer reads one published feed and
returns None when that feed cannot support the card, which is why several are
sport-specific: MATCHUP INTELLIGENCE needs nflverse team ratings, PROP LAB
needs MLB game logs. A quiet day produces fewer cards, not softer ones.

Three adaptations from the reference sheet, all because the data is not there:
THE BOARD prices moneylines, not spreads and totals, because moneyline is what
the board feed captures; RESULT RECEIPT has no final-score column, because the
graded ledger stores outcomes and prices, not scores; PROP LAB shows hit rates
rather than a projection, because the projection only exists for strikeouts.
Inventing any of the three would break the only thing this account sells.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from engine.xkit import (BG, BRAND, DIM, INK, INK2, LOSS, PANEL, PANEL2, PUSH,
                         STROKE, Card, body, crest, display, headshot, load, mono)

BOOKS = {"williamhill_us": "Caesars", "betmgm": "BetMGM", "draftkings": "DraftKings",
         "fanduel": "FanDuel", "betrivers": "BetRivers", "bovada": "Bovada",
         "mybookieag": "MyBookie", "betonlineag": "BetOnline", "lowvig": "LowVig",
         "betus": "BetUS", "pointsbetus": "PointsBet"}

# Leagues with enough books quoting them that a price move means something.
# A three-book prelim fight drifting eight points is noise wearing a suit.
LIQUID = {"nfl", "nba", "mlb", "nhl", "ncaaf", "ncaab", "wnba", "epl", "mls"}
COMBAT = {"ufc", "mma", "boxing"}

# The model that never sees the line. The other one reads the market, so its
# record is not the honest one to publish.
INDEPENDENT = "elo+epa-v1"


def book(k: str) -> str:
    return BOOKS.get((k or "").lower(), (k or "").replace("_", " ").title())


def implied(price) -> float | None:
    """American price -> implied probability, vig included. Labelled as such
    everywhere it is shown: a one-sided price is not a fair probability."""
    if not isinstance(price, (int, float)) or price == 0:
        return None
    p = float(price)
    return (-p) / (-p + 100) if p < 0 else 100 / (p + 100)


def am(price) -> str:
    return f"{int(price):+d}" if isinstance(price, (int, float)) else "—"


def clock(iso: str) -> str:
    try:
        t = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        return t.astimezone().strftime("%a %-I:%M%p").upper()
    except Exception:
        return "—"


def fixture(sport: str, away: str, home: str) -> str:
    """'A at B' for a venue sport, 'A vs B' for a fight. Two fighters do not
    play at each other's house."""
    return f"{away} {'vs' if (sport or '').lower() in COMBAT else 'at'} {home}"


def abbr(name: str, cap: int = 20) -> str:
    return name if len(name) <= cap else name[:cap - 1] + "."


# ============================================================ 01 — THE BOARD

def board():
    """A slate at a glance. A table, because a slate IS a table."""
    d = load("board.json")
    rows = []
    for b in d.get("boards") or []:
        for e in b.get("events") or []:
            sides = e.get("sides") or []
            if len(sides) < 2:
                continue
            rows.append({"sport": b.get("sport", ""), "away": e.get("away", ""),
                         "home": e.get("home", ""), "starts": e.get("starts", ""),
                         "sides": sides,
                         "gain": max((s.get("gain_pts") or 0) for s in sides)})
    if len(rows) < 3:
        return None
    rows.sort(key=lambda r: r["gain"], reverse=True)
    rows = rows[:5]
    tot = d.get("totals") or {}

    c = Card("the board")
    p = c.pad
    c.d.text((p - 4, p + 70), "TODAY'S BOARD", font=display(94), fill=INK)
    c.label((p, p + 182), f"{tot.get('events', 0)} events priced · "
                          f"{len(d.get('boards') or [])} sports · "
                          f"best available price, both sides", DIM, 21)

    cols = (p, 560, 750, 1010, 1300)
    y = p + 216
    c.label((cols[0], y), "matchup", DIM, 18)
    c.label((cols[1], y), "start", DIM, 18)
    c.label((cols[2], y), "away", DIM, 18)
    c.label((cols[3], y), "home", DIM, 18)
    c.label((cols[4], y), "shop gain", DIM, 18)
    y += 30
    c.rule(p, y, c.w - p)

    for r in rows:
        c.d.text((cols[0], y + 14), abbr(r["away"], 22), font=body(27, "medium"), fill=INK)
        c.d.text((cols[0] + 4, y + 46), f"{'vs' if r['sport'] in COMBAT else 'at'} "
                                        f"{abbr(r['home'], 22)}", font=body(23), fill=INK2)
        c.d.text((cols[1], y + 26), clock(r["starts"]), font=mono(22), fill=INK2)
        for i, s in enumerate(r["sides"][:2]):
            x = cols[2 + i]
            c.d.text((x, y + 20), am(s.get("best_price")), font=mono(28, True), fill=INK)
            c.d.text((x, y + 50), book(s.get("best_book", "")), font=mono(17), fill=DIM)
        c.d.text((cols[4] + 46, y + 22), f"{r['gain']:.2f}", font=mono(28, True), fill=BRAND)
        c.d.text((cols[4] + 132, y + 28), "PTS", font=mono(18), fill=DIM)
        y += 84
        c.rule(p, y, c.w - p, (20, 23, 27))

    top = rows[0]
    cap = (f"Today's board: {tot.get('events', 0)} events across "
           f"{len(d.get('boards') or [])} sports, priced at every US book we read.\n\n"
           f"Widest shop gap right now — {fixture(top['sport'], top['away'], top['home'])}, "
           f"{top['gain']:.2f} points of implied probability between the best and "
           f"worst price on the same side.\n\n"
           "No sides here. Just what the market says.\n\nsooth.bet/board")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return {"key": f"board-{stamp}", "title": "Today's board", "caption": cap,
            "img": c.done()}


# ------------------------------------------------ 01b — THE BOARD, PORTRAIT

def board_portrait():
    """The board again, built for a 4:5 feed rather than cropped into one.

    A wide table does not survive the trip: at 4:5 the columns either collapse
    or the type drops below thumb-legible. So each game becomes a stacked block
    — fixture and shop gap on one line, clock and both prices under it — which
    is what a table turns into when you take its width away.
    """
    d = load("board.json")
    rows = []
    for b in d.get("boards") or []:
        for e in b.get("events") or []:
            sides = e.get("sides") or []
            if len(sides) < 2:
                continue
            rows.append({"sport": b.get("sport", ""), "away": e.get("away", ""),
                         "home": e.get("home", ""), "starts": e.get("starts", ""),
                         "sides": sides,
                         "gain": max((s.get("gain_pts") or 0) for s in sides)})
    if len(rows) < 3:
        return None
    rows.sort(key=lambda r: r["gain"], reverse=True)
    rows = rows[:6]
    tot = d.get("totals") or {}

    c = Card("the board", size="portrait")
    p = c.pad
    c.d.text((p - 3, p + 66), "TODAY'S", font=display(96), fill=INK)
    c.d.text((p - 3, p + 152), "BOARD", font=display(96), fill=INK)
    c.label((p, p + 264), f"{tot.get('events', 0)} events · "
                          f"{len(d.get('boards') or [])} sports", DIM, 20)
    c.label((p, p + 296), "best available price, both sides", DIM, 20)

    y = p + 340
    c.rule(p, y, c.w - p)
    for r in rows:
        gain = f"{r['gain']:.2f}"
        gw = c.d.textlength(gain, font=mono(30, True))
        c.d.text((c.w - p - gw - 46, y + 20), gain, font=mono(30, True), fill=BRAND)
        c.d.text((c.w - p - 40, y + 26), "PTS", font=mono(18), fill=DIM)
        c.d.text((p, y + 18), abbr(r["away"], 24), font=body(28, "medium"), fill=INK)
        c.d.text((p, y + 50), f"{'vs' if r['sport'] in COMBAT else 'at'} "
                              f"{abbr(r['home'], 24)}", font=body(26), fill=INK2)
        c.d.text((p, y + 90), clock(r["starts"]), font=mono(20), fill=DIM)
        x = p + 190
        for sd in r["sides"][:2]:
            c.d.text((x, y + 88), am(sd.get("best_price")), font=mono(23, True), fill=INK)
            # 9 chars clipped DraftKings to "DraftKing", which reads as a typo
            c.d.text((x + 74, y + 90), book(sd.get("best_book", ""))[:10],
                     font=mono(17), fill=DIM)
            x += 250
        y += 132
        c.rule(p, y, c.w - p, (20, 23, 27))

    top = rows[0]
    cap = (f"Today's board: {tot.get('events', 0)} events across "
           f"{len(d.get('boards') or [])} sports, priced at every US book we read.\n\n"
           f"Widest shop gap right now — {fixture(top['sport'], top['away'], top['home'])}, "
           f"{top['gain']:.2f} points of implied probability between the best and "
           f"worst price on the same side.\n\n"
           "No sides here. Just what the market says.\n\n"
           "Every number, free, at sooth.bet/board")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return {"key": f"board-ig-{stamp}", "title": "Today's board (4:5)",
            "caption": cap, "img": c.done()}


# ---- shared selection for the two model-vs-price cards ----------------------

def _disagreements() -> list[tuple[float, dict, float]]:
    """Every game where our number and the best price differ, widest first."""
    out = []
    for g in (load("best_lines.json").get("games") or []):
        imp = implied(g.get("best_price"))
        if imp is None or not g.get("our_prob"):
            continue
        out.append((abs(g["our_prob"] - imp), g, imp))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


# ========================================================= 02 — SOOTH SIGNAL

def signal():
    """One disagreement, with the ratings that caused it.

    Deliberately takes the SECOND widest, because MODEL VS MARKET takes the
    widest. Two cards about the same game on the same day reads as one card
    posted twice.
    """
    d = _disagreements()
    if not d:
        return None
    _, g, imp = d[1] if len(d) > 1 else d[0]
    delta = (g["our_prob"] - imp) * 100
    away, home = g.get("away", ""), g.get("home", "")

    c = Card("sooth signal")
    p = c.pad
    c.d.text((p - 4, p + 70), "SOOTH SIGNAL", font=display(94), fill=INK)

    c.paste(crest(away, "nfl"), (p, p + 178, 92, 92))
    c.d.text((p + 108, p + 196), "@", font=display(54), fill=DIM)
    c.paste(crest(home, "nfl"), (p + 158, p + 178, 92, 92))
    c.d.text((p, p + 292), f"{away} @ {home}", font=body(34, "medium"), fill=INK)
    c.label((p, p + 340), f"{clock(g.get('kickoff', ''))} · {g.get('n_books', 0)} books",
            DIM, 20)

    px, py, pw = p, p + 392, 640
    c.panel((px, py, px + pw, py + 250))
    rows = [("MARKET IMPLIED", f"{imp * 100:.1f}%",
             f"{am(g['best_price'])} at {book(g.get('best_book', ''))}", INK),
            ("SOOTH MODEL", f"{g['our_prob'] * 100:.1f}%",
             "independent · never sees the line", INK),
            ("DIFFERENCE", f"{delta:+.1f} PTS", "of implied probability",
             BRAND if delta > 0 else LOSS)]
    ry = py + 24
    for i, (lab, val, note, col) in enumerate(rows):
        c.label((px + 28, ry + 4), lab, DIM, 18)
        vw = c.d.textlength(val, font=mono(38, True))
        c.d.text((px + pw - 28 - vw, ry - 8), val, font=mono(38, True), fill=col)
        c.d.text((px + 28, ry + 30), note, font=body(20), fill=DIM)
        ry += 78
        if i < 2:
            c.rule(px + 28, ry - 14, px + pw - 28, (26, 29, 34))

    rx = 790
    c.label((rx, p + 180), "what the ratings say", BRAND, 20)
    c.para((rx, p + 224), _why_nfl(load("teamstats-nfl.json").get("teams") or {},
                                   away, home),
           body(26), INK2, max_w=c.w - rx - p, lead=41, limit=c.floor - 40)
    c.label((rx, c.floor - 22), "nflverse team ratings · walk-forward", DIM, 18)

    cap = (f"{away} @ {home}.\n\n"
           f"Best price on {g.get('pick', '')} is {am(g['best_price'])} at "
           f"{book(g.get('best_book', ''))} — {imp * 100:.1f}% implied. Our "
           f"independent model, which never sees the line, has it at "
           f"{g['our_prob'] * 100:.1f}%. A {delta:+.1f} point disagreement.\n\n"
           "A disagreement is a reason to research a game, not a reason to back "
           "a side. The model is wrong plenty — the record is public.\n\n"
           "sooth.bet/edges")
    return {"key": f"signal-{g.get('game_id')}-{round(delta, 1)}",
            "title": "Sooth Signal", "caption": cap, "img": c.done()}


def _why_nfl(ts: dict, away: str, home: str) -> str:
    a, h = ts.get(away) or {}, ts.get(home) or {}
    ra, rh = (a.get("rating") or {}), (h.get("rating") or {})
    if not ra or not rh:
        return ("The model reads walk-forward team ratings and the market's own "
                "price history. It has no ratings for this pairing yet.")
    na, nh = ra.get("net", 0), rh.get("net", 0)
    lead, trail = (home, away) if nh > na else (away, home)
    hi, lo = max(nh, na), min(nh, na)
    return (f"{lead} rates {hi:+.3f} net EPA per play against {trail}'s {lo:+.3f}, "
            f"walk-forward — built only from games played before the one being "
            f"priced.\n\n"
            f"That gap is most of the model's number here. It carries no injury "
            f"news and no line movement.")


# ================================================ 03 — MATCHUP INTELLIGENCE

KEYS = ("off_epa_pp", "def_epa_pp", "yards_pp", "first_down_rate",
        "explosive_rate", "turnover_rate")


def matchup():
    """Two teams, six measures, mirrored bars. The one card that is a diagram."""
    reports = [r for r in (load("research.json").get("reports") or [])
               if ((r.get("stats") or {}).get("home") or {}).get("season")
               and ((r.get("stats") or {}).get("away") or {}).get("season")]
    if not reports:
        return None
    r = reports[0]
    st = r["stats"]
    metrics = {m["key"]: m for m in st.get("metrics") or []}
    hs, as_ = st["home"]["season"], st["away"]["season"]
    keys = [k for k in KEYS if k in hs and k in as_][:6]
    if len(keys) < 4:
        return None
    home, away = r.get("home", ""), r.get("away", "")

    c = Card("matchup intelligence")
    p = c.pad
    c.d.text((p - 4, p + 68), "MATCHUP INTELLIGENCE", font=display(84), fill=INK)

    mid = c.w // 2
    c.paste(crest(away, "nfl"), (p, p + 172, 78, 78))
    c.d.text((p + 96, p + 186), st["away"].get("abbr", ""), font=display(56), fill=INK)
    hab = st["home"].get("abbr", "")
    hw = c.d.textlength(hab, font=display(56))
    c.paste(crest(home, "nfl"), (c.w - p - 78, p + 172, 78, 78))
    c.d.text((c.w - p - 96 - hw, p + 186), hab, font=display(56), fill=INK)
    c.d.text((mid - 24, p + 196), "VS", font=display(40), fill=DIM)

    # each side gets a number gutter OUTSIDE its bar; the first cut printed the
    # values on top of the bars they described
    y = p + 292
    for k in keys:
        m = metrics.get(k, {"label": k, "better": "high", "dp": 3})
        av, hv = as_.get(k), hs.get(k)
        fa, fh = _pair(av, hv, m.get("better"))
        dp = m.get("dp", 3)
        at, ht = f"{av:.{dp}f}", f"{hv:.{dp}f}"
        aw = c.d.textlength(at, font=mono(24, True))
        c.d.text((250 - aw, y - 5), at, font=mono(24, True), fill=INK2)
        c.hbar(272, y, 348, 15, fa, BRAND if fa >= fh else LOSS, rtl=True)
        lab = m.get("label", k).upper()
        lw = c.track_w(lab, mono(19), 3)
        c.tracked((mid - lw / 2, y - 4), lab, mono(19), DIM, 3)
        c.hbar(980, y, 348, 15, fh, BRAND if fh > fa else LOSS)
        c.d.text((1350, y - 5), ht, font=mono(24, True), fill=INK2)
        y += 64

    c.label((p, c.floor - 6), f"season {st.get('basis_season', '')} · nflverse "
                              f"play-by-play · teal = better of the two", DIM, 18)

    cap = (f"{away} at {home} — six measures, both sides, same scale.\n\n"
           f"Season {st.get('basis_season', '')} rates on nflverse play-by-play. "
           "Teal is the better of the pair on that measure; the numbers are "
           "printed so you can check the bar against them.\n\n"
           "No side, no number to back. Research first.\n\nsooth.bet/research")
    return {"key": f"matchup-{r.get('event_id')}", "title": "Matchup intelligence",
            "caption": cap, "img": c.done()}


def _pair(a, b, better) -> tuple[float, float]:
    """Bar lengths for a head-to-head. The better side is full, the other is
    scaled down but never to zero — a short bar still has to be readable."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return 0.3, 0.3
    ga, gb = (a, b) if better != "low" else (-a, -b)
    hi, lo = max(ga, gb), min(ga, gb)
    if hi == lo:
        return 0.7, 0.7
    return (0.32 + 0.68 * (ga - lo) / (hi - lo),
            0.32 + 0.68 * (gb - lo) / (hi - lo))


# ============================================================= 04 — ONE STAT

def onestat():
    """One number, big enough to read at thumbnail size. Nothing else."""
    b = load("board.json")
    tot = b.get("totals") or {}
    if not tot.get("max_gain_pts"):
        return None
    fig = f"{tot['max_gain_pts']:.2f}"

    c = Card("one stat")
    f = display(300)
    w = c.d.textlength(fig, font=f)
    unit_w = c.d.textlength("PTS", font=display(80))
    x0 = (c.w - (w + 24 + unit_w)) / 2
    c.d.text((x0, 206), fig, font=f, fill=BRAND)
    c.d.text((x0 + w + 24, 300), "PTS", font=display(80), fill=DIM)

    y = 552
    for ln in ("POINTS BETWEEN THE BEST AND WORST PRICE",
               "ON THE SAME SIDE OF THE SAME GAME"):
        lw = c.track_w(ln, body(30, "medium"), 2)
        c.tracked(((c.w - lw) / 2, y), ln, body(30, "medium"), INK, 2)
        y += 46
    c.rule(c.w / 2 - 90, y + 32, c.w / 2 + 90, STROKE)
    src = (f"across {tot.get('events', 0)} events and "
           f"{len(b.get('boards') or [])} sports today · average gap "
           f"{tot.get('avg_gain_pts', 0):.2f} pts · us books").upper()
    sw = c.track_w(src, mono(19), 3)
    c.tracked(((c.w - sw) / 2, y + 58), src, mono(19), DIM, 3)

    cap = (f"{fig} points.\n\n"
           f"That is the widest gap between the best and the worst price on the "
           f"same side of the same game on today's board — across "
           f"{tot.get('events', 0)} events. The average gap is "
           f"{tot.get('avg_gain_pts', 0):.2f} points.\n\n"
           "Same wager. Different price. The book you use is a bigger edge than "
           "most models are.\n\nsooth.bet/board")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return {"key": f"onestat-{stamp}", "title": "One stat", "caption": cap,
            "img": c.done()}


# ========================================================= 05 — MARKET WATCH

def marketwatch():
    """A price that moved, with its own history under it."""
    best = None
    for e in load("timeline.json").get("events") or []:
        ml = (e.get("markets") or {}).get("moneyline") or {}
        pts = [v for _, v in (ml.get("consensus") or []) if isinstance(v, (int, float))]
        # liquidity gate: a three-book market drifting is a bookkeeping event,
        # not a market event, and the first render led with a prelim UFC fight
        if len(pts) < 8 or (ml.get("n_books") or 0) < 5:
            continue
        if str(e.get("sport", "")).lower() not in LIQUID:
            continue
        move = pts[-1] - pts[0]
        if best is None or abs(move) > abs(best[0]):
            best = (move, e, ml, pts)
    if not best or abs(best[0]) < 0.8:
        return None
    move, e, ml, pts = best
    side = e.get("home") if ml.get("ref") == "home" else e.get("away")
    sport = str(e.get("sport", "")).lower()

    c = Card("market watch")
    p = c.pad
    c.d.text((p - 4, p + 70), "MARKET WATCH", font=display(94), fill=INK)
    c.d.text((p, p + 186), fixture(sport, e.get("away", ""), e.get("home", "")),
             font=body(31, "medium"), fill=INK2)
    c.label((p, p + 234), f"{sport.upper()} · {side} · {ml.get('n_books', 0)} books",
            DIM, 20)

    col = BRAND if move > 0 else LOSS
    y = p + 306
    # "earliest", not "open": this is the start of OUR capture window, which is
    # not the same thing as the market's opening price and must not claim to be
    for lab, val, colr in (("EARLIEST READ", f"{pts[0]:.1f}%", INK2),
                           ("LATEST", f"{pts[-1]:.1f}%", INK),
                           ("MOVE", f"{move:+.1f} PTS", col)):
        c.label((p, y), lab, DIM, 19)
        c.d.text((p, y + 28), val, font=display(72), fill=colr)
        y += 124

    cx, cy, cw, ch = 700, p + 286, c.w - 700 - p, 330
    c.panel((cx - 26, cy - 36, cx + cw + 26, cy + ch + 66))
    c.sparkline((cx, cy, cw, ch), pts, col)
    c.label((cx, cy + ch + 24), f"{len(pts)} hourly observations · our own capture",
            DIM, 18)

    cap = (f"{fixture(sport, e.get('away', ''), e.get('home', ''))} — the market moved.\n\n"
           f"{side} was at {pts[0]:.1f}% implied across {ml.get('n_books', 0)} books "
           f"at the earliest reading in our capture window, and sits at "
           f"{pts[-1]:.1f}% now. A {move:+.1f} point move over {len(pts)} hourly "
           f"observations.\n\n"
           "We log what moved. We do not claim to know why — that is usually a "
           "story told after the fact.\n\nsooth.bet/timeline")
    return {"key": f"move-{e.get('event_id')}-{round(move, 1)}",
            "title": "Market watch", "caption": cap, "img": c.done()}


# ======================================================== 06 — PLAYER PROP LAB

def proplab():
    """One player, one line, the game log behind it. Portrait left, panel right."""
    cand = []
    for b in load("props.json").get("boards") or []:
        for e in b.get("events") or []:
            for pp in e.get("props") or []:
                if ((pp.get("hit") or {}).get("season") or {}).get("n"):
                    cand.append((pp.get("gain_pts") or 0, pp, e, b))
    if not cand:
        return None
    _, pp, e, b = max(cand, key=lambda t: t[0])
    hit, player = pp["hit"], pp.get("player", "")
    s = hit["season"]

    c = Card("player prop lab")
    p = c.pad
    c.d.text((p - 4, p + 70), "PLAYER PROP LAB", font=display(90), fill=INK)

    px, py, pw, ph = p, p + 196, 452, 452
    c.panel((px, py, px + pw, py + ph))
    if not c.paste(headshot(player), (px + 40, py + 24, pw - 80, ph - 140)):
        ini = "".join(w[0] for w in player.split()[:2])
        iw = c.d.textlength(ini, font=display(150))
        c.d.text((px + (pw - iw) / 2, py + 120), ini, font=display(150), fill=PANEL2)
    c.d.text((px + 30, py + ph - 96), abbr(player, 24), font=body(30, "medium"), fill=INK)
    # club names only: the full fixture ran out of its own panel, and an
    # ellipsis in the middle of a team name reads as a rendering bug
    nick = lambda n: (n or "").split()[-1]
    c.label((px + 30, py + ph - 50),
            f"{b.get('label', '')} · {nick(e.get('away'))} at {nick(e.get('home'))}",
            DIM, 17)

    rx = px + pw + 46
    c.label((rx, p + 200), pp.get("market_label", pp.get("market", "")), BRAND, 22)
    c.d.text((rx, p + 234), f"OVER {pp.get('line')}", font=display(82), fill=INK)

    rows = [("BEST PRICE", f"{am(pp['over'].get('best_price'))}  "
                           f"{book(pp['over'].get('best_book', ''))}"),
            ("DE-VIGGED FAIR", am(pp["over"].get("fair_price"))),
            ("LAST 5", f"{hit['l5']['over']} of {hit['l5']['n']}"),
            ("LAST 10", f"{hit['l10']['over']} of {hit['l10']['n']}"),
            ("SEASON", f"{s['over']} of {s['n']}  ({s['over'] / s['n'] * 100:.0f}%)")]
    y = p + 346
    for lab, val in rows:
        c.label((rx, y + 6), lab, DIM, 19)
        vw = c.d.textlength(val, font=mono(27, True))
        c.d.text((c.w - p - vw, y - 2), val, font=mono(27, True), fill=INK)
        y += 58
        c.rule(rx, y - 16, c.w - p, (24, 27, 32))
    c.label((rx, y + 10), f"game log: statsapi.mlb.com · shop gain "
                          f"{pp.get('gain_pts', 0):.2f} pts", DIM, 18)

    cap = (f"{player} — {pp.get('market_label', '')} {pp.get('line')}.\n\n"
           f"Over has hit {s['over']} of {s['n']} this season "
           f"({s['over'] / s['n'] * 100:.0f}%), {hit['l10']['over']} of "
           f"{hit['l10']['n']} in the last ten. Best available price is "
           f"{am(pp['over'].get('best_price'))} at "
           f"{book(pp['over'].get('best_book', ''))}; de-vigged fair is "
           f"{am(pp['over'].get('fair_price'))}.\n\n"
           "A hit rate is history, not a projection. Here is the log — draw "
           "your own conclusion.\n\nsooth.bet/props")
    return {"key": f"prop-{player}-{pp.get('market')}-{pp.get('line')}",
            "title": "Player prop lab", "caption": cap, "img": c.done()}


# ====================================================== 07 — MODEL VS MARKET

def modelvmarket():
    """Two plates, one delta. The account's signature recurring post."""
    d = _disagreements()
    if not d:
        return None
    _, g, imp = d[0]
    delta = (g["our_prob"] - imp) * 100
    away, home = g.get("away", ""), g.get("home", "")

    c = Card("model vs market")
    p = c.pad
    c.d.text((p - 4, p + 70), "MODEL VS MARKET", font=display(94), fill=INK)
    c.paste(crest(away, "nfl"), (p, p + 180, 72, 72))
    label = f"{away} @ {home}"
    c.d.text((p + 90, p + 192), label, font=body(34, "medium"), fill=INK2)
    c.paste(crest(home, "nfl"),
            (p + 106 + c.d.textlength(label, font=body(34, "medium")), p + 180, 72, 72))

    plates = [("MARKET IMPLIED", f"{imp * 100:.1f}%", INK,
               f"{am(g['best_price'])} · {book(g.get('best_book', ''))}"),
              ("SOOTH MODEL", f"{g['our_prob'] * 100:.1f}%", BRAND,
               "independent · never sees the line")]
    x, pw = p, 560
    for lab, val, col, note in plates:
        c.panel((x, p + 290, x + pw, p + 512))
        c.label((x + 32, p + 320), lab, DIM, 20)
        c.d.text((x + 28, p + 352), val, font=display(112), fill=col)
        c.d.text((x + 32, p + 468), note, font=body(21), fill=DIM)
        x += pw + 60

    dcol = BRAND if delta > 0 else LOSS
    c.label((p, p + 556), "delta", DIM, 22)
    c.d.text((p, p + 588), f"{delta:+.1f}%", font=display(112), fill=dcol)
    c.para((p + 400, p + 536), "Points of implied probability between our number "
                               "and the best price on the market.\n\n"
                               "Not an instruction — a place to look.",
           body(24), DIM, max_w=680, lead=34, limit=c.floor)

    cap = (f"{away} @ {home}.\n\n"
           f"Market implied: {imp * 100:.1f}% ({am(g['best_price'])} at "
           f"{book(g.get('best_book', ''))}, vig included).\n"
           f"Sooth model: {g['our_prob'] * 100:.1f}%.\n"
           f"Delta: {delta:+.1f} points.\n\n"
           "The model is independent — it never sees the line before it prices "
           "a game. When it disagrees this much, one of the two is wrong, and "
           "it is often us. The record is public.\n\nsooth.bet/record")
    return {"key": f"mvm-{g.get('game_id')}-{round(delta, 1)}",
            "title": "Model vs market", "caption": cap, "img": c.done()}


# ======================================================= 08 — RESULT RECEIPT

def _graded() -> dict | None:
    """The most recent graded slate. Replays are used and LABELLED as replays —
    week one has not been played yet, and a replay presented as a live result is
    exactly the dishonesty this account exists to be the opposite of."""
    import glob
    from engine.xkit import DATA
    files = sorted(glob.glob(os.path.join(DATA, "*.graded.json")))
    return load(files[-1]) if files else None


def _sample(picks: list, n: int) -> list:
    """An evenly spaced slice of the confidence range.

    Taking the top N by probability is how a receipt becomes a highlight reel:
    the first render showed six calls and all six had won. Spanning the range
    puts the shakiest call on the card by construction.
    """
    ordered = sorted(picks, key=lambda x: -(x.get("prob") or 0))
    n = min(n, len(ordered))
    if n < 2:
        return ordered
    step = (len(ordered) - 1) / (n - 1)
    return [ordered[round(i * step)] for i in range(n)]


def receipt():
    """Graded calls, wins and losses in the same weight. The identity card."""
    d = _graded()
    all_picks = [x for x in ((d or {}).get("picks") or [])
                 if x.get("model") == INDEPENDENT] or ((d or {}).get("picks") or [])
    if len(all_picks) < 4:
        return None
    slate = d.get("slate_id", "")
    replay = slate.upper().startswith("REPLAY")
    won = sum(1 for x in all_picks if x.get("won"))
    shown = _sample(all_picks, 6)

    c = Card("result receipt")
    p = c.pad
    c.d.text((p - 4, p + 66), "RESULT RECEIPT", font=display(92), fill=INK)
    c.label((p, p + 180), f"{slate} · {INDEPENDENT} · {won}-{len(all_picks) - won} "
                          f"on the full slate", DIM, 20)
    if replay:
        c.label((p, p + 212), "replayed on sealed historical data — not a live slate",
                LOSS, 18)

    cols = (p, 520, 760, 990, 1240)
    y = p + 252
    for lab, x in zip(("matchup", "call", "model", "ref price", "result"), cols):
        c.label((x, y), lab, DIM, 18)
    y += 30
    c.rule(p, y, c.w - p)

    for x in shown:
        c.d.text((cols[0], y + 16), x.get("matchup", ""), font=body(26), fill=INK2)
        c.d.text((cols[1], y + 16), x.get("pick", ""), font=body(26, "medium"), fill=INK)
        c.d.text((cols[2], y + 18), f"{(x.get('prob') or 0) * 100:.1f}%",
                 font=mono(24), fill=INK2)
        c.d.text((cols[3], y + 18), am(x.get("reference_price")), font=mono(24), fill=INK2)
        w = x.get("won")
        col = BRAND if w else LOSS
        c.d.rounded_rectangle([cols[4], y + 8, cols[4] + 116, y + 48], radius=4,
                              fill=(10, 30, 26) if w else (38, 14, 16), outline=col)
        c.tracked((cols[4] + 22 if w else cols[4] + 18, y + 13),
                  "WIN" if w else "LOSS", mono(21, True), col, 3)
        y += 62
        c.rule(p, y, c.w - p, (20, 23, 27))

    c.label((p, c.floor - 6), "we show the wins. we show the losses. that's sooth.",
            INK2, 20)

    cap = (f"Graded calls from {slate} — {INDEPENDENT}, the model that never "
           f"sees the line.\n\n"
           f"{won}-{len(all_picks) - won} on the full slate. The six on the card "
           f"are spread across the confidence range, most confident to least, so "
           f"this is not a highlight reel.\n\n"
           + ("This is a replay on sealed historical data, labelled as one — not "
              "a live slate.\n\n" if replay else "")
           + "Losses get the same graphic as wins. Every one is still on the "
             "site.\n\nsooth.bet/verify")
    return {"key": f"receipt-{slate}", "title": "Result receipt", "caption": cap,
            "img": c.done()}


# ================================================== 09 — WHAT THE MODEL SEES

def modelsees():
    """The teaching card. Uses a real observed move as its diagram."""
    ex = None
    for e in load("timeline.json").get("events") or []:
        ml = (e.get("markets") or {}).get("moneyline") or {}
        pts = [v for _, v in (ml.get("consensus") or []) if isinstance(v, (int, float))]
        if len(pts) >= 8 and (ml.get("n_books") or 0) >= 5 and abs(pts[-1] - pts[0]) >= 1.0:
            ex = (e, pts, ml)
            break
    if not ex:
        return None
    e, pts, ml = ex

    c = Card("what the model sees")
    p = c.pad
    c.d.text((p - 4, p + 62), "WHY CLOSING", font=display(92), fill=INK)
    c.d.text((p - 4, p + 152), "LINE VALUE MATTERS", font=display(92), fill=INK)

    y, x1, x2 = p + 316, p + 46, 720
    up = pts[-1] >= pts[0]
    y1, y2 = (y + 56, y + 6) if up else (y + 6, y + 56)
    c.d.line([x1, y1, x2, y2], fill=STROKE, width=3)
    for lab, xx, yy, val, col in (("EARLIEST", x1, y1, f"{pts[0]:.1f}%", INK2),
                                  ("LATEST", x2, y2, f"{pts[-1]:.1f}%", BRAND)):
        c.d.ellipse([xx - 13, yy - 13, xx + 13, yy + 13], fill=col)
        c.label((xx - 26, yy - 78), lab, DIM, 19)
        c.d.text((xx - 26, yy - 50), val, font=mono(27, True), fill=col)
    c.label((x1 - 46, y + 114), f"{fixture(str(e.get('sport', '')), e.get('away', ''), e.get('home', ''))} "
                                f"· {len(pts)} hourly readings · our own capture", DIM, 18)

    c.para((p, p + 500), "If you take a price and the market then moves past you, "
                         "you got the better of it — whatever the game does. That "
                         "is closing line value, and over a season it predicts a "
                         "bettor's results better than their win rate does.\n\n"
                         "It is also why we seal every prediction before kickoff "
                         "and publish the reference price. A number that can move "
                         "after the fact proves nothing.",
           body(27), INK2, max_w=1080, lead=42, limit=c.floor)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    cap = ("Closing line value, in one graphic.\n\n"
           f"{fixture(str(e.get('sport', '')), e.get('away', ''), e.get('home', ''))} "
           f"was at {pts[0]:.1f}% implied at the earliest reading in our capture "
           f"window and sits at {pts[-1]:.1f}% now — {len(pts)} hourly readings. "
           "Anyone who priced it early got the better of the market, whatever the "
           "game does.\n\n"
           "Over a season, CLV predicts a bettor's results better than their win "
           "rate does. It is why we seal predictions before kickoff and publish "
           "the reference price.\n\nsooth.bet/verify")
    return {"key": f"sees-clv-{stamp}", "title": "What the model sees",
            "caption": cap, "img": c.done()}


# =========================================================== 10 — SLATE RECAP

def recap():
    """End-of-slate dashboard. The biggest miss is as large as the biggest hit."""
    d = _graded()
    picks = (d or {}).get("picks") or []
    if len(picks) < 4:
        return None
    slate = d.get("slate_id", "")
    models = d.get("by_model") or {}
    wins = [x for x in picks if x.get("won")]
    losses = [x for x in picks if not x.get("won")]
    hit = max(wins, key=lambda x: x.get("prob") or 0) if wins else None
    miss = max(losses, key=lambda x: x.get("prob") or 0) if losses else None

    c = Card("slate recap")
    p = c.pad
    c.d.text((p - 4, p + 70), "SLATE RECAP", font=display(94), fill=INK)
    c.label((p, p + 186), f"{slate} · {d.get('n_settled', 0)} settled", DIM, 20)

    cells = [("PREDICTIONS", str(d.get("n_predictions", 0)), INK),
             ("SETTLED", str(d.get("n_settled", 0)), INK)]
    for name, m in list(models.items())[:2]:
        cells.append((name.upper()[:18], str(m.get("record", "—")),
                      BRAND if (m.get("win_pct") or 0) >= 0.5 else LOSS))
    x = p
    for lab, val, col in cells[:4]:
        c.panel((x, p + 240, x + 320, p + 388))
        c.label((x + 26, p + 268), lab, DIM, 18)
        c.d.text((x + 22, p + 296), val, font=display(70), fill=col)
        x += 340

    briers = [m.get("brier") for m in models.values() if m.get("brier")]
    if briers:
        c.label((p, p + 436), "mean brier · lower is better", DIM, 19)
        c.d.text((p, p + 466), f"{sum(briers) / len(briers):.3f}",
                 font=display(74), fill=INK2)
        c.label((p, p + 556), f"{len(wins)} won · {len(losses)} lost", DIM, 19)

    for lab, x_, col, item in (("BIGGEST HIT", 700, BRAND, hit),
                               ("BIGGEST MISS", 1080, LOSS, miss)):
        if not item:
            continue
        c.panel((x_, p + 428, x_ + 350, p + 632), PANEL, col)
        c.label((x_ + 24, p + 456), lab, col, 19)
        c.d.text((x_ + 22, p + 486), f"{(item.get('prob') or 0) * 100:.1f}%",
                 font=display(64), fill=col)
        c.para((x_ + 24, p + 566), f"{item.get('matchup', '')} · "
                                   f"{item.get('pick', '')}",
               body(21), INK2, max_w=302, lead=28, limit=p + 626)

    c.label((p, c.floor - 6), "sealed before kickoff · graded in public · "
                              "the miss is the point", DIM, 19)

    parts = [f"{slate} — graded.", ""]
    for name, m in list(models.items())[:2]:
        parts.append(f"{name}: {m.get('record', '')} "
                     f"({(m.get('win_pct') or 0) * 100:.1f}%), brier "
                     f"{m.get('brier', 0):.3f}")
    if miss:
        parts += ["", f"Biggest miss: {miss.get('matchup', '')} · "
                      f"{miss.get('pick', '')} at "
                      f"{(miss.get('prob') or 0) * 100:.1f}%. It lost."]
    parts += ["", "Every prediction was sealed before kickoff and every one is "
                  "still published, including that one.", "", "sooth.bet/verify"]
    return {"key": f"recap-{slate}", "title": "Slate recap",
            "caption": "\n".join(parts), "img": c.done()}


REGISTRY = {"board": board, "board-ig": board_portrait, "signal": signal, "matchup": matchup,
            "onestat": onestat, "market": marketwatch, "prop": proplab,
            "mvm": modelvmarket, "receipt": receipt, "sees": modelsees,
            "recap": recap}
