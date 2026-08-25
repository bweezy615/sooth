"""Which watched games are about to start — the selection half of game alerts.

    python -m engine.watchlist --hours 24          # what would be sent
    python -m engine.watchlist --selfcheck

The split mirrors the price alerts: this module decides WHAT qualifies and
engine.alert_email decides who gets it and sends it. Keeping selection pure
means it can be tested with no Stripe key, no Resend key and no network, which
is the only reason the price-alert logic has a selfcheck at all.

What qualifies
--------------
A game on the published board that (a) has not started, (b) starts inside the
window, and (c) has at least one side on somebody's watchlist. Nothing about
prices or edges enters into it: this is a reminder that a game you follow is
about to begin, not a recommendation, and it must not quietly become one.

The watermark holds GAME IDS AND NOTHING ELSE
---------------------------------------------
data/watchlist_sent.json is committed to a public repository, so it must not
carry a hint of who is on the list. Keying it by recipient — even hashed —
would put a per-person record in public history forever, which is the exact
mistake engine.subscribers exists to avoid.

So a game is reminded ONCE, to everyone watching it at that moment. The cost
is that somebody who adds a team after the reminder for tonight's game has
already gone out starts from the next game instead. That is a fair trade for
keeping the public artefact anonymous, and the alternative — a per-recipient
watermark — is a subscriber list in git by another name.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any

BOARD = "site/public/data/board.json"
LOGOS = "site/public/data/team-logos.json"
WATERMARK = "data/watchlist_sent.json"

# How far ahead a reminder goes out. A day is early enough to be useful and
# late enough that the price on screen still resembles the price at kickoff.
DEFAULT_HOURS = 24.0


def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def team_index(path: str = LOGOS) -> dict[str, str]:
    """Full team name -> sport-scoped key, from the crest map.

    The board publishes full names ("Philadelphia 76ers"); the watchlist stores
    "nba:PHI". team-logos.json already holds both and is already deployed, so
    it is the mapping rather than a second table that can drift from it.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            teams = (json.load(fh) or {}).get("teams") or {}
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for key, t in teams.items():
        sport = str(t.get("sport") or "").lower()
        abbr = str(t.get("abbr") or "").upper()
        if sport and abbr:
            out[key] = f"{sport}:{abbr}"
    return out


def keys_for(name: str, index: dict[str, str]) -> str | None:
    """One team name -> its sport-scoped key, or None if we cannot say.

    None is normal and must stay silent: UFC events are two fighters, not two
    teams, and a fighter has no crest and no watchlist key.
    """
    return index.get(_norm(name))


def load_board(path: str = BOARD) -> list[dict]:
    """Every event on the published board, flattened, with its sport attached."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    for b in data.get("boards") or []:
        sport = str(b.get("sport") or "")
        for e in b.get("events") or []:
            out.append({**e, "sport": sport})
    return out


def upcoming(events: list[dict], index: dict[str, str], hours: float,
             now: datetime | None = None) -> list[dict]:
    """Games starting inside the window that have not started yet.

    Both bounds matter. Without the lower bound a finished game is "within 24
    hours" of now and would be reminded about after the fact; without the upper
    bound the first run of the season reminds everyone about everything.
    """
    now = now or datetime.now(timezone.utc)
    out: list[dict] = []
    for e in events:
        raw = e.get("starts")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ahead = (ts - now).total_seconds() / 3600.0
        if not (0 <= ahead <= hours):
            continue
        home, away = keys_for(e.get("home"), index), keys_for(e.get("away"), index)
        if not home and not away:
            continue          # fighters, or a team we cannot resolve — silent
        out.append({
            "game_id": str(e.get("id") or ""),
            "sport": e.get("sport") or "",
            "home": e.get("home"), "away": e.get("away"),
            "home_key": home, "away_key": away,
            "starts": ts.isoformat(),
            "hours_out": round(ahead, 2),
        })
    out.sort(key=lambda g: g["starts"])
    return out


def load_sent(path: str = WATERMARK) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_sent(sent: dict, path: str = WATERMARK) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sent, fh, indent=1, sort_keys=True)
        fh.write("\n")


def select_new(games: list[dict], sent: dict) -> list[dict]:
    """Games not already reminded about. Ids only — see the module docstring."""
    return [g for g in games if g["game_id"] and g["game_id"] not in sent]


def mark(sent: dict, games: list[dict], stamp: str | None = None) -> dict:
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    for g in games:
        sent[g["game_id"]] = stamp
    return sent


def prune(sent: dict, events: list[dict]) -> dict:
    """Drop watermark entries for games no longer on the board.

    Without this the file grows for the life of the project and every alert run
    reads and rewrites a larger artefact. A game that has left the board can
    never be reminded about again, so its entry has no work left to do.
    """
    live = {str(e.get("id") or "") for e in events}
    return {k: v for k, v in sent.items() if k in live}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return _selfcheck()

    index = team_index()
    if not index:
        print("no team map — cannot resolve watchlist keys", file=sys.stderr)
        return 1
    events = load_board(a.board)
    games = upcoming(events, index, a.hours)
    fresh = select_new(games, load_sent())
    for g in fresh:
        print(f"{g['sport']:<4} {g['hours_out']:>6}h  "
              f"{g['away_key'] or '-':<9} at {g['home_key'] or '-':<9}  "
              f"{g['away']} at {g['home']}")
    print(f"{len(games)} in window, {len(fresh)} unsent", file=sys.stderr)
    return 0


def _selfcheck() -> int:
    from datetime import timedelta
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    idx = {_norm("New York Knicks"): "nba:NYK",
           _norm("Philadelphia 76ers"): "nba:PHI",
           _norm("Buffalo Bills"): "nfl:BUF"}

    def ev(i, home, away, dh):
        return {"id": i, "home": home, "away": away, "sport": "x",
                "starts": (now + timedelta(hours=dh)).isoformat()}

    events = [
        ev("g1", "New York Knicks", "Philadelphia 76ers", 5),      # in window
        ev("g2", "Buffalo Bills", "New York Knicks", 40),          # too far out
        ev("g3", "New York Knicks", "Philadelphia 76ers", -2),     # already started
        ev("g4", "Cameron Nelson", "Meng Ding", 6),                # fighters
        {"id": "g5", "home": "New York Knicks", "away": "Buffalo Bills",
         "sport": "x", "starts": "not-a-date"},                    # junk
        {"id": "g6", "home": "New York Knicks", "away": "Buffalo Bills",
         "sport": "x"},                                            # no start
    ]
    got = upcoming(events, idx, 24.0, now=now)
    assert [g["game_id"] for g in got] == ["g1"], got
    assert got[0]["home_key"] == "nba:NYK" and got[0]["away_key"] == "nba:PHI"

    # a game with ONE resolvable side still qualifies: somebody may follow it
    one = upcoming([ev("g7", "New York Knicks", "Nobody At All", 3)], idx, 24.0, now=now)
    assert len(one) == 1 and one[0]["away_key"] is None, one

    # dedupe, and the watermark carries ids only
    sent = mark({}, got)
    assert select_new(got, sent) == []
    assert list(sent) == ["g1"]
    assert not any("@" in k for k in sent), "watermark must never hold an address"

    # prune drops games that left the board
    assert prune({"g1": "t", "gone": "t"}, events) == {"g1": "t"}

    # window boundaries are inclusive at 0 and at the limit, exclusive beyond
    edge = upcoming([ev("a", "New York Knicks", "Buffalo Bills", 0),
                     ev("b", "New York Knicks", "Buffalo Bills", 24),
                     ev("c", "New York Knicks", "Buffalo Bills", 24.01)],
                    idx, 24.0, now=now)
    assert [g["game_id"] for g in edge] == ["a", "b"], edge

    print("watchlist.selfcheck: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
