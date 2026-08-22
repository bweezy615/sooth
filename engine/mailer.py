"""Shared email chrome and delivery for every alert Sooth sends.

One module so that the compliance footer, the unsubscribe links and the
List-Unsubscribe headers cannot drift apart between senders. Three senders use
it: alert_email (price divergence), alert_lifecycle (slate sealed, week
graded), and anything added later.

Two rules encoded here rather than left to each caller:

**No email leaves without a working unsubscribe.** ``send`` requires an
unsubscribe URL and refuses the send if it is missing. Bulk mail without a
one-click opt-out is a CAN-SPAM violation and a fast route to a poisoned
sending domain — and this is a product built on not cutting corners in public.

**RFC 8058 one-click.** Gmail and Yahoo require ``List-Unsubscribe`` plus
``List-Unsubscribe-Post`` for bulk senders. Both headers ship on every message
and api/alerts.js answers the POST form of the link, so a recipient's "unsub"
button works without them ever seeing a web page.
"""

from __future__ import annotations

import html as _html
import json
import os
import sys
import urllib.request
from typing import Any

FROM_ADDR = "Sooth Alerts <alerts@sooth.bet>"
UA = "sooth-alerts/1.0"
BASE = os.environ.get("SOOTH_BASE_URL", "https://sooth.bet")

# The legal floor, same wording as PRODUCT.md and the Ask AI system prompt.
FOOTER_TEXT = (
    "Sooth is an odds analysis tool — not a sportsbook, and not betting advice. "
    "Shopping the best price is +EV on its own arithmetic; a game's outcome is "
    "not promised. Prices move — check the book before you bet. 21+. Problem "
    "gambling? Call 1-800-522-4700."
)

# Desk palette, inlined — email clients strip <style> and have no CSS variables.
# Mirrors the FROZEN MARKET tokens in assets/desk.css; an email that arrives in
# last season's colours is the most public place a palette drift shows up.
INK, INK2, MUT, DIM = "#F0F5F6", "#AEBDC2", "#7E8D93", "#546268"
BG, HAIR, BRAND = "#06080A", "rgba(190,222,228,.17)", "#2DD4A7"
FROST = "#BFEAF2"


def esc(s: Any) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


def shell(eyebrow: str, headline: str, blurb: str, body_html: str,
          cta_text: str, cta_href: str, unsub_url: str, prefs_url: str) -> str:
    """The one email layout. Table-free, single column, dark, 560px."""
    return (
        f'<div style="max-width:560px;margin:0 auto;background:{BG};'
        f'border:1px solid {HAIR};padding:30px 26px">'
        f'<div style="color:{BRAND};font:700 12px/1 ui-monospace,monospace;'
        f'letter-spacing:.14em;text-transform:uppercase">{esc(eyebrow)}</div>'
        f'<div style="color:{INK};font:600 19px/1.35 ui-sans-serif,system-ui;'
        f'margin:14px 0 8px">{esc(headline)}</div>'
        f'<div style="color:{INK2};font:14px/1.6 ui-sans-serif,system-ui;'
        f'margin-bottom:18px">{esc(blurb)}</div>'
        f'{body_html}'
        f'<a href="{esc(cta_href)}" style="display:inline-block;margin-top:22px;'
        f'background:{BRAND};color:{BG};font:600 14px/1 ui-sans-serif,system-ui;'
        f'text-decoration:none;padding:12px 20px">{esc(cta_text)} &rarr;</a>'
        f'<div style="color:{DIM};font:11px/1.7 ui-sans-serif,system-ui;'
        f'margin-top:24px;border-top:1px solid {HAIR};padding-top:14px">'
        f'{esc(FOOTER_TEXT)}<br><br>'
        f'<a href="{esc(prefs_url)}" style="color:{MUT}">Change what you get</a>'
        f' &nbsp;·&nbsp; '
        f'<a href="{esc(unsub_url)}" style="color:{MUT}">Unsubscribe</a>'
        f'</div></div>'
    )


def text_tail(unsub_url: str, prefs_url: str) -> str:
    return ("\n\n" + FOOTER_TEXT +
            "\n\nChange what you get: " + prefs_url +
            "\nUnsubscribe: " + unsub_url +
            "\n\nsooth.bet")


def send(resend_key: str, to: str, subject: str, html_body: str, text: str,
         unsub_url: str) -> bool:
    """One message. Returns False on failure rather than raising.

    A single bad address must not abort a run — the remaining recipients are
    owed their mail, and the watermark only advances if at least one send
    succeeded, so a total outage is retried on the next tick.
    """
    if not unsub_url:
        print("refusing to send without an unsubscribe link", file=sys.stderr)
        return False
    payload = json.dumps({
        "from": FROM_ADDR,
        "to": [to],
        "subject": subject,
        "html": html_body,
        "text": text,
        "headers": {
            "List-Unsubscribe": f"<{unsub_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": "Bearer " + resend_key,
                 "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return 200 <= r.status < 300
    except Exception as e:
        print(f"  send failed for {to}: {e}", file=sys.stderr)
        return False


def row(label: str, value: str, mono: bool = False) -> str:
    """One key/value line in the body of a lifecycle email."""
    font = "ui-monospace,monospace" if mono else "ui-sans-serif,system-ui"
    return (
        f'<div style="display:block;padding:9px 0;border-bottom:1px solid {HAIR}">'
        f'<span style="color:{MUT};font:600 11px/1.4 ui-monospace,monospace;'
        f'letter-spacing:.08em;text-transform:uppercase">{esc(label)}</span><br>'
        f'<span style="color:{INK};font:14px/1.5 {font};'
        f'word-break:break-all">{esc(value)}</span></div>'
    )
