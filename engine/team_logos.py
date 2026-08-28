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
  NBA   https://a.espncdn.com/i/teamlogos/nba/500/{abbr}.png
  NCAAF https://a.espncdn.com/i/teamlogos/ncaa/500/{teamId}.png — addressed by
        ESPN's own numeric team id, not an abbreviation. This one is NOT a
        table: FBS is ~136 teams and its membership changes every year, so a
        hand table would be stale by November. ESPN's group-80 roster
        (group 80 is FBS, the same filter engine/capture.py uses and for the
        same reason) is one request for the roster plus one per team, run
        offline like the rest of this script.
  NHL   https://a.espncdn.com/i/teamlogos/nhl/500/{abbr}.png — same CDN. ESPN's
        JSON teams API (site.api.espn.com) answers 403 to server-side callers,
        so the name -> abbreviation bridge is a table here rather than a fetch.
        That is acceptable precisely because every URL is HEAD-verified below:
        a stale or mistyped abbreviation drops the team rather than shipping a
        broken image, and the roster of both leagues changes about once a
        decade. Keys are the full names the odds feed publishes.

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
import time
import unicodedata
import re
from pathlib import Path

import requests

from .hitrates import API

OUT = "site/public/data/team-logos.json"
NFL_STATS = "site/public/data/teamstats-nfl.json"
MLB_LOGO = "https://www.mlbstatic.com/team-logos/{id}.svg"
NFL_LOGO = "https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png"
ESPN_LOGO = "https://a.espncdn.com/i/teamlogos/{league}/500/{abbr}.png"
NCAAF_LOGO = "https://a.espncdn.com/i/teamlogos/ncaa/500/{id}.png"
NCAAF_ROSTER = ("http://sports.core.api.espn.com/v2/sports/football/leagues/"
                "college-football/seasons/{season}/types/2/groups/80/teams"
                "?limit=400")
PAUSE = 0.2  # polite guest on an undocumented free endpoint, as in capture.py

# Full name -> ESPN abbreviation. The name side must match what the odds feed
# returns, because that is the key the board looks up.
NBA_TEAMS = {
    "Atlanta Hawks": "atl", "Boston Celtics": "bos", "Brooklyn Nets": "bkn",
    "Charlotte Hornets": "cha", "Chicago Bulls": "chi",
    "Cleveland Cavaliers": "cle", "Dallas Mavericks": "dal",
    "Denver Nuggets": "den", "Detroit Pistons": "det",
    "Golden State Warriors": "gs", "Houston Rockets": "hou",
    "Indiana Pacers": "ind", "LA Clippers": "lac",
    "Los Angeles Lakers": "lal", "Memphis Grizzlies": "mem",
    "Miami Heat": "mia", "Milwaukee Bucks": "mil",
    "Minnesota Timberwolves": "min", "New Orleans Pelicans": "no",
    "New York Knicks": "ny", "Oklahoma City Thunder": "okc",
    "Orlando Magic": "orl", "Philadelphia 76ers": "phi",
    "Phoenix Suns": "phx", "Portland Trail Blazers": "por",
    "Sacramento Kings": "sac", "San Antonio Spurs": "sa",
    "Toronto Raptors": "tor", "Utah Jazz": "utah",
    "Washington Wizards": "wsh",
}
NHL_TEAMS = {
    "Anaheim Ducks": "ana", "Boston Bruins": "bos", "Buffalo Sabres": "buf",
    "Calgary Flames": "cgy", "Carolina Hurricanes": "car",
    "Chicago Blackhawks": "chi", "Colorado Avalanche": "col",
    "Columbus Blue Jackets": "cbj", "Dallas Stars": "dal",
    "Detroit Red Wings": "det", "Edmonton Oilers": "edm",
    "Florida Panthers": "fla", "Los Angeles Kings": "la",
    "Minnesota Wild": "min", "Montreal Canadiens": "mtl",
    "Nashville Predators": "nsh", "New Jersey Devils": "nj",
    "New York Islanders": "nyi", "New York Rangers": "nyr",
    "Ottawa Senators": "ott", "Philadelphia Flyers": "phi",
    "Pittsburgh Penguins": "pit", "San Jose Sharks": "sj",
    "Seattle Kraken": "sea", "St. Louis Blues": "stl",
    "Tampa Bay Lightning": "tb", "Toronto Maple Leafs": "tor",
    "Utah Mammoth": "utah", "Vancouver Canucks": "van",
    "Vegas Golden Knights": "vgk", "Washington Capitals": "wsh",
    "Winnipeg Jets": "wpg",
}


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


def espn_league(session: requests.Session, league: str, table: dict) -> dict:
    """One ESPN-hosted league from a name -> abbreviation table."""
    out = {}
    for name, abbr in table.items():
        url = ESPN_LOGO.format(league=league, abbr=abbr)
        if not ok(session, url):
            continue
        out[norm(name)] = {"sport": league, "name": name,
                           "abbr": abbr.upper(), "logo": url}
    return out


def ncaaf(session: requests.Session, season: int = 2026) -> dict:
    """FBS crests, read from ESPN's roster rather than typed into this file.

    Returns {} on any failure rather than raising: a crest is an aid to
    scanning and never carries a fact, so the worst case is the board we
    already ship, with college teams named in text.
    """
    try:
        r = session.get(NCAAF_ROSTER.format(season=season), timeout=25)
        r.raise_for_status()
        items = r.json().get("items") or []
    except (requests.RequestException, ValueError):
        return {}

    out: dict = {}
    for item in items:
        ref = str(item.get("$ref") or "")
        if not ref:
            continue
        try:
            t = session.get(ref, timeout=20).json()
        except (requests.RequestException, ValueError):
            continue
        time.sleep(PAUSE)
        name, tid = t.get("displayName"), t.get("id")
        if not name or not tid:
            continue
        url = NCAAF_LOGO.format(id=tid)
        if not ok(session, url):
            continue
        out[norm(name)] = {"sport": "ncaaf", "name": name,
                           "abbr": str(t.get("abbreviation") or "").upper(),
                           "logo": url}
    return out


def nba(session: requests.Session) -> dict:
    return espn_league(session, "nba", NBA_TEAMS)


def nhl(session: requests.Session) -> dict:
    return espn_league(session, "nhl", NHL_TEAMS)


def main() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-site/1.0 (+https://sooth.bet)"
    teams = {}
    for label, fn in (("mlb", mlb), ("nfl", nfl), ("nba", nba), ("nhl", nhl),
                      ("ncaaf", ncaaf)):
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
