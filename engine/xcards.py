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

from engine import timefmt
from engine.xkit import (BG, BRAND, DIM, INK, INK2, LOSS, PANEL, PANEL2, PUSH,
                         STROKE, Card, body, crest, display, headshot, load, mono,
                         team_abbr)

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
        return timefmt.strftime(t.astimezone(), "%a %-I:%M%p").upper()
    except Exception:
        return "—"


def fixture(sport: str, away: str, home: str) -> str:
    """'A at B' for a venue sport, 'A vs B' for a fight. Two fighters do not
    play at each other's house."""
    return f"{away} {'vs' if (sport or '').lower() in COMBAT else 'at'} {home}"


def abbr(name: str, cap: int = 20) -> str:
    return name if len(name) <= cap else name[:cap - 1] + "."


# ====================================== 01 — THE BOARD, against the reference

def board_ref():
    """Today's board the way the reference sheet draws it.

    The differences from the first pass are all deliberate and all came from
    the sheet: the whole post sits in a bordered container; the matchup column
    is two CRESTS rather than two team names, which is what makes the table
    scannable at thumbnail size; and the columns are SPREAD / TOTAL /
    MONEYLINE, which is how football is actually discussed, instead of the
    shop-gap arithmetic the first version led with.

    Reads engine/nflboard.py's feed, so the spread and total are our own
    hourly ESPN capture and the moneyline is the multi-book de-vigged number
    wherever more than one book quoted.
    """
    d = load("nflboard.json")
    games = [g for g in (d.get("games") or []) if g.get("spread") and g.get("total")]
    if len(games) < 4:
        return None
    games.sort(key=lambda g: g["kickoff"])
    shown = games[:5]

    # the games worth a second look are the ones the market changed its mind
    # about, which is a fact about the market rather than an opinion about them
    movers = sorted((g for g in games if (g.get("spread") or {}).get("move_pts")),
                    key=lambda g: -abs(g["spread"]["move_pts"]))[:3]

    c = Card("01 the board", framed=True)
    p = c.pad
    right = c.frame[2] - 42

    c.d.text((p - 3, p + 44), "TODAY'S BOARD", font=display(80), fill=INK)
    c.label((p, p + 150), f"week {shown[0].get('week', '')} · "
                          f"{len(games)} games priced · spread & total: "
                          f"{shown[0]['spread'].get('book', '')}", DIM, 19)

    COLS = (p, 470, 640, 860, 1030)
    y = p + 202
    for lab, x in zip(("matchup", "start", "spread", "total", "moneyline"), COLS):
        c.label((x, y), lab, DIM, 18)
    y += 28
    c.rule(p, y, right)

    for g in shown:
        sp, to = g["spread"], g["total"]
        ml = (g.get("moneyline") or {}).get("sides") or {}
        aw, hm = g["away"], g["home"]
        aab, hab = team_abbr(aw, "nfl"), team_abbr(hm, "nfl")

        # crest pair — the reference's matchup column carries no team text
        c.paste(crest(aw, "nfl"), (p, y + 20, 54, 54))
        c.d.text((p + 68, y + 30), "@", font=display(38), fill=DIM)
        c.paste(crest(hm, "nfl"), (p + 108, y + 20, 54, 54))
        c.d.text((p + 178, y + 24), aab, font=body(23, "medium"), fill=INK2)
        c.d.text((p + 178, y + 52), hab, font=body(23, "medium"), fill=INK2)

        c.d.text((COLS[1], y + 36), clock(g["kickoff"]), font=mono(21), fill=INK2)

        fav = team_abbr(sp.get("favourite", ""), "nfl")
        c.d.text((COLS[2], y + 32), f"{fav} {sp.get('favourite_line')}",
                 font=mono(26, True), fill=INK)
        mv = sp.get("move_pts")
        if mv:
            c.d.text((COLS[2], y + 62), f"open {sp.get('open_home')}",
                     font=mono(17), fill=DIM)

        c.d.text((COLS[3], y + 32), f"{to.get('line')}", font=mono(26, True), fill=INK)
        c.d.text((COLS[3], y + 62), "o/u", font=mono(17), fill=DIM)

        for i, (name, ab) in enumerate(((aw, aab), (hm, hab))):
            side = ml.get(name) or {}
            c.d.text((COLS[4], y + 22 + i * 30), ab, font=mono(20), fill=DIM)
            c.d.text((COLS[4] + 62, y + 22 + i * 30), am(side.get("best_price")),
                     font=mono(21, True), fill=INK if side.get("best_price") else DIM)
        # best-of-N is the claim; naming the book for each side as well made the
        # cell three columns deep and the reference's is two
        n = (g.get("moneyline") or {}).get("n_books") or 0
        c.d.text((COLS[4] + 168, y + 36), f"best of {n}" if n > 1 else "1 book",
                 font=mono(18), fill=DIM)

        y += 96
        c.rule(p, y, right, (20, 23, 27))

    # the chip strip, straight off the sheet
    cy = y + 30
    lab = "THE MARKET MOVED ON"
    c.tracked((p, cy + 12), lab, mono(18), DIM, 3)
    cx = p + c.track_w(lab, mono(18), 3) + 34      # measured, not guessed
    for g in movers:
        sp = g["spread"]
        txt = (f"{team_abbr(g['away'], 'nfl')} @ {team_abbr(g['home'], 'nfl')}  "
               f"{sp['move_pts']:+.1f}")
        w = c.d.textlength(txt, font=mono(20, True)) + 44
        c.d.rounded_rectangle([cx, cy, cx + w, cy + 44], radius=5,
                              fill=PANEL, outline=STROKE)
        c.d.text((cx + 22, cy + 10), txt, font=mono(20, True), fill=BRAND)
        cx += w + 16

    top = movers[0] if movers else shown[0]
    sp = top["spread"]
    if movers:
        line = (f"{top['away']} at {top['home']} opened "
                f"{team_abbr(top['home'], 'nfl')} {sp['open_home']} and is "
                f"{team_abbr(top['home'], 'nfl')} {sp['home']} now.")
    else:
        line = (f"{sp['favourite']} {sp['favourite_line']}, "
                f"total {top['total']['line']}.")
    cap = (f"Week {shown[0].get('week', '')} is on the board — {len(games)} games, "
           f"spread and total from our own hourly capture.\n\n"
           f"{line}\n\nsooth.bet/board")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return {"key": f"boardref-{stamp}", "title": "Today's board", "caption": cap,
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



def prob_to_spread(p_home: float, sd: float = 13.86) -> float:
    """A win probability expressed as a point spread.

    Margin of victory in the NFL is roughly normal about the spread with a
    standard deviation near 13.9 points — the figure every published
    spread-to-moneyline table is built on. Inverting it turns our model's
    probability into the unit the sport is actually discussed in.

    It is a CONVERSION, not a second model, and the cards say so. Negative
    means the home team is favoured, matching the board's own convention.
    """
    from statistics import NormalDist
    p = min(max(p_home, 0.001), 0.999)
    return -NormalDist().inv_cdf(p) * sd


def _nfl_join() -> list[dict]:
    """Games where we hold both the market's spread and our own number.

    nflboard.json names teams in full, best_lines.json in abbreviations, so the
    join goes through the same club index the crests come from rather than a
    hand-kept mapping that would rot the first time a team moved city.
    """
    board = load("nflboard.json").get("games") or []
    ours = {}
    for g in load("best_lines.json").get("games") or []:
        if g.get("our_prob") and g.get("home") and g.get("away"):
            ours[(g["away"], g["home"])] = g

    out = []
    for b in board:
        sp = b.get("spread") or {}
        if sp.get("home") is None:
            continue
        key = (team_abbr(b["away"], "nfl"), team_abbr(b["home"], "nfl"))
        o = ours.get(key)
        if not o:
            continue
        p_home = o["our_prob"] if o.get("pick") == key[1] else 1 - o["our_prob"]
        model = prob_to_spread(p_home)
        out.append({**b, "model_home": round(model, 1), "p_home": p_home,
                    "edge_pts": round(sp["home"] - model, 1)})
    out.sort(key=lambda g: -abs(g["edge_pts"]))
    return out


def _game_strip(c, g, y):
    """A bordered strip carrying the rest of the game's market.

    Three cards told their story by roughly two thirds of the frame and left
    the last band empty, which is the gap between a graphic and a slide. The
    remaining markets are the obvious thing to put there: real, already on the
    feed, and the context a reader wants next.
    """
    p, right = c.pad, c.frame[2] - 42
    to = g.get("total") or {}
    ml = (g.get("moneyline") or {}).get("sides") or {}
    n = (g.get("moneyline") or {}).get("n_books") or 0
    hab, aab = team_abbr(g["home"], "nfl"), team_abbr(g["away"], "nfl")

    # stop short of the bottom-right corner: the wordmark lives there, and a
    # full-width strip ending eight pixels above it reads as a collision even
    # when the boxes do not actually touch
    right = right - 200
    c.panel((p, y, right, y + 96))
    cells = [("TOTAL", f"{to.get('line', '—')}")]
    for name, ab in ((g["away"], aab), (g["home"], hab)):
        side = ml.get(name) or {}
        cells.append((f"{ab} MONEYLINE", am(side.get("best_price"))))
    if to.get("move_pts"):
        cells.append(("TOTAL MOVED", f"{to['move_pts']:+g}"))
    cells.append(("QUOTED BY", f"{n} book{'s' if n != 1 else ''}"))

    step = (right - p) / len(cells)
    for i, (lab, val) in enumerate(cells):
        x = p + 30 + i * step
        c.label((x, y + 24), lab, DIM, 17)
        c.d.text((x - 2, y + 46), val, font=mono(30, True), fill=INK)


# ========================================================= 02 — SOOTH SIGNAL

def signal():
    """One game where our number and the market's number disagree, in POINTS.

    The reference sheet states this card in spread points (BUF -2.5 market,
    -4.1 model) and it is right to: implied-probability points, which the first
    pass led with, are the same fact in a unit nobody argues in.
    """
    games = _nfl_join()
    if not games:
        return None
    g = games[1] if len(games) > 1 else games[0]      # MODEL VS MARKET takes the widest
    sp = g["spread"]
    aw, hm = g["away"], g["home"]
    aab, hab = team_abbr(aw, "nfl"), team_abbr(hm, "nfl")
    mkt_fav, mkt_line = (hab, sp["home"]) if sp["home"] < 0 else (aab, -sp["home"])
    mdl_fav, mdl_line = ((hab, g["model_home"]) if g["model_home"] < 0
                         else (aab, -g["model_home"]))
    diff = abs(g["edge_pts"])

    c = Card("02 sooth signal", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 44), "SOOTH SIGNAL", font=display(80), fill=INK)

    c.paste(crest(aw, "nfl"), (p, p + 142, 68, 68))
    c.d.text((p + 84, p + 156), "@", font=display(44), fill=DIM)
    c.paste(crest(hm, "nfl"), (p + 134, p + 142, 68, 68))
    c.d.text((p + 224, p + 152), f"{aab} @ {hab}", font=display(54), fill=INK)
    c.label((p + 226, p + 210), clock(g["kickoff"]), DIM, 19)

    px, py, pw = p, p + 262, 660
    c.panel((px, py, px + pw, py + 258))
    rows = ((f"MARKET  {sp.get('book', '')}", f"{mkt_fav} {mkt_line}", INK),
            ("SOOTH MODEL", f"{mdl_fav} {mdl_line}", INK),
            ("DIFFERENCE", f"{diff:.1f} PTS", BRAND))
    ry = py + 26
    for i, (lab, val, col) in enumerate(rows):
        c.label((px + 30, ry + 12), lab, DIM, 18)
        vw = c.d.textlength(val, font=display(52))
        c.d.text((px + pw - 30 - vw, ry - 4), val, font=display(52), fill=col)
        ry += 78
        if i < 2:
            c.rule(px + 30, ry - 12, px + pw - 30, (26, 29, 34))

    rx = 790
    c.label((rx, p + 146), "what the ratings say", BRAND, 20)
    ts = load("teamstats-nfl.json").get("teams") or {}
    c.para((rx, p + 186), _why_nfl(ts, aab, hab, aw, hm),
           body(26), INK2, max_w=right - rx, lead=40, limit=p + 372)

    # the market's own price history, so the right column carries evidence
    # rather than one paragraph and a lot of ground
    pts = _ml_series(aw, hm)
    sx, sy, sw, sh = rx, p + 400, right - rx, 148
    c.panel((sx - 24, sy - 30, right, sy + sh + 56))
    if len(set(pts[-40:])) >= 3:
        c.sparkline((sx, sy, sw, sh), pts[-40:], BRAND)
        c.label((sx, sy + sh + 20), f"{hab} moneyline · {len(pts[-40:])} hourly "
                                    f"readings · our own capture", DIM, 17)
    else:
        c.label((sx, sy + 20), "our win probability converted to a spread at", DIM, 18)
        c.label((sx, sy + 48), "13.9 points of margin — the standard", DIM, 18)
        c.label((sx, sy + 76), "conversion, not a second model", DIM, 18)
        c.label((sx, sy + sh + 20), "it never sees the line", BRAND, 17)

    _game_strip(c, g, p + 626)

    cap = (f"{aab} @ {hab}.\n\n"
           f"{sp.get('book', 'The book')} has {mkt_fav} {mkt_line}. "
           f"Our model, which never sees the line, has {mdl_fav} {mdl_line}. "
           f"A {diff:.1f} point disagreement.\n\nsooth.bet/edges")
    return {"key": f"signal-{g['event_id']}-{diff}", "title": "Sooth Signal",
            "caption": cap, "img": c.done()}


def _ml_series(away: str, home: str) -> list:
    for e in load("timeline.json").get("events") or []:
        if e.get("away") == away and e.get("home") == home:
            return [v for _, v in ((e.get("markets") or {}).get("moneyline") or {}
                                   ).get("consensus") or []
                    if isinstance(v, (int, float))]
    return []


def _why_nfl(ts: dict, away: str, home: str, away_full: str = "",
             home_full: str = "") -> str:
    """teamstats-nfl.json is keyed by ABBREVIATION (BUF), not by club name."""
    a, h = ts.get(away) or {}, ts.get(home) or {}
    ra, rh = (a.get("rating") or {}), (h.get("rating") or {})
    if not ra or not rh:
        return ("The model reads walk-forward team ratings and the market's own "
                "price history. It has no ratings for this pairing yet.")
    na, nh = ra.get("net", 0), rh.get("net", 0)
    an, hn = away_full or away, home_full or home
    lead, trail = (hn, an) if nh > na else (an, hn)
    hi, lo = max(nh, na), min(nh, na)
    return (f"{lead} rates {hi:+.3f} net EPA per play against {trail}'s "
            f"{lo:+.3f}, walk-forward — built only from games played before "
            f"the one being priced.\n\n"
            f"That gap is most of the model's number here. It carries no "
            f"injury news and no line movement.")


# ================================================ 03 — MATCHUP INTELLIGENCE

KEYS = ("off_epa_pp", "def_epa_pp", "yards_pp", "first_down_rate",
        "explosive_rate", "turnover_rate")


def matchup():
    """Two teams, six measures, mirrored bars — the one card that is a diagram."""
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

    c = Card("03 matchup intelligence", framed=True)
    p, right = c.pad, c.frame[2] - 42
    mid = (p + right) // 2
    c.d.text((p - 3, p + 40), "MATCHUP INTELLIGENCE", font=display(74), fill=INK)

    # crests at reference scale — they are the identity of the card, not garnish
    c.paste(crest(away, "nfl"), (p, p + 128, 96, 96))
    c.d.text((p + 118, p + 148), st["away"].get("abbr", ""), font=display(66), fill=INK)
    hab = st["home"].get("abbr", "")
    hw = c.d.textlength(hab, font=display(66))
    c.paste(crest(home, "nfl"), (right - 96, p + 128, 96, 96))
    c.d.text((right - 118 - hw, p + 148), hab, font=display(66), fill=INK)
    c.d.text((mid - 26, p + 160), "VS", font=display(44), fill=DIM)

    y = p + 268
    for k in keys:
        m = metrics.get(k, {"label": k, "better": "high", "dp": 3})
        av, hv = as_.get(k), hs.get(k)
        fa, fh = _pair(av, hv, m.get("better"))
        dp = m.get("dp", 3)
        at, ht = f"{av:.{dp}f}", f"{hv:.{dp}f}"
        aw_ = c.d.textlength(at, font=mono(25, True))
        c.d.text((p + 150 - aw_, y - 5), at, font=mono(25, True), fill=INK2)
        c.hbar(p + 174, y, 330, 18, fa, BRAND if fa >= fh else LOSS, rtl=True)
        lab = m.get("label", k).upper()
        lw = c.track_w(lab, mono(19), 3)
        c.tracked((mid - lw / 2, y - 3), lab, mono(19), DIM, 3)
        c.hbar(right - 504, y, 330, 18, fh, BRAND if fh > fa else LOSS)
        c.d.text((right - 150, y - 5), ht, font=mono(25, True), fill=INK2)
        y += 66

    c.rule(p, y + 12, right, (26, 29, 34))
    c.label((p, y + 34), f"season {st.get('basis_season', '')} · nflverse "
                         f"play-by-play · teal is the better of the two", DIM, 18)

    cap = (f"{team_abbr(away, 'nfl')} at {team_abbr(home, 'nfl')}, six measures, "
           f"same scale.\n\nSeason {st.get('basis_season', '')} on nflverse "
           f"play-by-play. The numbers are printed so you can check the bars "
           f"against them.\n\nsooth.bet/research")
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


# ---- the games the market changed its mind about ---------------------------

def _movers() -> list[dict]:
    g = [x for x in (load("nflboard.json").get("games") or [])
         if (x.get("spread") or {}).get("move_pts")]
    g.sort(key=lambda x: -abs(x["spread"]["move_pts"]))
    return g


# ============================================================= 04 — ONE STAT

def onestat():
    """One number, big enough to read at thumbnail size. Nothing else."""
    mv = _movers()
    if not mv:
        return None
    g = mv[0]
    sp = g["spread"]
    aw, hm = g["away"], g["home"]
    hab, aab = team_abbr(hm, "nfl"), team_abbr(aw, "nfl")
    moved = abs(sp["move_pts"])
    toward = (hm if sp["move_pts"] < 0 else aw).split()[-1]

    c = Card("04 one stat", framed=True)
    p, right = c.pad, c.frame[2] - 42
    mid = (p + right) // 2

    fig = f"{moved:.1f}"
    f = display(300)
    fw = c.d.textlength(fig, font=f)
    uw = c.d.textlength("PTS", font=display(84))
    x0 = mid - (fw + 26 + uw) / 2
    c.d.text((x0, p + 116), fig, font=f, fill=BRAND)
    c.d.text((x0 + fw + 26, p + 210), "PTS", font=display(84), fill=DIM)

    for i, ln in enumerate((f"THE MARKET HAS MOVED {moved:.1f} POINTS TOWARD "
                            f"{toward.upper()}", "SINCE THIS LINE OPENED")):
        lw = c.track_w(ln, body(31, "medium"), 2)
        c.tracked((mid - lw / 2, p + 420 + i * 48), ln, body(31, "medium"), INK, 2)

    # the fixture, with its crests, under the statement
    label = f"{aab} @ {hab}"
    lw = c.d.textlength(label, font=display(50))
    c.d.text((mid - lw / 2, p + 540), label, font=display(50), fill=INK2)
    c.paste(crest(aw, "nfl"), (mid - lw / 2 - 96, p + 528, 66, 66))
    c.paste(crest(hm, "nfl"), (mid + lw / 2 + 30, p + 528, 66, 66))

    c.rule(mid - 110, p + 624, mid + 110, STROKE)
    src = (f"open {sp['open_home']} · now {sp['home']} · {sp.get('book', '')} "
           f"· our own hourly capture").upper()
    sw = c.track_w(src, mono(19), 3)
    c.tracked((mid - sw / 2, p + 650), src, mono(19), DIM, 3)

    cap = (f"{moved:.1f} points.\n\n"
           f"That is how far the market has moved toward {toward} in "
           f"{aab} @ {hab} since the line opened — {hab} {sp['open_home']} "
           f"then, {hab} {sp['home']} now.\n\nsooth.bet/board")
    return {"key": f"onestat-{g['event_id']}-{moved}", "title": "One stat",
            "caption": cap, "img": c.done()}


# ========================================================= 05 — MARKET WATCH

def marketwatch():
    """A line that moved, with the shape of the move beside it."""
    mv = _movers()
    if not mv:
        return None
    # prefer a game whose moneyline series actually varies, so the chart has a
    # shape; every NFL spread we hold is flat inside our own window because the
    # move happened before we started polling that event
    series = {}
    for e in load("timeline.json").get("events") or []:
        pts = [v for _, v in ((e.get("markets") or {}).get("moneyline") or {}).get(
            "consensus") or [] if isinstance(v, (int, float))]
        if len(pts) >= 8:
            series[(e.get("away"), e.get("home"))] = pts
    # the headline is the move, so the biggest mover wins outright; the chart
    # falls back to a two-point slope when that game's series is flat
    g = mv[0]
    pts = series.get((g["away"], g["home"]), [])
    sp = g["spread"]
    hab, aab = team_abbr(g["home"], "nfl"), team_abbr(g["away"], "nfl")

    c = Card("05 market watch", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 44), "MARKET WATCH", font=display(80), fill=INK)
    c.paste(crest(g["away"], "nfl"), (p, p + 142, 56, 56))
    c.d.text((p + 72, p + 150), f"{aab} @ {hab}", font=display(46), fill=INK2)
    c.paste(crest(g["home"], "nfl"),
            (p + 92 + c.d.textlength(f"{aab} @ {hab}", font=display(46)), p + 142, 56, 56))

    col = BRAND if sp["move_pts"] < 0 else LOSS
    y = p + 234
    for lab, val, colr in (("OPENED", f"{hab} {sp['open_home']}", INK2),
                           ("NOW", f"{hab} {sp['home']}", INK),
                           ("MOVE", f"{sp['move_pts']:+.1f} PTS", col)):
        c.panel((p, y, p + 400, y + 118))
        c.label((p + 26, y + 22), lab, DIM, 18)
        c.d.text((p + 22, y + 48), val, font=display(56), fill=colr)
        y += 134

    cx, cy, cw, ch = 560, p + 250, right - 560, 300
    c.panel((cx - 28, cy - 40, right, cy + ch + 76))
    if len(set(pts[-40:])) >= 3:
        c.sparkline((cx, cy, cw, ch), pts[-40:], BRAND)
        note = (f"moneyline, {len(pts[-40:])} hourly readings, our own capture")
    else:
        # two real points beat a flat line pretending to be a chart
        x1, x2 = cx + 40, cx + cw - 60
        up = sp["move_pts"] < 0
        y1, y2 = (cy + ch - 60, cy + 60) if up else (cy + 60, cy + ch - 60)
        c.d.line([x1, y1, x2, y2], fill=STROKE, width=3)
        for lab, xx, yy, val, cc in (("OPEN", x1, y1, str(sp["open_home"]), INK2),
                                     ("NOW", x2, y2, str(sp["home"]), BRAND)):
            c.d.ellipse([xx - 14, yy - 14, xx + 14, yy + 14], fill=cc)
            c.label((xx - 28, yy - 84), lab, DIM, 18)
            c.d.text((xx - 28, yy - 56), val, font=display(44), fill=cc)
        note = f"{hab} spread, open to now, {sp.get('book', '')}"
    c.label((cx, cy + ch + 34), note, DIM, 18)

    _game_strip(c, g, p + 634)

    cap = (f"{aab} @ {hab} — the line moved.\n\n"
           f"{hab} opened {sp['open_home']} and is {sp['home']} now, a "
           f"{sp['move_pts']:+.1f} point move at {sp.get('book', 'the book')}.\n\n"
           f"We log what moved. We do not claim to know why.\n\nsooth.bet/timeline")
    return {"key": f"move-{g['event_id']}-{sp['move_pts']}",
            "title": "Market watch", "caption": cap, "img": c.done()}


# ======================================================== 06 — PLAYER PROP LAB

def proplab():
    """One player, one line, the game log behind it."""
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

    c = Card("06 player prop lab", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 44), "PLAYER PROP LAB", font=display(80), fill=INK)

    px, py, pw, ph = p, p + 152, 430, 520
    c.panel((px, py, px + pw, py + ph))
    if not c.paste(headshot(player), (px + 34, py + 22, pw - 68, ph - 152)):
        ini = "".join(w[0] for w in player.split()[:2])
        iw = c.d.textlength(ini, font=display(170))
        c.d.text((px + (pw - iw) / 2, py + 130), ini, font=display(170), fill=PANEL2)
    c.d.text((px + 30, py + ph - 108), abbr(player, 22), font=body(31, "medium"), fill=INK)
    nick = lambda n: (n or "").split()[-1]
    c.label((px + 30, py + ph - 62),
            f"{b.get('label', '')} · {nick(e.get('away'))} at {nick(e.get('home'))}",
            DIM, 18)

    rx = px + pw + 54
    c.label((rx, p + 156), pp.get("market_label", pp.get("market", "")), BRAND, 22)
    c.d.text((rx - 3, p + 188), f"OVER {pp.get('line')}", font=display(96), fill=INK)

    rows = [("BEST PRICE", f"{am(pp['over'].get('best_price'))}  "
                           f"{book(pp['over'].get('best_book', ''))}", INK),
            ("DE-VIGGED FAIR", am(pp["over"].get("fair_price")), INK2),
            ("LAST 5", f"{hit['l5']['over']} of {hit['l5']['n']}", INK),
            ("LAST 10", f"{hit['l10']['over']} of {hit['l10']['n']}", INK),
            ("SEASON", f"{s['over']} of {s['n']}", INK)]
    y = p + 316
    for lab, val, col in rows:
        c.label((rx, y + 8), lab, DIM, 19)
        vw = c.d.textlength(val, font=mono(28, True))
        c.d.text((right - vw, y - 2), val, font=mono(28, True), fill=col)
        y += 62
        c.rule(rx, y - 16, right, (26, 29, 34))

    pct = s["over"] / s["n"] * 100
    c.panel((rx, y + 12, right, y + 108), PANEL, STROKE)
    c.label((rx + 26, y + 36), "season hit rate", DIM, 18)
    pw_ = c.d.textlength(f"{pct:.0f}%", font=display(56))
    c.d.text((right - 30 - pw_, y + 30), f"{pct:.0f}%", font=display(56), fill=BRAND)
    c.label((p, c.floor - 4), "game log: statsapi.mlb.com · a hit rate is history, "
                              "not a projection", DIM, 18)

    cap = (f"{player} — {pp.get('market_label', '')} {pp.get('line')}.\n\n"
           f"Over has hit {s['over']} of {s['n']} this season ({pct:.0f}%), "
           f"{hit['l10']['over']} of {hit['l10']['n']} in the last ten. Best "
           f"price {am(pp['over'].get('best_price'))} at "
           f"{book(pp['over'].get('best_book', ''))}, de-vigged fair "
           f"{am(pp['over'].get('fair_price'))}.\n\nsooth.bet/props")
    return {"key": f"prop-{player}-{pp.get('market')}-{pp.get('line')}",
            "title": "Player prop lab", "caption": cap, "img": c.done()}


# ====================================================== 07 — MODEL VS MARKET

def modelvmarket():
    """Two plates, one delta. Stated in probability, where SIGNAL uses points."""
    games = _nfl_join()
    if not games:
        return None
    g = games[0]
    sp = g["spread"]
    mkt_p = 1 - implied_from_spread(sp["home"])
    ours = g["p_home"]
    delta = (ours - mkt_p) * 100
    aw, hm = g["away"], g["home"]
    aab, hab = team_abbr(aw, "nfl"), team_abbr(hm, "nfl")

    c = Card("07 model vs market", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 44), "MODEL VS MARKET", font=display(80), fill=INK)

    c.paste(crest(aw, "nfl"), (p, p + 142, 62, 62))
    lab = f"{aab} @ {hab}"
    c.d.text((p + 80, p + 148), lab, font=display(50), fill=INK2)
    c.paste(crest(hm, "nfl"),
            (p + 100 + c.d.textlength(lab, font=display(50)), p + 142, 62, 62))
    c.label((p, p + 226), f"{hab} to win · converted from {hab} "
                          f"{sp['home']:+g} at {sp.get('book', '')}", DIM, 19)

    plates = (("MARKET IMPLIED", f"{mkt_p * 100:.1f}%", INK,
               f"{hab} {sp['home']} at {sp.get('book', '')}"),
              ("SOOTH MODEL", f"{ours * 100:.1f}%", BRAND,
               "independent · never sees the line"))
    x, pw = p, 700
    for l, v, col, note in plates:
        c.panel((x, p + 270, x + pw, p + 470))
        c.label((x + 30, p + 296), l, DIM, 19)
        c.d.text((x + 26, p + 324), v, font=display(104), fill=col)
        c.d.text((x + 30, p + 428), note, font=body(21), fill=DIM)
        x += pw + 72

    dcol = BRAND if delta > 0 else LOSS
    c.label((p, p + 492), "delta", DIM, 22)
    c.d.text((p - 3, p + 520), f"{delta:+.1f}%", font=display(104), fill=dcol)
    c.para((p + 440, p + 530), "Percentage points between our number and the "
                               "market's, on the same side of the same game.",
           body(25), DIM, max_w=right - p - 440, lead=38, limit=c.floor)

    _game_strip(c, g, p + 634)

    cap = (f"{aab} @ {hab}.\n\n"
           f"Market implied {mkt_p * 100:.1f}% for {hab}, from the {sp['home']} "
           f"spread. Our model has {ours * 100:.1f}%. Delta {delta:+.1f} points.\n\n"
           f"The model never sees the line before it prices a game. When it "
           f"disagrees this much, one of the two is wrong.\n\nsooth.bet/record")
    return {"key": f"mvm-{g['event_id']}-{round(delta, 1)}",
            "title": "Model vs market", "caption": cap, "img": c.done()}


def implied_from_spread(home_line: float, sd: float = 13.86) -> float:
    """The away team's win probability implied by a home spread.

    The inverse of prob_to_spread, and the reason MODEL VS MARKET can put a
    spread and a probability on the same card without quoting a vig-loaded
    moneyline as if it were fair.
    """
    from statistics import NormalDist
    return NormalDist().cdf(home_line / sd)


# ======================================================= 08 — RESULT RECEIPT

def _graded() -> dict | None:
    """The most recent graded slate. Replays are used and LABELLED as replays."""
    import glob
    from engine.xkit import DATA
    files = sorted(glob.glob(os.path.join(DATA, "*.graded.json")))
    return load(files[-1]) if files else None


def _sample(picks: list, n: int) -> list:
    """An evenly spaced slice of the confidence range.

    Taking the top N by probability is how a receipt becomes a highlight reel:
    the first render showed six calls and all six had won.
    """
    ordered = sorted(picks, key=lambda x: -(x.get("prob") or 0))
    n = min(n, len(ordered))
    if n < 2:
        return ordered
    step = (len(ordered) - 1) / (n - 1)
    return [ordered[round(i * step)] for i in range(n)]


INDEPENDENT = "elo+epa-v1"


def receipt():
    """Graded calls, wins and losses in the same weight. The identity card."""
    d = _graded()
    picks = [x for x in ((d or {}).get("picks") or [])
             if x.get("model") == INDEPENDENT] or ((d or {}).get("picks") or [])
    if len(picks) < 4:
        return None
    slate = d.get("slate_id", "")
    replay = slate.upper().startswith("REPLAY")
    won = sum(1 for x in picks if x.get("won"))
    shown = _sample(picks, 6)

    c = Card("08 result receipt", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 44), "RESULT RECEIPT", font=display(80), fill=INK)
    c.label((p, p + 146), f"{slate} · {INDEPENDENT} · {won}-{len(picks) - won} "
                          f"on the full slate", DIM, 19)
    if replay:
        c.label((p, p + 176), "replayed on sealed historical data — not a live slate",
                LOSS, 18)

    COLS = (p, 520, 800, 1030, 1290)
    y = p + 224
    for lab, x in zip(("matchup", "call", "model", "ref price", "result"), COLS):
        c.label((x, y), lab, DIM, 18)
    y += 28
    c.rule(p, y, right)

    for x in shown:
        c.d.text((COLS[0], y + 18), x.get("matchup", ""), font=body(27), fill=INK2)
        c.d.text((COLS[1], y + 18), x.get("pick", ""), font=body(27, "medium"), fill=INK)
        c.d.text((COLS[2], y + 20), f"{(x.get('prob') or 0) * 100:.1f}%",
                 font=mono(25), fill=INK2)
        c.d.text((COLS[3], y + 20), am(x.get("reference_price")), font=mono(25), fill=INK2)
        w = x.get("won")
        col = BRAND if w else LOSS
        c.d.rounded_rectangle([COLS[4], y + 10, COLS[4] + 132, y + 54], radius=5,
                              fill=(10, 30, 26) if w else (38, 14, 16), outline=col)
        c.tracked((COLS[4] + 26, y + 17), "WIN" if w else "LOSS", mono(22, True), col, 3)
        y += 70
        c.rule(p, y, right, (20, 23, 27))

    c.label((p, y + 26), "we show the wins. we show the losses. that's sooth.",
            INK2, 20)

    cap = (f"{slate}, graded — {INDEPENDENT}, the model that never sees the line.\n\n"
           f"{won}-{len(picks) - won} on the full slate. The six here are spread "
           f"across the confidence range, most confident to least, so this is not "
           f"a highlight reel.\n\n"
           + ("A replay on sealed historical data, labelled as one.\n\n" if replay else "")
           + "sooth.bet/verify")
    return {"key": f"receipt-{slate}", "title": "Result receipt", "caption": cap,
            "img": c.done()}


# ================================================== 09 — WHAT THE MODEL SEES

def modelsees():
    """The teaching card, drawn on a line that really moved."""
    mv = _movers()
    if not mv:
        return None
    g = mv[0]
    sp = g["spread"]
    hab, aab = team_abbr(g["home"], "nfl"), team_abbr(g["away"], "nfl")

    c = Card("09 what the model sees", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 36), "WHY CLOSING", font=display(84), fill=INK)
    c.d.text((p - 3, p + 118), "LINE VALUE MATTERS", font=display(84), fill=INK)

    bx, by, bw, bh = p, p + 248, right - p, 244
    c.panel((bx, by, bx + bw, by + bh))
    x1, x2 = bx + 150, bx + bw - 210
    up = sp["move_pts"] < 0
    y1, y2 = (by + bh - 74, by + 74) if up else (by + 74, by + bh - 74)
    c.d.line([x1, y1, x2, y2], fill=STROKE, width=3)
    for lab, xx, yy, val, col in (("OPENED", x1, y1, f"{hab} {sp['open_home']}", INK2),
                                  ("NOW", x2, y2, f"{hab} {sp['home']}", BRAND)):
        c.d.ellipse([xx - 15, yy - 15, xx + 15, yy + 15], fill=col)
        c.label((xx - 30, yy - 86), lab, DIM, 18)
        c.d.text((xx - 30, yy - 58), val, font=display(48), fill=col)
    c.label((bx + 26, by + bh - 36), f"{aab} @ {hab} · {sp.get('book', '')} "
                                     f"· our own hourly capture", DIM, 17)

    c.para((p, p + 538), "If you take a price and the market then moves past you, "
                         "you got the better of it — whatever the game does. That "
                         "is closing line value, and over a season it predicts a "
                         "bettor's results better than their win rate does.\n\n"
                         "It is why we seal every prediction before kickoff and "
                         "publish the reference price.",
           body(27), INK2, max_w=1180, lead=42, limit=c.floor)

    cap = ("Closing line value, in one graphic.\n\n"
           f"{hab} opened {sp['open_home']} and is {sp['home']} now. Anyone who "
           f"took the opening number got the better of the market, whatever the "
           f"game does.\n\nOver a season that predicts results better than a win "
           f"rate does. It is why we seal predictions before kickoff.\n\n"
           "sooth.bet/verify")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
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

    c = Card("10 slate recap", framed=True)
    p, right = c.pad, c.frame[2] - 42
    c.d.text((p - 3, p + 44), "SLATE RECAP", font=display(80), fill=INK)
    c.label((p, p + 148), f"{slate} · {d.get('n_settled', 0)} settled · "
                          f"sealed before kickoff", DIM, 19)

    cells = [("PREDICTIONS", str(d.get("n_predictions", 0)), INK),
             ("SETTLED", str(d.get("n_settled", 0)), INK)]
    for name, m in list(models.items())[:2]:
        cells.append((name.upper()[:18], str(m.get("record", "—")),
                      BRAND if (m.get("win_pct") or 0) >= 0.5 else LOSS))
    x, cw = p, 344
    for lab, val, col in cells[:4]:
        c.panel((x, p + 196, x + cw, p + 344))
        c.label((x + 26, p + 222), lab, DIM, 18)
        c.d.text((x + 22, p + 250), val, font=display(74), fill=col)
        x += cw + 32

    briers = [m.get("brier") for m in models.values() if m.get("brier")]
    if briers:
        c.panel((p, p + 380, p + cw, p + 528))
        c.label((p + 26, p + 406), "mean brier", DIM, 18)
        c.d.text((p + 22, p + 434), f"{sum(briers) / len(briers):.3f}",
                 font=display(74), fill=INK2)
    c.panel((p + cw + 32, p + 380, p + 2 * cw + 32, p + 528))
    c.label((p + cw + 58, p + 406), "won / lost", DIM, 18)
    c.d.text((p + cw + 54, p + 434), f"{len(wins)}-{len(losses)}",
             font=display(74), fill=INK)

    for lab, x_, col, item in (("BIGGEST HIT", p + 2 * (cw + 32), BRAND, hit),
                               ("BIGGEST MISS", p + 3 * (cw + 32), LOSS, miss)):
        if not item:
            continue
        c.panel((x_, p + 380, x_ + cw, p + 528), PANEL, col)
        c.label((x_ + 26, p + 406), lab, col, 18)
        c.d.text((x_ + 22, p + 432), f"{(item.get('prob') or 0) * 100:.1f}%",
                 font=display(66), fill=col)
        c.label((x_ + 26, p + 504), f"{item.get('matchup', '')} · "
                                    f"{item.get('pick', '')}", INK2, 17)

    c.rule(p, p + 576, right, (26, 29, 34))
    c.label((p, p + 600), "every prediction sealed before kickoff, graded in "
                          "public, and still published — including the miss", DIM, 19)

    parts = [f"{slate} — graded.", ""]
    for name, m in list(models.items())[:2]:
        parts.append(f"{name}: {m.get('record', '')} "
                     f"({(m.get('win_pct') or 0) * 100:.1f}%), brier "
                     f"{m.get('brier', 0):.3f}")
    if miss:
        parts += ["", f"Biggest miss: {miss.get('matchup', '')} · "
                      f"{miss.get('pick', '')} at "
                      f"{(miss.get('prob') or 0) * 100:.1f}%. It lost."]
    parts += ["", "Sealed before kickoff. Still published.", "", "sooth.bet/verify"]
    return {"key": f"recap-{slate}", "title": "Slate recap",
            "caption": "\n".join(parts), "img": c.done()}


REGISTRY = {"board": board_ref, "board-ig": board_portrait, "signal": signal,
            "matchup": matchup, "onestat": onestat, "market": marketwatch,
            "prop": proplab, "mvm": modelvmarket, "receipt": receipt,
            "sees": modelsees, "recap": recap}
