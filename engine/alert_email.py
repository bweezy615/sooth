"""Email fresh divergence alerts to Sooth Pro subscribers.

The detection is already done: engine.alerts finds the opportunities — a book
paying MORE than the cross-book consensus on a game that hasn't started. That is
the one worth a push: a better number is sitting there right now. This module is
only the delivery arm.

Three jobs, kept apart so the send logic can be checked offline:
  1. pick the alerts we have NOT emailed before, above a send threshold;
  2. find who to send to — everyone who confirmed a price subscription;
  3. render + send via Resend, then record what we sent.

Each subscriber sets their own threshold in points of implied probability, so
there is no single "the" threshold any more. The scan runs once at the LOWEST
threshold anyone asked for and each alert is then offered to each person on
their own terms. Scanning per-person would be the obvious implementation and it
would re-read the whole capture history once per subscriber.

Dedup is a committed watermark (data/alerts_sent.json). A re-run, a restart, or
two overlapping cron ticks can never double-send, because the record of "sent"
lives in git next to the evidence, same as every other sooth artifact. The
watermark stores the *magnitude* each alert went out at, not just its identity:
if a book drifts from 2.0 points out of line to 4.5, the people who asked only
about 4-point gaps still get told, and the people already told at 2.0 are not
told twice. Storing a bare list of keys — which is what this file held before
subscribers had thresholds — silently dropped that second wave. It stays a
list-compatible read so an existing watermark upgrades in place.

Addresses are NOT in the watermark, deliberately: it is committed to a public
repo. Recording "who got what" would put the subscriber list in git history
forever, which is exactly the mistake this project already made once.

Drift alerts (a book's own price moved) are intentionally NOT emailed: they are
retrospective — "you beat the close" — not an opportunity you can still take.
Only divergence pays immediately.

    python -m engine.alert_email --min-send 2.0        # a real send run
    python -m engine.alert_email --selfcheck           # offline logic check
    ALERT_TEST_EMAIL=you@x.com python -m engine.alert_email --force  # test to yourself
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import alert_token, mailer, subscribers
from . import alerts as alerts_mod

WATERMARK = "data/alerts_sent.json"
FROM_ADDR = mailer.FROM_ADDR
UA = mailer.UA

# Points of implied probability. Detection fires at 1.5; we only *email* the
# clearer ones so an inbox alert always means something worth the tap. This is
# the floor used when nobody is subscribed yet — a real run takes its floor
# from the lowest threshold anyone on the list actually asked for.
DEFAULT_MIN_SEND = 2.0

# The legal floor, same as PRODUCT.md and the Ask AI system prompt. Every email
# carries it; sooth is not a book and never claims to beat the market. It no
# longer says "because you're a Pro subscriber" — alerts are free and opt-in,
# and telling a free subscriber they are paying is a lie in the footer that
# exists to be the honest part of the email.
FOOTER_TEXT = mailer.FOOTER_TEXT


# ---- 1. pick what's new -----------------------------------------------------

def alert_key(a: dict) -> str:
    """Stable identity for dedup: one email per book-over-consensus, per game.

    Price is deliberately NOT in the key. A book that stays above consensus for
    an hour is one opportunity, not twelve; keying on price would re-send it on
    every tick. The line IS in the key — a new line is a different bet.

    # ponytail: once-per-(game,market,selection,line,book) forever. If a book
    # drifts back to consensus and later diverges again we won't re-alert; add
    # the capture date to the key if that recurrence turns out to matter.
    """
    return "|".join(str(a.get(k, "")) for k in
                    ("event_id", "market", "selection", "line", "book"))


# Points of implied probability a divergence must GROW by before it is worth
# saying again. Below this it is the same opportunity, slightly repriced.
RESEND_STEP = 1.0


def slate_divergence(pro_path: str, min_div: float) -> list[dict]:
    """Model-vs-market divergence rows from the sealed pro slate.

    Shaped like capture divergence alerts so dedup, rendering and the sent
    watermark treat both kinds identically. The 'book' slot carries the model
    name — that is what diverged. Only future kickoffs alert; a sealed slate
    is immutable, so once-per-game dedup is exactly right here.
    """
    import datetime as _dt
    try:
        doc = json.loads(Path(pro_path).read_text())
    except (OSError, json.JSONDecodeError):
        return []
    now = _dt.datetime.now(_dt.timezone.utc)
    out = []
    for g in doc.get("games", []):
        div = g.get("divergence")
        if div is None or div < min_div:
            continue
        try:
            kick = _dt.datetime.fromisoformat(str(g.get("kickoff", "")))
            if kick <= now:
                continue
        except ValueError:
            continue
        ind = g.get("independent") or {}
        mkt = g.get("market_prob")
        # market_prob is home-basis; show it on the PICK's side or the
        # comparison reads as nonsense ("61% vs 64%" with divergence 0.24).
        mkt_side = (None if mkt is None
                    else (mkt if ind.get("pick") == g.get("home") else 1 - mkt))
        out.append({
            "kind": "model_divergence",
            "event_id": g.get("game_id"),
            "market": "moneyline",
            "selection": ind.get("pick"),
            "line": None,
            "book": "independent-model",
            "home": g.get("home"), "away": g.get("away"),
            "move_pts": round(div * 100, 2),
            "detail": (f"Pick engine: the independent model has "
                       f"{ind.get('pick')} at {ind.get('prob', 0):.0%} vs the "
                       f"market's {(mkt_side or 0):.0%} — divergence "
                       f"{div:.3f} on {g.get('away')} at {g.get('home')}. "
                       f"Research, not advice: the model's published record "
                       f"loses to the close."),
            "observed_at": doc.get("committed_at", ""),
        })
    return sorted(out, key=lambda a: -a["move_pts"])


def select_new(scan: dict, sent: dict, min_send: float) -> list[dict]:
    """Divergence alerts worth sending that we haven't already sent as loudly.

    ``sent`` maps alert key -> the magnitude it last went out at. An alert
    clears the gate if it is above the run's floor AND is meaningfully bigger
    than the last time we mentioned it, so a book drifting further out of line
    can reach a subscriber whose threshold it has only now crossed.

    Sorted strongest-first so a truncated email leads with the best number.
    """
    out = []
    for a in scan.get("divergence", []):
        pts = a.get("move_pts", 0)
        if pts < min_send:
            continue
        before = sent.get(alert_key(a))
        # RESEND_STEP, not "any increase": prices tick constantly and a
        # re-alert on +0.01 points is the noise this threshold exists to stop.
        if before is not None and pts < before + RESEND_STEP:
            continue
        out.append(a)
    return sorted(out, key=lambda a: -a.get("move_pts", 0))


def for_recipient(new: list[dict], sub: "subscribers.Subscriber",
                  sent: dict) -> list[dict]:
    """The subset of this batch that this person actually asked for.

    Two gates, both per-person: their own threshold, and whether they were
    already told about this exact alert at this magnitude on an earlier tick.
    """
    out = []
    for a in new:
        pts = a.get("move_pts", 0)
        if not sub.wants("price", pts):
            continue
        before = sent.get(alert_key(a))
        if before is not None and pts < before + RESEND_STEP:
            continue
        out.append(a)
    return out


# ---- 2. who to send to ------------------------------------------------------

def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (trusted host)
        return json.loads(r.read().decode())


def price_subscribers(stripe_key: str) -> list["subscribers.Subscriber"]:
    """Everyone who confirmed a price-alert subscription, with their threshold.

    This replaced a "recipients = active Stripe subscriptions" lookup. That
    version could never send anything: Pro is disarmed and free, so the set of
    active subscriptions is empty by construction, and the most-requested
    feature in the entire competitive scan was quietly wired to an empty list.
    Paying and wanting email are now separate facts, which is also the only
    defensible reading of consent.
    """
    return subscribers.recipients(stripe_key, "price")


# ---- 3. render + send -------------------------------------------------------

def render(new: list[dict], unsub_url: str = "", prefs_url: str = ""
           ) -> tuple[str, str, str]:
    """(subject, html, text) for one person's batch of fresh alerts.

    Rendered per recipient rather than once per run, because the unsubscribe
    and preferences links are specific to the address they are sent to. That is
    also why the batch itself is per-recipient: two people with different
    thresholds get genuinely different emails, not the same email with a
    footer swapped.
    """
    n = len(new)
    lead = new[0]
    subject = (f"Sooth: {lead['book']} +{lead['move_pts']:.1f} pts on "
               f"{lead['selection']}" + (f" (+{n - 1} more)" if n > 1 else ""))

    text_lines, rows = [], []
    for a in new:
        sport = str(a.get("sport", "")).upper()
        game = f"{a.get('away','')} at {a.get('home','')}".strip(" at ")
        detail = a.get("detail", "")
        start = a.get("kickoff", "")
        text_lines.append(f"{sport}  {game}\n  {detail}"
                          + (f"\n  starts {start}" if start else ""))
        rows.append(
            f'<div style="padding:13px 0;border-bottom:1px solid {mailer.HAIR}">'
            f'<div style="color:{mailer.BRAND};font:600 11px/1.4 ui-monospace,'
            f'monospace;letter-spacing:.08em">{mailer.esc(sport)} &middot; '
            f'{mailer.esc(game)}</div>'
            f'<div style="color:{mailer.INK};font:14.5px/1.55 ui-sans-serif,'
            f'system-ui;margin-top:4px">{mailer.esc(detail)}</div>'
            + (f'<div style="color:{mailer.DIM};font:12px/1.4 ui-monospace,'
               f'monospace;margin-top:4px">starts {mailer.esc(start)}</div>'
               if start else "")
            + '</div>')

    blurb = ("A book is pricing away from where the rest of the market has it. "
             "That is a fact about prices, not a forecast about the game — and "
             "prices move, so check the book before you act on it.")
    html = mailer.shell("Sooth · line alert", "A book is out of line.", blurb,
                        "".join(rows), "Open the board",
                        mailer.BASE + "/edges", unsub_url, prefs_url)
    text = (blurb + "\n\n" + "\n\n".join(text_lines)
            + "\n\nOpen the board: " + mailer.BASE + "/edges"
            + mailer.text_tail(unsub_url, prefs_url))
    return subject, html, text


def send_email(resend_key: str, to: str, subject: str, html: str, text: str,
               unsub_url: str = "") -> bool:
    return mailer.send(resend_key, to, subject, html, text, unsub_url)


# ---- orchestration ----------------------------------------------------------

def load_sent(path: str = WATERMARK) -> dict:
    """key -> the magnitude that key last went out at.

    Reads the older list-of-keys format too. Those entries carry no magnitude,
    so they are restored at +inf: an alert we have already sent under the old
    scheme is treated as fully spoken for and can never re-fire on the upgrade.
    Re-mailing every subscriber the entire back-catalogue on deploy day is the
    one migration failure that would actually cost us the list.
    """
    try:
        raw = json.loads(Path(path).read_text()).get("keys", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if isinstance(raw, list):
        return {str(k): float("inf") for k in raw}
    # null round-trips as "already sent, magnitude unknown" -> never re-fire.
    return {str(k): (float("inf") if v is None else float(v))
            for k, v in raw.items()}


def save_sent(sent: dict, path: str = WATERMARK) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Keep it bounded — old keys can't re-fire once their game is long past.
    # ponytail: last 5000 is plenty for daily volume; trims the watermark file.
    keys = sorted(sent)[-5000:]
    out = {k: (None if sent[k] == float("inf") else round(sent[k], 2))
           for k in keys}
    Path(path).write_text(json.dumps({"keys": out}, indent=1) + "\n")


def mark(sent: dict, alerts: list[dict]) -> dict:
    """Record each alert at the largest magnitude it has now been sent at."""
    for a in alerts:
        k = alert_key(a)
        pts = float(a.get("move_pts", 0))
        sent[k] = pts if k not in sent else max(sent[k], pts)
    return sent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-send", type=float, default=DEFAULT_MIN_SEND)
    ap.add_argument("--pro-slate", default="data/pro/latest.pro.json")
    ap.add_argument("--pick-divergence", type=float, default=0.10,
                    help="model-vs-market divergence floor for slate alerts")
    ap.add_argument("--pattern", default="data/capture/*/*.jsonl")
    ap.add_argument("--force", action="store_true",
                    help="send the top current alert even if already recorded (test)")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    if a.selfcheck:
        return _selfcheck()

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    resend_key = os.environ.get("RESEND_API_KEY", "")

    people = price_subscribers(stripe_key) if stripe_key else []
    test = os.environ.get("ALERT_TEST_EMAIL", "")
    if test and not any(s.email == test for s in people):
        people.append(subscribers.Subscriber(
            email=test, kinds=frozenset(subscribers.KINDS), min_pts=a.min_send))

    # Scan once, at the lowest bar anyone asked for. With nobody subscribed we
    # still scan (at the CLI default) so the watermark keeps pace and the first
    # person to join gets live alerts rather than a backlog.
    floor = subscribers.floor_for(people) if people else a.min_send
    scan = alerts_mod.scan(a.pattern, min_move=floor)
    sent = {} if a.force else load_sent()
    new = select_new(scan, sent, floor)
    slate_new = [x for x in slate_divergence(a.pro_slate, a.pick_divergence)
                 if alert_key(x) not in sent]
    new = slate_new + new   # the sealed slate leads; it is the product
    if a.force and not new and scan.get("divergence"):
        new = scan["divergence"][:1]   # nothing new? send the strongest for a test
    print(f"floor {floor} pts · divergence found: "
          f"{len(scan.get('divergence', []))} · new to send: {len(new)}")
    if not new:
        return 0

    if not people:
        print("nobody subscribed — recording as sent so we don't backlog.")
        if not a.force:
            save_sent(mark(sent, new))
        return 0
    if not resend_key:
        print("RESEND_API_KEY not set — nothing sent.", file=sys.stderr)
        return 1
    try:
        alert_token._secret()
    except alert_token.NoSecret as e:
        # No signing secret means no verifiable unsubscribe link. Sending
        # anyway would be the CAN-SPAM violation; not sending costs one tick.
        print(str(e), file=sys.stderr)
        return 1

    ok = attempted = 0
    for s in people:
        mine = for_recipient(new, s, sent)
        if not mine:
            continue
        attempted += 1
        unsub = alert_token.unsub_link(s.email, mailer.BASE)
        prefs = alert_token.prefs_link(s.email, mailer.BASE)
        subject, html, text = render(mine, unsub, prefs)
        ok += send_email(resend_key, s.email, subject, html, text, unsub)
    print(f"sent {ok}/{attempted} emails to {len(people)} subscriber(s)")
    if ok and not a.force:
        save_sent(mark(sent, new))
    return 0 if ok else 1


def _selfcheck() -> int:
    """Offline check of the parts that don't touch the network."""
    div = lambda k, pts: {"kind": "divergence", "event_id": k, "market": "ml",
                          "selection": "A", "line": None, "book": "FD",
                          "move_pts": pts, "sport": "mlb", "away": "X", "home": "Y",
                          "detail": "FD pays", "kickoff": ""}
    scan = {"divergence": [div("g1", 3.0), div("g2", 1.0), div("g3", 2.5)]}
    sub = subscribers.Subscriber

    # threshold filters, and results are strongest-first
    got = select_new(scan, {}, 2.0)
    assert [a["event_id"] for a in got] == ["g1", "g3"], got

    # dedup: an already-sent key is excluded
    got2 = select_new(scan, {alert_key(div("g1", 3.0)): 3.0}, 2.0)
    assert [a["event_id"] for a in got2] == ["g3"], got2

    # ...but a divergence that has grown past the resend step speaks again
    grown = {"divergence": [div("g1", 3.0 + RESEND_STEP)]}
    assert len(select_new(grown, {alert_key(div("g1", 0)): 3.0}, 2.0)) == 1
    nudged = {"divergence": [div("g1", 3.2)]}
    assert select_new(nudged, {alert_key(div("g1", 0)): 3.0}, 2.0) == [], \
        "a 0.2pt tick is the same opportunity, not a new one"

    # key ignores price so a moving book doesn't re-fire on identical prices
    assert alert_key(div("g1", 3.0)) == alert_key(div("g1", 9.9))

    # per-recipient thresholds: one batch, two different emails
    quiet = sub("q@x.com", frozenset({"price"}), 3.0)
    eager = sub("e@x.com", frozenset({"price"}), 1.5)
    assert [a["event_id"] for a in for_recipient(got, quiet, {})] == ["g1"]
    assert [a["event_id"] for a in for_recipient(got, eager, {})] == ["g1", "g3"]

    # someone who only wants seals is never in a price batch
    sealonly = sub("s@x.com", frozenset({"seal"}), 1.5)
    assert for_recipient(got, sealonly, {}) == []
    assert sealonly.wants("seal") and not sealonly.wants("price", 99)

    # the run's floor is the lowest anyone asked for, never a fixed constant
    assert subscribers.floor_for([quiet, eager]) == 1.5
    assert subscribers.floor_for([sealonly]) == subscribers.MIN_FLOOR

    # watermark: magnitudes round-trip, and the old list format upgrades to
    # "already spoken for" rather than re-mailing the back catalogue
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "wm.json")
        save_sent(mark({}, got), p)
        back = load_sent(p)
        assert back[alert_key(div("g1", 0))] == 3.0
        Path(p).write_text(json.dumps({"keys": ["legacy|k|A||FD"]}))
        assert load_sent(p)["legacy|k|A||FD"] == float("inf")
        save_sent(load_sent(p), p)
        assert load_sent(p)["legacy|k|A||FD"] == float("inf"), "inf survives a rewrite"

    # render carries the compliance floor, the lead number, and the opt-out
    subj, html, text = render(got, "https://sooth.bet/api/alerts?unsub=T",
                              "https://sooth.bet/alerts?prefs=T")
    assert "1-800-522-4700" in text and "1-800-522-4700" in html
    assert "not betting advice" in text.lower() or "not a sportsbook" in text.lower()
    assert "3.0" in subj
    assert "unsub=T" in html and "unsub=T" in text, "every email carries an opt-out"
    assert "Pro subscriber" not in text, "alerts are free; don't tell people they paid"

    # mailer refuses to send at all without an unsubscribe link
    assert mailer.send("key", "a@b.co", "s", "<p>h</p>", "t", "") is False

    print("alert_email.selfcheck: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
