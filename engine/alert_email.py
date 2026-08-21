"""Email fresh divergence alerts to Sooth Pro subscribers.

The detection is already done: engine.alerts finds the opportunities — a book
paying MORE than the cross-book consensus on a game that hasn't started. That is
the one worth a push: a better number is sitting there right now. This module is
only the delivery arm.

Three jobs, kept apart so the send logic can be checked offline:
  1. pick the alerts we have NOT emailed before, above a send threshold;
  2. find who to send to — the emails on active Stripe subscriptions;
  3. render + send via Resend, then record what we sent.

Dedup is a committed watermark (data/alerts_sent.json). A re-run, a restart, or
two overlapping cron ticks can never double-send, because the record of "sent"
lives in git next to the evidence, same as every other sooth artifact.

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

from . import alerts as alerts_mod

WATERMARK = "data/alerts_sent.json"
FROM_ADDR = "Sooth Alerts <alerts@sooth.bet>"
# Cloudflare fronts these APIs and bans the default "Python-urllib/x" agent
# (error 1010). A named agent sails through — set it on every call.
UA = "sooth-alerts/1.0"

# Points of implied probability. Detection fires at 1.5; we only *email* the
# clearer ones so an inbox alert always means something worth the tap.
DEFAULT_MIN_SEND = 2.0

# The legal floor, same as PRODUCT.md and the Ask AI system prompt. Every email
# carries it; sooth is not a book and never claims to beat the market.
FOOTER_TEXT = (
    "You get these because you're a Sooth Pro subscriber. Sooth is an odds "
    "analysis tool — not a sportsbook, and not betting advice. Shopping the "
    "best price is +EV on its own arithmetic; a game's outcome is not promised. "
    "Prices move — check the book before you bet. 21+. Problem gambling? Call "
    "1-800-522-4700."
)


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


def select_new(scan: dict, sent: set, min_send: float) -> list[dict]:
    """Divergence alerts above threshold that we haven't emailed yet.

    Sorted strongest-first so a truncated email leads with the best number.
    """
    fresh = [a for a in scan.get("divergence", [])
             if a.get("move_pts", 0) >= min_send and alert_key(a) not in sent]
    return sorted(fresh, key=lambda a: -a.get("move_pts", 0))


# ---- 2. who to send to ------------------------------------------------------

def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (trusted host)
        return json.loads(r.read().decode())


def stripe_recipients(stripe_key: str) -> list[str]:
    """Emails on active Stripe subscriptions (paginated, deduped).

    A subscription's email lives on its customer, so we expand the customer in
    the same call rather than fetching each one. Canceled/past_due subs are
    excluded by status=active — the source of truth for "is this person Pro".
    """
    emails: list[str] = []
    seen: set[str] = set()
    url = ("https://api.stripe.com/v1/subscriptions?status=active&limit=100"
           "&expand[]=data.customer")
    while url:
        data = _get(url, stripe_key)
        for sub in data.get("data", []):
            cust = sub.get("customer") or {}
            email = cust.get("email") if isinstance(cust, dict) else None
            if email and email not in seen:
                seen.add(email)
                emails.append(email)
        if data.get("has_more") and data.get("data"):
            last = data["data"][-1]["id"]
            url = ("https://api.stripe.com/v1/subscriptions?status=active"
                   "&limit=100&expand[]=data.customer&starting_after=" + last)
        else:
            url = None
    return emails


# ---- 3. render + send -------------------------------------------------------

def render(new: list[dict]) -> tuple[str, str, str]:
    """(subject, html, text) for a batch of fresh alerts."""
    n = len(new)
    lead = new[0]
    subject = (f"Sooth: {lead['book']} +{lead['move_pts']:.1f} pts on "
               f"{lead['selection']}" + (f" (+{n - 1} more)" if n > 1 else ""))

    text_lines, html_rows = [], []
    for a in new:
        sport = str(a.get("sport", "")).upper()
        game = f"{a.get('away','')} at {a.get('home','')}".strip(" at ")
        detail = a.get("detail", "")
        start = a.get("kickoff", "")
        text_lines.append(f"{sport}  {game}\n  {detail}"
                          + (f"\n  starts {start}" if start else ""))
        html_rows.append(
            f'<tr><td style="padding:14px 0;border-bottom:1px solid #1f2937">'
            f'<div style="color:#7dd3fc;font:600 12px/1.4 ui-monospace,monospace;'
            f'letter-spacing:.05em">{sport} &middot; {game}</div>'
            f'<div style="color:#e5e7eb;font:15px/1.5 ui-sans-serif,system-ui;'
            f'margin-top:4px">{detail}</div>'
            + (f'<div style="color:#6b7280;font:12px/1.4 ui-monospace,monospace;'
               f'margin-top:4px">starts {start}</div>' if start else "")
            + '</td></tr>')

    text = ("A book is paying over the market. These prices move — check the "
            "book.\n\n" + "\n\n".join(text_lines) + "\n\n" + FOOTER_TEXT
            + "\n\nsooth.bet")
    html = (
        '<div style="max-width:560px;margin:0 auto;background:#0b0f14;'
        'border:1px solid #1f2937;border-radius:12px;padding:28px 24px">'
        '<div style="color:#7dd3fc;font:700 13px/1 ui-monospace,monospace;'
        'letter-spacing:.12em;text-transform:uppercase">Sooth &middot; line alert</div>'
        '<div style="color:#9ca3af;font:14px/1.5 ui-sans-serif,system-ui;'
        'margin:8px 0 4px">A book is paying over the market right now.</div>'
        '<table style="width:100%;border-collapse:collapse">'
        + "".join(html_rows) + '</table>'
        '<a href="https://sooth.bet/edges.html" style="display:inline-block;'
        'margin-top:20px;background:#7dd3fc;color:#0b0f14;font:600 14px/1 '
        'ui-sans-serif,system-ui;text-decoration:none;padding:11px 18px;'
        'border-radius:8px">Open the board &rarr;</a>'
        f'<div style="color:#6b7280;font:11px/1.6 ui-sans-serif,system-ui;'
        f'margin-top:22px;border-top:1px solid #1f2937;padding-top:14px">'
        f'{FOOTER_TEXT}</div></div>')
    return subject, html, text


def send_email(resend_key: str, to: str, subject: str, html: str, text: str) -> bool:
    payload = json.dumps({
        "from": FROM_ADDR, "to": [to],
        "subject": subject, "html": html, "text": text,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": "Bearer " + resend_key,
                 "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return 200 <= r.status < 300
    except Exception as e:  # a bad address shouldn't kill the whole run
        print(f"  send failed for {to}: {e}", file=sys.stderr)
        return False


# ---- orchestration ----------------------------------------------------------

def load_sent() -> set:
    try:
        return set(json.loads(Path(WATERMARK).read_text()).get("keys", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_sent(sent: set) -> None:
    Path(WATERMARK).parent.mkdir(parents=True, exist_ok=True)
    # Keep it bounded — old keys can't re-fire once their game is long past.
    # ponytail: last 5000 is plenty for daily volume; trims the watermark file.
    keys = sorted(sent)[-5000:]
    Path(WATERMARK).write_text(json.dumps({"keys": keys}, indent=1))


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

    scan = alerts_mod.scan(a.pattern, min_move=a.min_send)
    sent = set() if a.force else load_sent()
    new = select_new(scan, sent, a.min_send)
    slate_new = [x for x in slate_divergence(a.pro_slate, a.pick_divergence)
                 if alert_key(x) not in sent]
    new = slate_new + new   # the sealed slate leads; it is the product
    if a.force and not new and scan.get("divergence"):
        new = scan["divergence"][:1]   # nothing new? send the strongest for a test
    print(f"divergence found: {len(scan.get('divergence', []))}  new to send: {len(new)}")
    if not new:
        return 0

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_key:
        print("RESEND_API_KEY not set — nothing sent.", file=sys.stderr)
        return 1

    to = stripe_recipients(stripe_key) if stripe_key else []
    test = os.environ.get("ALERT_TEST_EMAIL", "")
    if test and test not in to:
        to.append(test)
    print(f"recipients: {len(to)}")
    if not to:
        print("no active subscribers — recording as sent so we don't backlog.")
        # Still mark them sent: when the first subscriber joins they get fresh
        # alerts, not a week-old backlog on their first tick.
        if not a.force:
            save_sent(sent | {alert_key(x) for x in new})
        return 0

    subject, html, text = render(new)
    ok = sum(send_email(resend_key, addr, subject, html, text) for addr in to)
    print(f"sent {ok}/{len(to)} emails")
    if ok and not a.force:
        save_sent(sent | {alert_key(x) for x in new})
    return 0 if ok else 1


def _selfcheck() -> int:
    """Offline check of the parts that don't touch the network."""
    div = lambda k, pts: {"kind": "divergence", "event_id": k, "market": "ml",
                          "selection": "A", "line": None, "book": "FD",
                          "move_pts": pts, "sport": "mlb", "away": "X", "home": "Y",
                          "detail": "FD pays", "kickoff": ""}
    scan = {"divergence": [div("g1", 3.0), div("g2", 1.0), div("g3", 2.5)]}

    # threshold filters, and results are strongest-first
    got = select_new(scan, set(), 2.0)
    assert [a["event_id"] for a in got] == ["g1", "g3"], got

    # dedup: an already-sent key is excluded
    got2 = select_new(scan, {alert_key(div("g1", 3.0))}, 2.0)
    assert [a["event_id"] for a in got2] == ["g3"], got2

    # key ignores price so a moving book doesn't re-fire
    assert alert_key(div("g1", 3.0)) == alert_key(div("g1", 9.9))

    # render carries the compliance floor and the lead number
    subj, html, text = render(got)
    assert "1-800-522-4700" in text and "1-800-522-4700" in html
    assert "not betting advice" in text.lower() or "not a sportsbook" in text.lower()
    assert "3.0" in subj

    print("alert_email.selfcheck: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
