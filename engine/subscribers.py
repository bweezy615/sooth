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
KINDS = ("seal", "graded", "price", "game")

# Metadata keys on the Stripe customer. Namespaced because the customer object
# is shared with the paid tier and we must never collide with billing fields.
K_ON = "sooth_alerts"          # "1" opted in, "0" unsubscribed
K_KINDS = "sooth_kinds"        # comma-separated subset of KINDS
K_MIN = "sooth_min_pts"        # float, price-alert threshold
K_AT = "sooth_confirmed_at"    # ISO8601, when they clicked the confirm link
K_TEAMS = "sooth_teams"        # the watchlist: "nba:NYK,nfl:BUF", sport-scoped

# WHY TEAMS AND NOT GAMES, given the feature is "per-game alerts".
#
# A game id dies at kickoff. Storing them means the watchlist empties itself
# every week and the reader has to re-add everything to keep getting anything,
# which is the opposite of a watchlist. Following a TEAM is durable, is how
# people actually describe it out loud, and yields per-game alerts anyway: a
# game qualifies when either side is on the list.
#
# It is also the only version that fits. Stripe caps a metadata VALUE at 500
# characters. Game ids here are 32 hex, so ids-plus-separator is 33 bytes and
# the whole watchlist would cap out at 15 games — less than one NFL Sunday.
# "nba:NYK," is 8, so the same 500 bytes holds ~60 teams, which is more than
# anyone will follow.
#
# SPORT-SCOPED, always. Bare abbreviations collide across leagues — MIA, PHI,
# ATL, MIN and a dozen more exist in several — and this is the same trap the
# crest lookup fell into. An unscoped "MIA" cannot be resolved to a team, and
# guessing would mail somebody about the wrong sport's game.
TEAM_RE = __import__("re").compile(r"^[a-z]{2,6}:[A-Z0-9]{2,4}$")

# 500 is Stripe's hard cap on a metadata value. The list is truncated to fit
# rather than rejected, because a person who follows 61 teams should still get
# alerts about the first 60 rather than an error they cannot act on.
TEAMS_MAX_BYTES = 500

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
    teams: frozenset[str] = frozenset()

    def wants(self, kind: str, pts: float | None = None) -> bool:
        """Does this person want this specific alert?

        Threshold applies to price alerts only — a seal or a grading result is
        an event, not a magnitude, and has nothing to compare a threshold to.

        "game" is deliberately NOT answered here. Whether a game alert applies
        depends on which teams are playing, which this object cannot see; ask
        watches() instead. Answering True here would mail every watchlist
        subscriber about every game on the board.
        """
        if kind not in self.kinds:
            return False
        if kind == "game":
            return bool(self.teams)
        if kind == "price" and pts is not None:
            return pts >= self.min_pts
        return True

    def watches(self, *team_keys: str) -> bool:
        """Is any of these sport-scoped team keys on this person's watchlist?

        Callers pass both sides of a matchup. Empty watchlist is False, never
        "everything" — an unfiltered watchlist alert is indistinguishable from
        spam to the person receiving it.
        """
        if "game" not in self.kinds or not self.teams:
            return False
        return any(k in self.teams for k in team_keys)


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


def parse_teams(raw: Any) -> frozenset[str]:
    """Comma string -> the sport-scoped team keys it names.

    Anything that is not `sport:ABBR` is dropped rather than repaired. A
    malformed entry means we do not know which team was meant, and the failure
    mode of guessing is emailing somebody about a game they never asked about.
    """
    if not raw:
        return frozenset()
    out = set()
    for part in str(raw).split(","):
        k = part.strip()
        if not k:
            continue
        sport, _, abbr = k.partition(":")
        k = sport.strip().lower() + ":" + abbr.strip().upper()
        if TEAM_RE.match(k):
            out.add(k)
    return frozenset(out)


def serialise_teams(teams: Iterable[str]) -> str:
    """Watchlist -> the metadata string, truncated to Stripe's 500-byte cap.

    Sorted first, so truncation is deterministic: the same watchlist always
    stores the same 60 teams rather than a different arbitrary subset each
    write.
    """
    out: list[str] = []
    used = 0
    for k in sorted(set(teams)):
        add = len(k) + (1 if out else 0)
        if used + add > TEAMS_MAX_BYTES:
            break
        out.append(k)
        used += add
    return ",".join(out)


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
                      min_pts=clamp_min(meta.get(K_MIN)),
                      teams=parse_teams(meta.get(K_TEAMS)))


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


def watchers(stripe_key: str, *team_keys: str) -> list[Subscriber]:
    """Subscribers watching either side of one matchup.

    Separate from recipients() because a game alert is not filtered by
    magnitude but by identity, and folding both into one signature produced a
    call that read as `recipients(key, "game")` and silently matched everyone.
    """
    return [s for s in fetch(stripe_key) if s.watches(*team_keys)]


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
    ap.add_argument("--teams", default="",
                    help="sport-scoped keys for --kind game, e.g. nba:NYK,nfl:BUF")
    a = ap.parse_args()
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        print("STRIPE_SECRET_KEY not set — the list is unreadable from here.",
              file=sys.stderr)
        return 1
    if a.kind == "game":
        got = watchers(key, *parse_teams(a.teams))
    else:
        got = recipients(key, a.kind, a.pts)
    for s in got:
        print(f"{s.email}\t{','.join(sorted(s.kinds))}\t>={s.min_pts}"
              f"\t{','.join(sorted(s.teams)) or '-'}")
    print(f"{len(got)} recipient(s) for kind={a.kind}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
