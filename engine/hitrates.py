"""Hit rates — how a player has actually performed against today's prop line.

The number on the props board says what the books think; this module says what
the player has done. For every captured prop we pull the player's game log
from MLB's public StatsAPI (free, no key) and count how often their stat
cleared today's line: last 5, last 10, and season.

A hit rate is a record, not a prediction. 7-of-10 over a line says nothing
about tonight on its own — but shown NEXT to the price, it lets a bettor see
at a glance when a book's line disagrees with recent reality, which is the
same disagreement this whole site exists to surface.

Stats come from statsapi.mlb.com, the same public API every scores site uses.
No scraping, no third-party product involved.

    python -m engine.hitrates          # annotate site/public/data/props.json
"""

from __future__ import annotations

import argparse
import json
import os
import time
import unicodedata
from pathlib import Path

import requests

API = "https://statsapi.mlb.com/api/v1"

# prop market key -> (statsapi group, gameLog stat field)
MARKET_STAT = {
    "batter_total_bases": ("hitting", "totalBases"),
    "batter_hits": ("hitting", "hits"),
    "pitcher_strikeouts": ("pitching", "strikeOuts"),
}


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def find_player(name: str, session: requests.Session) -> int | None:
    r = session.get(f"{API}/people/search",
                    params={"names": name}, timeout=20)
    if r.status_code != 200:
        return None
    people = r.json().get("people", [])
    want = norm(name)
    matches = [p for p in people if norm(p.get("fullName", "")) == want]
    if len(matches) == 1:
        return matches[0].get("id")
    # No exact match, or an ambiguous duplicate name (two Luis Garcias):
    # publishing the WRONG player's record is worse than publishing none.
    return None


def game_log(pid: int, group: str, season: int,
             session: requests.Session) -> list[float]:
    r = session.get(f"{API}/people/{pid}/stats",
                    params={"stats": "gameLog", "group": group,
                            "season": season}, timeout=20)
    if r.status_code != 200:
        return []
    for s in r.json().get("stats", []):
        vals = []
        for sp in s.get("splits", []):
            v = sp.get("stat", {})
            vals.append(v)
        return vals
    return []


def rate(values: list[float], line: float) -> dict:
    overs = sum(1 for v in values if v > line)
    return {"n": len(values), "over": overs}


def annotate(props_path: str = "site/public/data/props.json",
             season: int = 2026) -> dict:
    path = Path(props_path)
    doc = json.loads(path.read_text())
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-hitrates/1.0 (+https://sooth.bet)"

    cache: dict[tuple, list] = {}
    pid_cache: dict[str, int | None] = {}
    looked = hit = 0

    for board in doc.get("boards", []):
        if board["sport"] != "mlb":
            continue
        for ev in board["events"]:
            for p in ev["props"]:
                m = MARKET_STAT.get(p["market"])
                if not m:
                    continue
                group, field = m
                looked += 1
                name = p["player"]
                if name not in pid_cache:
                    pid_cache[name] = find_player(name, session)
                    time.sleep(0.2)   # be polite to a free API
                pid = pid_cache[name]
                if not pid:
                    continue
                key = (pid, group)
                if key not in cache:
                    cache[key] = game_log(pid, group, season, session)
                    time.sleep(0.2)
                stats = cache[key]
                vals = []
                for g in stats:
                    v = g.get(field)
                    if v is None:
                        continue
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        continue
                if not vals:
                    continue
                line = p["line"]
                p["hit"] = {
                    "l5": rate(vals[-5:], line),
                    "l10": rate(vals[-10:], line),
                    "season": rate(vals, line),
                }
                hit += 1

    doc["hitrates"] = {"source": "statsapi.mlb.com gameLog",
                       "season": season,
                       "annotated": hit, "eligible": looked}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, path)
    return doc["hitrates"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", default="site/public/data/props.json")
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    res = annotate(a.props, a.season)
    print(f"annotated {res['annotated']}/{res['eligible']} props "
          f"from {res['source']}")


if __name__ == "__main__":
    main()
