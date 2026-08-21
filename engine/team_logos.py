"""Team crests for the board, keyed by the team names our data already uses.

The board writes full team names ("Milwaukee Brewers") because that is what the
odds feed returns. Logos are addressed by id or abbreviation, so this builds the
bridge once, offline, and writes it to a static file the pages read. Doing the
lookup at render time would mean a network call per row on a 126-row board.

Sources, both official or long-stable public CDNs:

  MLB   https://www.mlbstatic.com/team-logos/{teamId}.svg — MLB's own asset,
        vector, a few KB, sharp at any size. Team ids come from the same free
        StatsAPI the models already use.
  NFL   https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png — abbreviations
        come from data/teamstats-nfl.json, which the research page already
        publishes, so no new source of truth.

Every URL is verified with a HEAD request before it is written. A logo that
404s renders as a broken image on a live board, and a missing crest is much
better than a broken one — anything that fails validation is simply left out,
and the page falls back to the team name alone.

These are club trademarks displayed to identify the teams a market covers.
Sooth is unaffiliated with any league, team or book, which every page states.

    python -m engine.team_logos
"""

from __future__ import annotations

import json
import os
import unicodedata
import re
from pathlib import Path

import requests

from .hitrates import API

OUT = "site/public/data/team-logos.json"
NFL_STATS = "site/public/data/teamstats-nfl.json"
MLB_LOGO = "https://www.mlbstatic.com/team-logos/{id}.svg"
NFL_LOGO = "https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png"


def norm(s: str) -> str:
    """Match key. Punctuation and case vary between feeds; the letters do not."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def ok(session: requests.Session, url: str) -> bool:
    try:
        r = session.head(url, timeout=15, allow_redirects=True)
        return r.status_code == 200 and "image" in r.headers.get("content-type", "")
    except requests.RequestException:
        return False


def mlb(session: requests.Session) -> dict:
    r = session.get(f"{API}/teams", params={"sportId": 1}, timeout=25)
    if r.status_code != 200:
        return {}
    out = {}
    for t in r.json().get("teams", []):
        tid, name = t.get("id"), t.get("name")
        if not tid or not name:
            continue
        url = MLB_LOGO.format(id=tid)
        if not ok(session, url):
            continue
        out[norm(name)] = {"sport": "mlb", "name": name,
                           "abbr": (t.get("abbreviation") or "").upper(),
                           "logo": url}
    return out


def nfl(session: requests.Session) -> dict:
    path = Path(NFL_STATS)
    if not path.exists():
        return {}
    teams = (json.loads(path.read_text()).get("teams") or {})
    out = {}
    for abbr, t in teams.items():
        name = t.get("name")
        if not name:
            continue
        url = NFL_LOGO.format(abbr=str(abbr).lower())
        if not ok(session, url):
            continue
        out[norm(name)] = {"sport": "nfl", "name": name,
                           "abbr": str(abbr).upper(), "logo": url}
    return out


def main() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-site/1.0 (+https://sooth.bet)"
    teams = {}
    for label, fn in (("mlb", mlb), ("nfl", nfl)):
        got = fn(session)
        print(f"{label}: {len(got)} crests verified")
        teams.update(got)
    payload = {"note": "club trademarks, shown to identify teams. "
                       "Sooth is unaffiliated with any league, team or book.",
               "n": len(teams), "teams": teams}
    out = Path(OUT)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True))
    os.replace(tmp, out)
    print(f"wrote {OUT} — {len(teams)} teams")


if __name__ == "__main__":
    main()
