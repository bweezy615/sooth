"""How close to kickoff our own capture actually gets.

This is the measurement that decides whether a sport can be graded. A closing
line is the market's last word; an observation taken two days early is not one,
and scoring a model against it flatters the model without any single field in
the payload being untrue. `engine/adapters/base.py` says the same thing about
`is_closing` in stronger terms.

Run it before wiring any sport's own capture into `load_historical_lines`, and
again after changing capture cadence, which is the thing that actually moves
these numbers:

    python scripts/capture_closeness.py --sport ncaaf
    python scripts/capture_closeness.py --sport nfl --provenance own_capture

Findings as of 2026-09-09 are written up in
docs/plans/2026-09-09-cfb-closing-line-evidence.md. The short version: college
football's median gap is 55 minutes and 95% of played games have a price inside
three hours, but only 27% have one inside thirty minutes — against a purchased
NFL backfill that caught 16 books within 5-28 minutes of EVERY kickoff. Good
enough to be worth keeping, not good enough to grade against.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
from datetime import datetime, timezone


def _ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def measure(sport: str, provenance: str, now: datetime | None = None) -> dict:
    """Latest pre-kickoff observation per event, and runs per day.

    Only rows observed BEFORE kickoff count. A row stamped after kickoff is
    either a settled price or a clock problem, and neither is evidence about
    what the market said while the game could still be bet.

    Only events that have ALREADY KICKED OFF are scored. This is not a detail.
    For a game still days away, "minutes from our last observation to kickoff"
    measures how far away the game is, not how close we managed to get — we
    have not had the chance to observe it near kickoff yet. Including those
    events makes the capture look arbitrarily bad the further ahead the
    schedule is published, which on the first pass of this script put the NFL
    at a 15,864-minute median while its week 1 had not been played.
    """
    now = now or datetime.now(timezone.utc)
    latest: dict[str, datetime] = {}
    kickoff: dict[str, datetime] = {}
    runs: dict[str, set[str]] = collections.defaultdict(set)
    rows = 0

    for path in sorted(glob.glob(f"data/capture/{sport}/*.jsonl")):
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if provenance and r.get("provenance") != provenance:
                    continue
                ko, ob = _ts(r.get("kickoff")), _ts(r.get("observed_at"))
                if not ko or not ob:
                    continue
                # Minute resolution: one capture run writes thousands of rows
                # sharing a timestamp, and it is the RUN we want to count.
                runs[ob.date().isoformat()].add(ob.strftime("%Y-%m-%dT%H:%M"))
                if ob >= ko:
                    continue
                rows += 1
                eid = str(r.get("event_id"))
                kickoff[eid] = ko
                if eid not in latest or ob > latest[eid]:
                    latest[eid] = ob

    played = [e for e in latest if kickoff[e] < now]
    gaps = sorted((kickoff[e] - latest[e]).total_seconds() / 60 for e in played)
    return {"rows": rows, "gaps": gaps, "runs": dict(runs),
            "events_seen": len(latest), "events_played": len(played)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="ncaaf")
    ap.add_argument("--provenance", default="own_capture",
                    help="empty string to count every row regardless of source")
    a = ap.parse_args()

    m = measure(a.sport, a.provenance)
    gaps, runs = m["gaps"], m["runs"]
    print(f"sport            : {a.sport}")
    print(f"provenance       : {a.provenance or '(any)'}")
    print(f"pre-kickoff rows : {m['rows']}")
    print(f"events observed  : {m['events_seen']}")
    print(f"  of which played: {m['events_played']}  (only these can be scored)")
    if not gaps:
        print("\nno observed event has kicked off yet — nothing to say about closeness")
        return

    def q(p: float) -> float:
        return gaps[min(len(gaps) - 1, int(len(gaps) * p))]

    print("\nminutes from our LAST observation to kickoff")
    print(f"  min {gaps[0]:.0f} | p25 {q(.25):.0f} | median {q(.5):.0f} | "
          f"p75 {q(.75):.0f} | p90 {q(.9):.0f} | max {gaps[-1]:.0f}")
    print()
    for thr in (15, 30, 60, 90, 180):
        n = sum(1 for g in gaps if g <= thr)
        print(f"  within {thr:>3} min of kickoff: {n:>5} / {len(gaps)} "
              f"({100 * n / len(gaps):.0f}%)")

    print("\ndistinct capture runs per UTC day")
    for day in sorted(runs)[-14:]:
        print(f"  {day}: {len(runs[day]):>3}")

    # The judgement, stated rather than left to the reader: the purchased NFL
    # backfill that engine/closing.py trusts caught its books within 5-28
    # minutes of kickoff, so that is the bar being compared against.
    near = sum(1 for g in gaps if g <= 30) / len(gaps)
    print(f"\n{near * 100:.0f}% of events have a price inside 30 minutes of kickoff.")
    print("The purchased NFL backfill managed 5-28 minutes for every game.")
    if near < 0.9:
        print("NOT a closing-line source. Grading against it would flatter the model.")


if __name__ == "__main__":
    main()
