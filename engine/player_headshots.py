"""Player headshots for the props board, keyed by the names the board publishes.

Same shape and the same discipline as engine.team_logos: resolve offline, HEAD
-verify every URL, write a static map the pages read, and fail to *nothing*
rather than to something wrong.

    MLB  https://img.mlbstatic.com/mlb-photos/image/upload/w_180,q_auto:best/
         v1/people/{personId}/headshot/67/current — MLB's own image CDN,
         sized and re-encoded server-side, so the page pulls ~6KB instead of a
         full-resolution portrait. Person ids come from the same free StatsAPI
         the hit-rate models already query, so this adds no new data source.

Only MLB. The props board is MLB-only today, and the other leagues have no
comparable free id->image bridge: ESPN hosts NFL and NBA headshots but its
JSON API answers 403 to server-side callers, and guessing ids is exactly the
failure mode the whole module is built to avoid.

**The identity risk is the point of this file.** A crest on the wrong game is
embarrassing; a FACE on the wrong player is a different category of wrong — it
is a photograph of a real person attached to a claim about someone else. So
resolution reuses hitrates.find_player, which requires an exact full-name match
and returns None on a duplicate name (there are two Luis Garcias pitching).
Anything ambiguous is dropped and the row renders as it does today, with the
player's name in text.

These are editorial images used to identify the players a market covers. Sooth
is unaffiliated with any league, team or player, which every page states.

    python -m engine.player_headshots
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

import requests

from .hitrates import API, find_player

OUT = "site/public/data/player-headshots.json"
PROPS = "site/public/data/props.json"
SHOT = ("https://img.mlbstatic.com/mlb-photos/image/upload/"
        "w_180,q_auto:best/v1/people/{pid}/headshot/67/current")

# A board can carry a few hundred props across a slate; every miss costs one
# search call. This is a cron job, not a request path, but there is no reason
# to hammer a free public API — the cache below means one call per NAME, not
# one per prop, and the previous map is reused for names already resolved.
TIMEOUT = 20


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def ok(session: requests.Session, url: str) -> bool:
    try:
        r = session.head(url, timeout=15, allow_redirects=True)
        return r.status_code == 200 and "image" in r.headers.get("content-type", "")
    except requests.RequestException:
        return False


def players_on_board(path: str = PROPS) -> list[str]:
    """Every distinct player name the props board currently publishes."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return []
    names: dict[str, str] = {}
    for b in doc.get("boards", []):
        if b.get("sport") not in (None, "mlb"):
            continue
        for ev in b.get("events", []):
            for p in ev.get("props", []):
                n = (p.get("player") or "").strip()
                if n:
                    names.setdefault(norm(n), n)
    return sorted(names.values())


def load_existing(path: str = OUT) -> dict:
    """Yesterday's map. Resolution is stable, so a name already resolved is not
    looked up again — which keeps a daily cron to a handful of calls."""
    try:
        return json.loads(Path(path).read_text()).get("players", {})
    except (OSError, json.JSONDecodeError):
        return {}


def build(session: requests.Session, names: list[str], existing: dict) -> dict:
    out: dict[str, dict] = {}
    resolved = skipped = reused = 0
    for name in names:
        key = norm(name)
        prior = existing.get(key)
        if prior and prior.get("img"):
            out[key] = prior
            reused += 1
            continue
        pid = find_player(name, session)
        if not pid:
            # Unknown or ambiguous. Dropping is the correct outcome: see the
            # module docstring on why a wrong face is worse than no face.
            skipped += 1
            continue
        url = SHOT.format(pid=pid)
        if not ok(session, url):
            skipped += 1
            continue
        out[key] = {"name": name, "id": pid, "img": url, "sport": "mlb"}
        resolved += 1
    print(f"players: {resolved} newly resolved, {reused} reused, {skipped} dropped")
    return out


def main() -> int:
    names = players_on_board()
    if not names:
        print("no players on the props board — nothing to resolve")
        return 0
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-site/1.0 (+https://sooth.bet)"
    players = build(session, names, load_existing())
    payload = {
        "note": "editorial player images, shown to identify the players a "
                "market covers. Sooth is unaffiliated with any league, team "
                "or player.",
        "source": "statsapi.mlb.com person ids; img.mlbstatic.com images",
        "n": len(players),
        "players": players,
    }
    out = Path(OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True))
    os.replace(tmp, out)
    print(f"wrote {OUT} — {len(players)} players")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
