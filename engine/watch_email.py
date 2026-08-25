"""Email the people who follow a team that one of its games is about to start.

    python -m engine.watch_email --hours 24 --dry-run
    python -m engine.watch_email --hours 24
    python -m engine.watch_email --selfcheck

Selection lives in engine.watchlist; this is the delivery arm, and it mirrors
engine.alert_email deliberately — same mailer, same signed unsubscribe, same
refusal to send without AUTH_SECRET.

What this email is, and what it must never become
-------------------------------------------------
It says a game you follow starts soon, and it carries the two numbers already
on the public board for it: the de-vigged fair price and the best number
anyone is posting. It does not say who will win, does not rank the games, and
does not tell anyone to bet. The moment a reminder starts recommending, it
stops being a reminder and the whole product's position goes with it.

One email per person per run, batching every one of their games. The
alternative — one email per game — turns a Sunday into nine emails and gets
the domain filed as spam, which costs the price alerts too.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from engine import alert_token, mailer, subscribers, watchlist


def fair_and_best(game_id: str, board_path: str = watchlist.BOARD) -> dict:
    """The two published numbers for one game, or {} if the board has neither.

    Read from the same board the site serves, so an email can never quote a
    figure the reader cannot then find on the page it links to.
    """
    try:
        with open(board_path, encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        return {}
    for b in data.get("boards") or []:
        for e in b.get("events") or []:
            if str(e.get("id")) != str(game_id):
                continue
            sides = e.get("sides") or []
            out = []
            for s in sides[:2]:
                out.append({
                    "name": s.get("name"),
                    "fair": s.get("fair_price"),
                    "best": s.get("best_price"),
                    "book": s.get("best_book"),
                })
            return {"sides": out, "books": e.get("n_books")}
    return {}


def render(games: list[dict], unsub_url: str = "", prefs_url: str = ""
           ) -> tuple[str, str, str]:
    """(subject, html, text) for one person's batch of upcoming watched games."""
    n = len(games)
    lead = games[0]
    matchup = f"{lead.get('away', '')} at {lead.get('home', '')}"
    subject = (f"Sooth: {matchup} starts soon"
               + (f" (+{n - 1} more)" if n > 1 else ""))

    rows, text_lines = [], []
    for g in games:
        sport = str(g.get("sport", "")).upper()
        game = f"{g.get('away', '')} at {g.get('home', '')}"
        when = str(g.get("starts", ""))[:16].replace("T", " ") + " UTC"
        nums = g.get("numbers") or {}
        bits = []
        for s in (nums.get("sides") or []):
            if s.get("fair") is None:
                continue
            piece = f"{s['name']} fair {s['fair']}"
            if s.get("best") is not None:
                piece += f", best {s['best']}"
                if s.get("book"):
                    piece += f" ({s['book']})"
            bits.append(piece)
        detail = " · ".join(bits) if bits else "No price posted yet."

        text_lines.append(f"{sport}  {game}\n  starts {when}\n  {detail}")
        rows.append(
            f'<div style="padding:13px 0;border-bottom:1px solid {mailer.HAIR}">'
            f'<div style="color:{mailer.BRAND};font:600 11px/1.4 ui-monospace,'
            f'monospace;letter-spacing:.08em">{mailer.esc(sport)}</div>'
            f'<div style="color:{mailer.INK};font:14.5px/1.55 ui-sans-serif,'
            f'system-ui;margin-top:4px">{mailer.esc(game)}</div>'
            f'<div style="color:{mailer.DIM};font:12px/1.4 ui-monospace,'
            f'monospace;margin-top:4px">starts {mailer.esc(when)}</div>'
            f'<div style="color:{mailer.INK2};font:13px/1.5 ui-sans-serif,'
            f'system-ui;margin-top:5px">{mailer.esc(detail)}</div>'
            '</div>')

    blurb = ("A game you follow starts soon. The numbers below are the "
             "de-vigged fair price and the best number posted anywhere we "
             "track — facts about prices, not a forecast, and not a "
             "suggestion to bet. Prices move; check the book.")
    html = mailer.shell("Sooth · watchlist", "A game you follow starts soon.",
                        blurb, "".join(rows), "Open the board",
                        mailer.BASE + "/market", unsub_url, prefs_url)
    text = (blurb + "\n\n" + "\n\n".join(text_lines)
            + "\n\nOpen the board: " + mailer.BASE + "/market"
            + mailer.text_tail(unsub_url, prefs_url))
    return subject, html, text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=watchlist.DEFAULT_HOURS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return _selfcheck()

    if not os.environ.get("AUTH_SECRET"):
        # Same refusal as the price alerts. An email without a working
        # unsubscribe is not a smaller feature, it is a compliance problem.
        print("AUTH_SECRET not set — refusing to send without a signed "
              "unsubscribe link.", file=sys.stderr)
        return 1

    index = watchlist.team_index()
    events = watchlist.load_board()
    games = watchlist.upcoming(events, index, a.hours)
    sent = watchlist.load_sent()
    fresh = watchlist.select_new(games, sent)
    if not fresh:
        print("nothing new in the window", file=sys.stderr)
        return 0

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    subs = [s for s in subscribers.fetch(stripe_key) if s.wants("game")]
    if not subs:
        # Record-and-skip, exactly as the price alerts do: without this the
        # first person to ever subscribe is greeted with every game already on
        # the board.
        if not a.dry_run:
            watchlist.save_sent(
                watchlist.prune(watchlist.mark(sent, fresh), events))
        print(f"{len(fresh)} game(s) in window, no watchlist subscribers — "
              f"marked as seen", file=sys.stderr)
        return 0

    for g in fresh:
        g["numbers"] = fair_and_best(g["game_id"])

    resend_key = os.environ.get("RESEND_API_KEY", "")
    ok = 0
    for sub in subs:
        mine = [g for g in fresh
                if sub.watches(*[k for k in (g["home_key"], g["away_key"]) if k])]
        if not mine:
            continue
        unsub = alert_token.unsub_link(sub.email, mailer.BASE)
        prefs = alert_token.prefs_link(sub.email, mailer.BASE)
        subject, html, text = render(mine, unsub, prefs)
        if a.dry_run:
            print(f"[dry-run] {sub.email}: {subject}")
            ok += 1
            continue
        if mailer.send(resend_key, sub.email, subject, html, text, unsub):
            ok += 1

    if not a.dry_run:
        watchlist.save_sent(watchlist.prune(watchlist.mark(sent, fresh), events))
    print(f"{len(fresh)} game(s), {ok} email(s)", file=sys.stderr)
    return 0


def _selfcheck() -> int:
    g = {"game_id": "g1", "sport": "nba", "home": "New York Knicks",
         "away": "Philadelphia 76ers", "home_key": "nba:NYK",
         "away_key": "nba:PHI", "starts": "2026-08-25T23:00:00+00:00",
         "hours_out": 5.0,
         "numbers": {"sides": [
             {"name": "New York Knicks", "fair": -173, "best": -165, "book": "FD"},
             {"name": "Philadelphia 76ers", "fair": 173, "best": 176, "book": "MGM"}]}}

    subject, html, text = render([g], "https://x/u", "https://x/p")
    assert "starts soon" in subject and "Knicks" in subject, subject
    assert "-173" in text and "FD" in text, text
    # the reminder must not have become a recommendation
    banned = ("pick", "bet on", "lock", "value play", "we like", "edge play")
    low = (subject + " " + text).lower()
    for w in banned:
        assert w not in low, f"reminder is recommending: {w!r}"
    assert "not a forecast" in low and "check the book" in low

    # a game with no posted price still renders rather than crashing
    bare = dict(g, numbers={})
    _, _, t2 = render([bare])
    assert "No price posted yet." in t2, t2

    # batching: one subject line covers the rest
    s3, _, _ = render([g, dict(g, game_id="g2"), dict(g, game_id="g3")])
    assert "(+2 more)" in s3, s3

    print("watch_email.selfcheck: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
