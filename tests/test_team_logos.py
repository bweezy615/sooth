"""The crest map must never be able to show the WRONG crest.

crest.js is explicit that a missing crest is fine and a wrong one is not: "a
wrong crest beside a matchup is worse than no crest, because it looks
authoritative." It defends the unscoped abbreviation lookup against collisions
(ATL is both the Braves and the Falcons) by resolving an ambiguous abbreviation
to nothing.

The SPORT-SCOPED lookup has no such defence. It is assigned unconditionally,
under the comment "unambiguous, always safe" - which was true when every league
in the map had 30-32 teams with hand-checked abbreviations. On 2026-08-28 the
map gained 138 FBS college teams from ESPN's roster. They happen not to
collide. Nothing was checking that they don't, and nothing would have said so
if a future roster made them.
"""

from __future__ import annotations

import collections
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGOS = ROOT / "site/public/data/team-logos.json"


def _norm(s: str) -> str:
    """The same key crest.js builds, so this checks what the browser will do."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _teams() -> dict:
    return json.loads(LOGOS.read_text(encoding="utf-8"))["teams"]


def test_no_two_teams_in_one_sport_share_an_abbreviation():
    seen = collections.defaultdict(list)
    for entry in _teams().values():
        abbr = _norm(entry.get("abbr") or "")
        if not abbr:
            continue
        seen[(entry.get("sport"), abbr)].append(entry.get("name"))

    clashes = {k: v for k, v in seen.items() if len(v) > 1}
    assert not clashes, (
        "crest.js indexes ABBR['<sport>:<abbr>'] unconditionally, so a shared "
        "abbreviation inside one sport silently resolves to whichever team was "
        "indexed last - a confidently wrong crest. Clashes: "
        + "; ".join(f"{s}:{a} -> {', '.join(n)}" for (s, a), n in clashes.items())
    )


def test_every_entry_can_actually_be_looked_up_by_name():
    """The map is keyed by the normalised name; an entry keyed under anything
    else is dead weight the board can never hit."""
    wrong = [k for k, e in _teams().items() if k != _norm(e.get("name") or "")]
    assert not wrong, f"entries whose key is not norm(name): {wrong[:10]}"


def test_college_football_is_present_and_scoped():
    teams = _teams()
    cfb = {k: e for k, e in teams.items() if e.get("sport") == "ncaaf"}
    assert len(cfb) > 100, f"expected the FBS roster, found {len(cfb)}"
    # Every crest must carry its sport, or crest.js cannot scope the lookup
    # and falls back to the collision-prone unscoped one.
    assert all(e.get("sport") for e in teams.values())
    assert all("/ncaa/" in e["logo"] for e in cfb.values())


# --- the map has to be able to CHANGE


def test_the_crest_map_is_not_fetched_with_force_cache():
    """force-cache returns any cached copy, fresh or stale, indefinitely.

    It overrides the server's own policy instead of trusting it, and the
    server's policy is already correct: Cache-Control public, max-age=300 with
    an ETag. Measured on 2026-08-28: a page whose cache held the previous map
    was served 124 teams by force-cache while the origin served 262, so the 138
    college crests added that day could not have reached a returning visitor.

    Every previous edit to this map had the same problem and nobody noticed,
    because a missing crest looks exactly like a crest we never had.
    """
    js = (ROOT / "site/public/assets/crest.js").read_text(encoding="utf-8")
    # Match the fetch option, not the word: the reasoning above lives in a
    # comment in that file and names force-cache several times.
    calls = re.findall(r"fetch\([^)]*?cache:\s*\"([a-z-]+)\"", js)
    assert calls, "crest.js no longer fetches with an explicit cache mode"
    bad = [c for c in calls if c == "force-cache"]
    assert not bad, (
        "crest.js is back to force-cache: updates to team-logos.json or "
        "player-headshots.json would never reach a returning visitor."
    )
    assert set(calls) == {"default"}, f"unexpected cache modes: {sorted(set(calls))}"
