"""Turn today's published numbers into post cards for @Soothbet.

    python -m engine.xpost --dry-run        # what would be queued, nothing written
    python -m engine.xpost                  # render cards into the approval queue
    python -m engine.xpost --selfcheck      # offline, no feeds, no network

This writes into the EXISTING queue that ~/sooth-poster/approval_bot.py
watches. It does not post. Nothing here can post: publishing is a Telegram
button tap, and publisher.py is the only thing that talks to X. That gate is
the reason this is safe to run on a schedule.

WHAT IT IS ALLOWED TO SAY
-------------------------
Every card states a fact that is already published on sooth.bet and can be
checked against it — a price gap between books, the model's measured record, a
sealed slate's hash. None of them names a side to back.

The line this must not cross is the whole product's position: sooth.bet is a
research analyzer, not a tip service, and "prop of the day" is a pick no matter
how it is worded. _selfcheck() fails the build if recommendation language
appears in a rendered caption, so the guardrail survives whoever edits the copy
next — the same enforcement engine/watch_email.py already uses.

WHY IT RENDERS AN IMAGE
-----------------------
publisher.py has no text-only path: it always uploads media and attaches it.
That is also the right call for X, where a card carrying one big number
outperforms the same sentence as plain text. The card uses ArchivoBlack, which
is the site's own display face and already sits in the poster rig's asset folder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

from engine.xcards import REGISTRY
from engine.xkit import BANNED, check_caption  # noqa: F401  (re-exported)

# ---- where things live ------------------------------------------------------
# The queue belongs to the poster rig, which is a separate project on purpose:
# it owns the credentials, the Telegram gate and the X client, and none of that
# should be duplicated here.
POSTER = os.path.expanduser("~/sooth-poster")
QUEUE_PENDING = os.path.join(POSTER, "queue", "pending")
FONT_DISPLAY = os.path.join(POSTER, "assets", "fonts", "ArchivoBlack.ttf")
FONT_MONO = "/System/Library/Fonts/Menlo.ttc"

MOVES = "site/public/data/moves.json"
FIGURES = "site/public/data/figures.json"
WATERMARK = "data/xpost_sent.json"

# FROZEN MARKET, from assets/desk.css. Restated rather than imported because
# this is a different runtime; if the site's palette moves, move these too.
BG = (6, 8, 10)
INK = (240, 245, 246)
INK2 = (174, 189, 194)
DIM = (84, 98, 104)
BRAND = (45, 212, 167)
LOSS = (255, 107, 107)

CARD_W, CARD_H = 1600, 900          # 16:9, the aspect X renders largest

# ---- selection --------------------------------------------------------------

def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def biggest_gap(moves: dict) -> dict | None:
    """The largest divergence on the board, one row per event.

    Both feeds are keyed by (event, book), so one game four books repriced
    arrives as four rows — taking the top N without collapsing them fills a
    card with the same matchup repeated, which is what happened on the
    dashboard panel before it was deduped.
    """
    rows = [r for r in (moves.get("divergence") or []) if r.get("move_pts")]
    if not rows:
        return None
    best: dict[str, dict] = {}
    for r in rows:
        k = r.get("event_id") or f"{r.get('home')}|{r.get('away')}"
        if k not in best or (r["move_pts"] or 0) > (best[k]["move_pts"] or 0):
            best[k] = r
    return max(best.values(), key=lambda r: r["move_pts"] or 0)


def record_card(figures: dict) -> dict | None:
    """The measured record — including the half that does not flatter us."""
    res = ((figures.get("evaluation_a") or {}).get("results") or {}).get("independent") or {}
    if not res.get("ats_pct"):
        return None
    return {
        "kind": "record",
        "acc": res.get("accuracy"),
        "ats": res.get("ats_pct"),
        "rec": res.get("ats_record"),
        "n": res.get("n"),
        "be": figures.get("breakeven_ats"),
    }


# ---- copy -------------------------------------------------------------------

def gap_caption(r: dict) -> tuple[str, str, str, str]:
    """(headline, subline, tweet caption, card line).

    The card line and the caption are deliberately different: the card carries
    one short line under the figure, the tweet carries the full text. Passing
    the caption to both produced a run-on card that nearly hit the wordmark."""
    book = r.get("book") or "A book"
    sel = r.get("selection") or "a side"
    pts = r.get("move_pts") or 0
    sport = str(r.get("sport") or "").upper()
    game = f"{r.get('away','')} at {r.get('home','')}".strip()
    price = r.get("to_price")
    head = f"+{pts:.2f} PTS"
    sub = f"{book} vs the consensus"
    card_line = f"{sport} · {game}"
    cap = (
        f"{book} is paying {pts:.2f} points more than the 5-book consensus on "
        f"{sel}"
        + (f" ({price:+d})" if isinstance(price, int) else "")
        + f".\n\n{sport} · {game}\n\n"
        "That is a gap between books, not a view on the game. Prices move — "
        "check the book.\n\nEvery number: sooth.bet/edges"
    )
    return head, sub, cap, card_line


def record_caption(c: dict) -> tuple[str, str, str, str]:
    acc = c["acc"] * 100
    ats = c["ats"] * 100
    be = c["be"] * 100
    head = f"{acc:.1f}%"
    sub = "straight-up accuracy"
    card_line = f"{c['rec']} against the spread · {ats:.1f}% · break-even {be:.2f}%"
    cap = (
        f"Our model picks the winner {acc:.1f}% of the time.\n\n"
        f"It still loses. {c['rec']} against the spread — {ats:.1f}%, where "
        f"{be:.2f}% is break-even at -110. Measured on {c['n']:,} graded games.\n\n"
        "Picking winners and beating a spread are different problems. Both "
        "numbers have been public since day one.\n\nsooth.bet/record"
    )
    return head, sub, cap, card_line


# ---- the card ---------------------------------------------------------------

def render_card(head: str, sub: str, foot: str, accent=BRAND):
    """One number, one line under it, the wordmark. Nothing else.

    Deliberately not a chart. A card is read at thumbnail size in a feed, and
    the only thing that survives that is a single large figure.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    d = ImageDraw.Draw(img)

    f_head = ImageFont.truetype(FONT_DISPLAY, 230)
    f_sub = ImageFont.truetype(FONT_MONO, 46)
    f_foot = ImageFont.truetype(FONT_MONO, 34)
    f_mark = ImageFont.truetype(FONT_DISPLAY, 44)

    pad = 96
    # the one teal rule, top-left — the site's own lit-edge motif
    d.rectangle([pad, pad, pad + 120, pad + 6], fill=accent)

    d.text((pad, pad + 150), head, font=f_head, fill=accent)
    d.text((pad, pad + 415), sub.upper(), font=f_sub, fill=INK2)


    # foot wraps by hand: PIL has no text box, and a caption that runs off the
    # right edge is the classic silent failure of generated cards.
    #
    # It is also CLIPPED to the space above the wordmark. The first card passed
    # the whole tweet caption in and its last line ended a few pixels from
    # "sooth.bet"; a longer game name would have run straight through it. The
    # card carries one line, the tweet carries the rest.
    y = pad + 520
    limit = CARD_H - pad - 110              # keep clear of the wordmark
    for line in wrap(foot, f_foot, CARD_W - pad * 2, d):
        if y > limit:
            break
        d.text((pad, y), line, font=f_foot, fill=DIM)
        y += 48

    mark = "sooth.bet"
    mw = d.textlength(mark, font=f_mark)
    d.text((CARD_W - pad - mw, CARD_H - pad - 44), mark, font=f_mark, fill=INK)
    return img


def wrap(text: str, font, max_w: int, draw) -> list[str]:
    """Wrap to a pixel width, PARAGRAPH BY PARAGRAPH.

    text.split() flattens newlines into spaces, which ran the sentences
    together on the first card printed: "...Jacksonville Jaguars That is a gap
    between books..." with no break at all. Blank lines are structure here, not
    whitespace.
    """
    out: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")                     # keep the blank line
            continue
        line = ""
        for word in para.split():
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=font) <= max_w:
                line = trial
            else:
                if line:
                    out.append(line)
                line = word
        if line:
            out.append(line)
    return out


# ---- queue ------------------------------------------------------------------

def enqueue(item_id: str, kind: str, key: str, title: str, caption: str, img) -> str:
    os.makedirs(QUEUE_PENDING, exist_ok=True)
    name = f"{item_id}.jpg"
    img.save(os.path.join(QUEUE_PENDING, name), "JPEG", quality=92)
    item = {
        "id": item_id, "type": kind, "key": key, "title": title,
        "caption": caption, "merch_slug": "", "image": name,
        "state": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "attempts": 0, "telegram_message_id": None, "permalink": None,
    }
    with open(os.path.join(QUEUE_PENDING, f"{item_id}.json"), "w",
              encoding="utf-8") as fh:
        json.dump(item, fh, indent=1)
    return name


def load_sent() -> dict:
    d = load(WATERMARK)
    return d if isinstance(d, dict) else {}


def save_sent(sent: dict) -> None:
    os.makedirs(os.path.dirname(WATERMARK) or ".", exist_ok=True)
    with open(WATERMARK, "w", encoding="utf-8") as fh:
        json.dump(sent, fh, indent=1, sort_keys=True)
        fh.write("\n")


# ---- main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--kind", default="gap",
                    choices=("gap", "record") + tuple(sorted(REGISTRY)))
    ap.add_argument("--preview", metavar="DIR",
                    help="render to a folder instead of the approval queue")
    a = ap.parse_args()
    if a.selfcheck:
        return _selfcheck()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    sent = load_sent()

    if a.kind in REGISTRY:
        # the ten broadcast types live in engine/xcards.py; each returns None
        # when its feed cannot support a card, which is a quiet day, not a bug
        card = REGISTRY[a.kind]()
        if not card:
            print(f"no {a.kind} card today: the feed it reads has nothing that "
                  "clears the bar", file=sys.stderr)
            return 0
        check_caption(card["caption"])
        if a.preview:
            os.makedirs(a.preview, exist_ok=True)
            out = os.path.join(a.preview, f"{a.kind}.jpg")
            card["img"].save(out, "JPEG", quality=93)
            print(f"{out}\n---\n{card['caption']}\n")
            return 0
        if card["key"] in sent:
            print(f"already queued: {card['key']}", file=sys.stderr)
            return 0
        if a.dry_run:
            print(f"[dry-run] {card['title']}\n---\n{card['caption']}")
            return 0
        item_id = f"post_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{a.kind}"
        enqueue(item_id, a.kind, card["key"], card["title"], card["caption"],
                card["img"])
        sent[card["key"]] = datetime.now(timezone.utc).isoformat()
        save_sent(sent)
        print(f"queued {item_id} — approve it in Telegram to post", file=sys.stderr)
        return 0

    if a.kind == "record":
        c = record_card(load(FIGURES))
        if not c:
            print("figures.json unreadable", file=sys.stderr)
            return 1
        head, sub, cap, card_line = record_caption(c)
        key, title, accent = f"record-{stamp}", "The record", LOSS
    else:
        r = biggest_gap(load(MOVES))
        if not r:
            print("no divergence on the board right now", file=sys.stderr)
            return 0
        head, sub, cap, card_line = gap_caption(r)
        key = f"gap-{r.get('event_id','?')}-{round(r.get('move_pts') or 0, 2)}"
        title, accent = "Biggest gap on the board", BRAND

    check_caption(cap)

    if key in sent:
        print(f"already queued: {key}", file=sys.stderr)
        return 0

    if a.dry_run:
        print(f"[dry-run] {title}\n{head} · {sub}\n---\n{cap}")
        return 0

    item_id = f"post_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{a.kind}"
    enqueue(item_id, a.kind, key, title, cap, render_card(head, sub, card_line, accent))
    sent[key] = datetime.now(timezone.utc).isoformat()
    save_sent(sent)
    print(f"queued {item_id} — approve it in Telegram to post", file=sys.stderr)
    return 0


def _selfcheck() -> int:
    # captions are built from real shapes, then checked as rendered strings
    r = {"book": "FanDuel", "selection": "Miami Heat", "move_pts": 2.62,
         "sport": "nba", "home": "Miami Heat", "away": "Minnesota Timberwolves",
         "to_price": -108, "event_id": "abc"}
    head, sub, cap, card_line = gap_caption(r)
    assert "2.62" in head and "FanDuel" in cap
    assert "not a view on the game" in cap, cap
    check_caption(cap)

    fig = {"breakeven_ats": 0.5238, "evaluation_a": {"results": {"independent": {
        "accuracy": 0.6372, "ats_pct": 0.495, "ats_record": "1291-1317-63", "n": 2671}}}}
    c = record_card(fig)
    h2, s2, cap2, card2 = record_caption(c)
    assert h2 == "63.7%" and "1291-1317-63" in cap2 and "49.5%" in cap2
    # the losing half must be present, or the card is a brag
    assert "still loses" in cap2.lower(), cap2
    check_caption(cap2)

    # the guardrail actually fires
    for bad in ("Prop of the day: Jokic over 24.5", "we like the under here",
                "free play — hammer the Bills"):
        try:
            check_caption(bad)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"advice slipped through: {bad!r}")

    # dedupe collapses one event repriced by several books
    moves = {"divergence": [
        dict(r, book="FanDuel", move_pts=2.62),
        dict(r, book="Caesars", move_pts=1.90),
        dict(r, event_id="zzz", book="MGM", move_pts=3.10, selection="Boston"),
    ]}
    top = biggest_gap(moves)
    assert top["move_pts"] == 3.10, top
    assert len({(x.get("event_id")) for x in moves["divergence"]}) == 2

    # every composer's RENDERED caption goes through the same gate. This is
    # the check that keeps the guardrail true as the ten card types grow: a
    # composer added later cannot quietly introduce advice.
    built = 0
    for name, fn in sorted(REGISTRY.items()):
        card = fn()
        if not card:
            continue
        for field in ("key", "title", "caption"):
            assert card.get(field), f"{name}: empty {field}"
        check_caption(card["caption"])
        assert "sooth.bet" in card["caption"], f"{name}: no link home"
        assert card["img"].size in ((1600, 900), (1080, 1350)), f"{name}: wrong size"
        built += 1
    assert built >= 6, f"only {built} of {len(REGISTRY)} card types could build"
    print(f"xpost.selfcheck: OK ({built}/{len(REGISTRY)} card types built)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
