"""Injuries — who is actually available, and when we learned it.

Every "AI betting researcher" renders an injury panel. Almost none of them have
a source for it: a language model asked who is out tonight will browse, find a
three-week-old article, and report it with today's confidence. This module is
the difference between that and a number you can stand behind.

Two feeds, and they are not interchangeable:

**ESPN** (``site.api``) is the live snapshot — status, body part, and a
per-player ``date`` stamping when it last changed. It is the only feed that
moves between weekly reports, so it is what makes a report current at 4pm on a
Sunday. It carries **no history**: ask it tomorrow and today's answer is gone.

**nflverse** ``injuries_<season>.csv`` is the official Wednesday-through-Friday
practice report — the designations the league itself publishes. Authoritative
for game status, but it only exists during the regular season and only updates
weekly. It 404s until Week 1; that is expected, not a failure.

Where both speak, the official report wins on ``status`` and ESPN supplies
``updated_at`` and the note. Where only ESPN speaks, ESPN is it, and the row
says so in ``source``.

**Why this module snapshots.** ``docs/multisport-data-plan.md`` R3 has carried
the same instruction since August: start daily availability snapshotting on day
one, because who was OUT for a game played last month cannot be reconstructed
afterwards. ESPN overwrites. This is the first thing on main that actually does
it — every run appends to ``data/capture/injuries/<sport>/<date>.jsonl``,
append-only, never rewritten. The backfill for the games before today does not
exist and never will.

    python -m engine.injuries --sport nfl
    python -m engine.injuries --sport nfl --dry-run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
from pathlib import Path

import requests

# sport slug -> (ESPN league path, nflverse release stem or None)
SPORTS: dict[str, dict] = {
    "nfl": {"espn": "football/nfl", "label": "NFL", "nflverse": "injuries"},
    "nba": {"espn": "basketball/nba", "label": "NBA", "nflverse": None},
    "nhl": {"espn": "hockey/nhl", "label": "NHL", "nflverse": None},
    "mlb": {"espn": "baseball/mlb", "label": "MLB", "nflverse": None},
}

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/injuries"
NFLVERSE = ("https://github.com/nflverse/nflverse-data/releases/download"
            "/injuries/injuries_{season}.csv")

# ESPN publishes a row for every player it has ever flagged this season, and
# leaves it there as "Active" once they are back. An Active row is the absence
# of news; carrying it into a matchup report pads the panel with 500 healthy
# players and buries the four that matter.
AVAILABLE = {"active"}

# Ordered worst-first so a report can sort by how much the answer matters.
STATUS_RANK = {
    "out": 0, "injured reserve": 1, "suspension": 2,
    "doubtful": 3, "questionable": 4, "probable": 5,
}


def _rank(status: str) -> int:
    return STATUS_RANK.get((status or "").strip().lower(), 9)


def fetch_espn(sport: str, session: requests.Session) -> dict | None:
    """The live snapshot. Returns None on any failure — never a partial dict."""
    path = SPORTS[sport]["espn"]
    try:
        r = session.get(ESPN.format(path=path), timeout=45,
                        headers={"accept": "application/json"})
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def parse_espn(doc: dict) -> tuple[dict[str, list[dict]], str | None]:
    """ESPN's payload -> {team display name: [row, ...]}, plus its timestamp."""
    teams: dict[str, list[dict]] = {}
    for team in doc.get("injuries") or []:
        name = team.get("displayName")
        if not name:
            continue
        rows = []
        for inj in team.get("injuries") or []:
            status = (inj.get("status") or "").strip()
            if status.lower() in AVAILABLE:
                continue
            ath = inj.get("athlete") or {}
            det = inj.get("details") or {}
            rows.append({
                "player": ath.get("displayName"),
                "position": ((ath.get("position") or {}).get("abbreviation")),
                "status": status,
                # ESPN's own short code (Q/D/O), handy for a status pill.
                "abbr": ((inj.get("type") or {}).get("abbreviation")),
                "body_part": det.get("type"),
                "location": det.get("location"),
                "side": None if det.get("side") == "Not Specified" else det.get("side"),
                "return_date": det.get("returnDate"),
                # When ESPN last changed THIS row, not when we asked. The
                # difference is the whole value of the field.
                "updated_at": inj.get("date"),
                "note": inj.get("shortComment"),
                "source": "espn",
            })
        if rows:
            rows.sort(key=lambda r: (_rank(r["status"]), r["player"] or ""))
            teams[name] = rows
    return teams, doc.get("timestamp")


def fetch_official(season: int, session: requests.Session) -> list[dict] | None:
    """The league's own practice report. None when the season has not started.

    nflverse cuts this release once Week 1 reports land, so a 404 in August is
    the normal state of the world and must not read as an outage.
    """
    try:
        r = session.get(NFLVERSE.format(season=season), timeout=60)
        if r.status_code != 200:
            return None
        rows = list(csv.DictReader(io.StringIO(r.text)))
        return rows or None
    except (requests.RequestException, UnicodeDecodeError):
        return None


def latest_week(rows: list[dict]) -> str | None:
    weeks = {r.get("week") for r in rows if (r.get("week") or "").strip()}
    return max(weeks, key=lambda w: int(w)) if weeks else None


def merge_official(teams: dict[str, list[dict]], rows: list[dict]) -> dict:
    """Overlay the official designations onto the ESPN snapshot.

    Matched on normalised full name within the same league, not on team: a
    player traded mid-week is listed by ESPN under the new club and by the
    report under whoever filed it. Name is the stable key; the team we trust is
    ESPN's, because it is the one the schedule agrees with.
    """
    week = latest_week(rows)
    by_name = {}
    for r in rows:
        if week and r.get("week") != week:
            continue
        name = (r.get("full_name") or "").strip().lower()
        if name:
            by_name[name] = r

    matched = 0
    for players in teams.values():
        for p in players:
            r = by_name.get((p.get("player") or "").strip().lower())
            if not r:
                continue
            status = (r.get("report_status") or "").strip()
            if status:
                p["status"] = status          # the league outranks the wire
                p["abbr"] = status[:1].upper()
            p["body_part"] = (r.get("report_primary_injury") or "").strip() or p.get("body_part")
            p["practice_status"] = (r.get("practice_status") or "").strip() or None
            p["source"] = "nflverse+espn"
            matched += 1
        players.sort(key=lambda x: (_rank(x["status"]), x["player"] or ""))
    return {"week": week, "rows": len(by_name), "matched": matched}


def snapshot(sport: str, teams: dict[str, list[dict]], observed_at: str,
             root: Path) -> Path:
    """Append today's answer to the permanent record. Append-only, by design."""
    d = root / "data" / "capture" / "injuries" / sport
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{observed_at[:10]}.jsonl"
    with path.open("a") as fh:
        for team, players in teams.items():
            for p in players:
                fh.write(json.dumps({"observed_at": observed_at,
                                     "sport": sport, "team": team, **p}) + "\n")
    return path


def build(sport: str, root: Path, out_dir: Path, dry_run: bool = False) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    session = requests.Session()
    # Deliberately no custom user-agent: site.api.espn.com answers requests'
    # default UA with 200 and a polite "sooth/injuries (+url)" with 403. Naming
    # ourselves is the courteous thing to do and it is what breaks this feed.

    doc = fetch_espn(sport, session)
    out = out_dir / "injuries.json"

    if doc is None:
        # A blank injury panel does not read as "we could not reach ESPN", it
        # reads as "nobody is hurt" — the single most dangerous way for this
        # file to fail. Keep the last good answer and stamp the attempt.
        if not dry_run and out.exists():
            try:
                prev = json.loads(out.read_text())
                prev["checked_at"] = now.isoformat()
                prev["last_fetch_failed"] = True
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(prev, indent=1))
                os.replace(tmp, out)
                return prev
            except (json.JSONDecodeError, OSError):
                pass
        raise SystemExit(f"injuries: ESPN fetch failed for {sport} and no previous file to keep")

    teams, espn_ts = parse_espn(doc)
    season = int((doc.get("season") or {}).get("year") or now.year)

    official = None
    if SPORTS[sport]["nflverse"]:
        rows = fetch_official(season, session)
        official = merge_official(teams, rows) if rows else None

    payload = {
        "sport": sport,
        "label": SPORTS[sport]["label"],
        "season": season,
        "espn_timestamp": espn_ts,
        "official": official,          # None = no league report yet this season
        "n_teams": len(teams),
        "n_players": sum(len(v) for v in teams.values()),
        "teams": teams,
    }

    merged = {}
    if not dry_run and out.exists():
        try:
            merged = json.loads(out.read_text()).get("sports") or {}
        except (json.JSONDecodeError, OSError):
            merged = {}
    merged[sport] = payload

    result = {
        "generated_at": now.isoformat(),
        "checked_at": now.isoformat(),
        "last_fetch_failed": False,
        "note": ("Injury designations as published by ESPN, overlaid with the "
                 "league's official practice report where it exists. Status "
                 "changes; check the team's report before acting on it."),
        "sports": merged,
    }

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=1))
        os.replace(tmp, out)
        snapshot(sport, teams, now.isoformat(), root)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sport", default="nfl", choices=sorted(SPORTS))
    ap.add_argument("--out-dir", default="site/public/data")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and report, write nothing")
    a = ap.parse_args()

    res = build(a.sport, Path(a.root), Path(a.out_dir), a.dry_run)
    s = res["sports"][a.sport]
    off = s.get("official")
    print(f"{s['label']}: {s['n_players']} players on {s['n_teams']} teams "
          f"(ESPN {s['espn_timestamp']})")
    print("official report: " +
          (f"week {off['week']}, {off['matched']} of {s['n_players']} matched"
           if off else "not published yet this season (ESPN only)"))


if __name__ == "__main__":
    main()
