"""Who has asked for alerts — the read side of the subscriber list.

The list lives on Stripe customer records, in metadata. That is an unusual
place for a mailing list and the reason is worth stating, because the next
person to read this will want to move it:

We had four options and three of them cost more than they returned. A file in
this repo would put subscriber addresses in a PUBLIC git history forever, which
is the exact mistake we already made once with the pro payload and which
encryption does not fully undo (a key leak is retroactive and permanent). A new
private repo plus a write token means a token in Vercel, a token in Actions, a
new repo to keep alive, and a read-modify-write race on every signup. Resend's
own contact store is purpose-built, but its audiences API is mid-migration to
segments and we cannot test any of it locally — every endpoint we add there is
an untested endpoint in the send path.

Stripe costs nothing new: STRIPE_SECRET_KEY is already configured in Vercel and
in Actions, customer records already hold exactly this person's email for the
paid tier, metadata is arbitrary key/value, and none of it is public. A
customer with no subscription is free and explicitly supported. The trade is
that "customer" now means "person who gave us an address", which is a naming
smell and not a correctness problem.

Alerts are NOT gated on paying. Pro is disarmed and the alert list is open to
anyone who confirms an address; a payer is enrolled only if they opted in on
the alerts page like everyone else. Nobody is subscribed to email by the act of
paying us — consent for one is not consent for the other.

    python -m engine.subscribers --kind price      # who would get a price alert
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

# Cloudflare fronts the Stripe API and rejects the default urllib agent.
UA = "sooth-alerts/1.0"

# The three things we will email about. Kept as a closed set so a typo in
# metadata silently subscribes nobody rather than silently subscribing everyone.
KINDS = ("seal", "graded", "price")

# Metadata keys on the Stripe customer. Namespaced because the customer object
# is shared with the paid tier and we must never collide with billing fields.
K_ON = "sooth_alerts"          # "1" opted in, "0" unsubscribed
K_KINDS = "sooth_kinds"        # comma-separated subset of KINDS
K_MIN = "sooth_min_pts"        # float, price-alert threshold
K_AT = "sooth_confirmed_at"    # ISO8601, when they clicked the confirm link

# Points of implied probability. Detection fires at 1.5 and the page offers
# three bands; anything outside them is clamped rather than trusted.
MIN_FLOOR = 1.5
MIN_CEIL = 10.0
DEFAULT_MIN = 2.5


@dataclass(frozen=True)
class Subscriber:
    email: str
    kinds: frozenset[str]
    min_pts: float

    def wants(self, kind: str, pts: float | None = None) -> bool:
        """Does this person want this specific alert?

        Threshold applies to price alerts only — a seal or a grading result is
        an event, not a magnitude, and has nothing to compare a threshold to.
        """
        if kind not in self.kinds:
            return False
        if kind == "price" and pts is not None:
            return pts >= self.min_pts
        return True


def clamp_min(value: Any, default: float = DEFAULT_MIN) -> float:
    """Coerce a stored/submitted threshold into the supported range."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if f != f:                      # NaN
        return default
    return max(MIN_FLOOR, min(MIN_CEIL, f))


def parse_kinds(raw: Any) -> frozenset[str]:
    """Comma string -> the subset of KINDS it names. Unknown names dropped."""
    if not raw:
        return frozenset()
    parts = [p.strip().lower() for p in str(raw).split(",")]
    return frozenset(p for p in parts if p in KINDS)


def from_customer(cust: dict) -> Subscriber | None:
    """A Stripe customer -> Subscriber, or None if they are not on the list.

    Four ways to not be on the list, all of them silent: no email, opted out,
    never confirmed, or confirmed for zero kinds. None of these is an error —
    most Stripe customers are simply not alert subscribers.
    """
    email = (cust.get("email") or "").strip()
    meta = cust.get("metadata") or {}
    if not email or str(meta.get(K_ON, "")) != "1":
        return None
    kinds = parse_kinds(meta.get(K_KINDS))
    if not kinds:
        return None
    return Subscriber(email=email, kinds=kinds,
                      min_pts=clamp_min(meta.get(K_MIN)))


# ---- Stripe fetch -----------------------------------------------------------

def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (trusted host)
        return json.loads(r.read().decode())


def _search(key: str) -> list[dict]:
    """Customers flagged as opted in, via Stripe's search index.

    Search is eventually consistent (Stripe documents up to a minute of lag).
    For a cron that runs twice an hour that is invisible; for a brand-new
    subscriber it can mean missing the very next tick, which is why the caller
    falls back to a full list scan when search returns nothing at all.
    """
    q = urllib.parse.quote(f"metadata['{K_ON}']:'1'")
    url = f"https://api.stripe.com/v1/customers/search?query={q}&limit=100"
    out: list[dict] = []
    while url:
        data = _get(url, key)
        out.extend(data.get("data", []))
        nxt = data.get("next_page")
        url = (f"https://api.stripe.com/v1/customers/search?query={q}"
               f"&limit=100&page={urllib.parse.quote(nxt)}") if nxt else None
    return out


def _list_all(key: str) -> list[dict]:
    """Every customer, paginated. The fallback when the search index is cold."""
    url = "https://api.stripe.com/v1/customers?limit=100"
    out: list[dict] = []
    while url:
        data = _get(url, key)
        rows = data.get("data", [])
        out.extend(rows)
        url = ("https://api.stripe.com/v1/customers?limit=100&starting_after="
               + rows[-1]["id"]) if (data.get("has_more") and rows) else None
    return out


def fetch(stripe_key: str) -> list[Subscriber]:
    """Everyone currently on the alert list, deduped by address.

    Deduped because Stripe does not enforce unique emails on customers: a
    person who bought Pro and later signed up for alerts can legitimately have
    two records. Sending them two copies of the same email would read as a bug
    to them and as spam to their provider, so the last-confirmed record wins.
    """
    if not stripe_key:
        return []
    try:
        rows = _search(stripe_key)
    except Exception as e:                       # index cold, or key scoped down
        print(f"customer search unavailable ({e}); falling back to list scan",
              file=sys.stderr)
        rows = _list_all(stripe_key)
    if not rows:
        rows = _list_all(stripe_key)

    best: dict[str, tuple[str, Subscriber]] = {}
    for cust in rows:
        sub = from_customer(cust)
        if not sub:
            continue
        stamp = str((cust.get("metadata") or {}).get(K_AT, ""))
        key = sub.email.lower()
        if key not in best or stamp >= best[key][0]:
            best[key] = (stamp, sub)
    return [s for _, s in sorted(best.values(), key=lambda t: t[1].email)]


def recipients(stripe_key: str, kind: str, pts: float | None = None
               ) -> list[Subscriber]:
    """Subscribers who want this kind of alert (at this magnitude, if priced)."""
    return [s for s in fetch(stripe_key) if s.wants(kind, pts)]


def floor_for(subs: Iterable[Subscriber]) -> float:
    """The lowest price threshold anyone has asked for.

    The scan runs once at this floor and each alert is then filtered per
    recipient. Without it we would either scan at a fixed threshold and never
    serve the person who asked for everything, or scan at the minimum possible
    and spam the person who asked for very little.
    """
    vals = [s.min_pts for s in subs if "price" in s.kinds]
    return min(vals) if vals else MIN_FLOOR


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=KINDS, default="price")
    ap.add_argument("--pts", type=float, default=None)
    a = ap.parse_args()
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        print("STRIPE_SECRET_KEY not set — the list is unreadable from here.",
              file=sys.stderr)
        return 1
    got = recipients(key, a.kind, a.pts)
    for s in got:
        print(f"{s.email}\t{','.join(sorted(s.kinds))}\t>={s.min_pts}")
    print(f"{len(got)} recipient(s) for kind={a.kind}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
