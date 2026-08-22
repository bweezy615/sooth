"""Every sealed slate past its settle time must have a published grade.

PRODUCT.md commits to four things about the pick engine, and the first is that
a sealed slate is graded and published whether it wins or loses. That was a
promise with no mechanism, and the gap had a specific shape: grade.yml ends with

    if git diff --cached --quiet; then echo "nothing newly settled"; exit 0

An empty result is success. So a sealed week that is never graded looks exactly
like a week where nothing was due — green check, no commit, no signal anywhere.
The single failure PRODUCT.md names is the one failure CI reported as fine.

This closes that. For every sealed slate whose last kickoff is more than
GRACE_HOURS ago, a published graded artifact must exist. Absence exits non-zero
and names the slate.

Deliberately dumb about *what* the grade says. A losing week and a winning week
are equally acceptable here and the check cannot tell them apart, which is the
point — the promise is that the grade is published, not that it is good.

    python -m scripts.check_sealed_graded        # or: python scripts/check_sealed_graded.py

Not yet on the trust surface. Failing the workflow tells us; it does not tell a
reader, and the promise is made to the reader. Publishing "N slates sealed, N
graded, 0 overdue" next to the ledger is the version that would actually be
checkable from outside, and belongs with whoever owns seal/grade.
"""

from __future__ import annotations

import datetime
import glob
import json
import sys
from pathlib import Path

PUBLIC = Path("site/public/data")

# Games run about three and a half hours; a Monday nighter settles overnight.
# 24h after the LAST kickoff on the slate is late enough that a missing grade
# is a real absence rather than a scheduling artifact, and early enough that it
# is caught in the same week it happened.
GRACE_HOURS = 24.0


def sealed_slates() -> list[dict]:
    """Every slate that made a public commitment, by the presence of a root."""
    out = []
    for f in sorted(glob.glob(str(PUBLIC / "*.json"))):
        p = Path(f)
        # .graded / .commitment / .reveal are companions, not slates
        if any(s in p.name for s in (".graded.", ".commitment.", ".reveal.")):
            continue
        try:
            d = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        if not isinstance(d, dict) or "merkle_root" not in d:
            continue
        if not d.get("slate_id"):
            continue
        out.append(d)
    return out


def last_kickoff(slate: dict) -> datetime.datetime | None:
    times = []
    for g in slate.get("games") or []:
        t = g.get("kickoff") or g.get("commence_time") or g.get("starts")
        if t:
            times.append(t)
    if not times:
        # A slate with no kickoffs cannot be judged overdue, and guessing would
        # produce exactly the false alarm that gets a check switched off.
        return None
    try:
        return datetime.datetime.fromisoformat(max(times).replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    slates = sealed_slates()
    overdue, pending, graded, unknown = [], [], [], []

    for s in slates:
        sid = s["slate_id"]
        has_grade = (PUBLIC / f"{sid}.graded.json").exists()
        end = last_kickoff(s)
        if has_grade:
            graded.append(sid)
        elif end is None:
            unknown.append(sid)
        elif (now - end).total_seconds() / 3600.0 > GRACE_HOURS:
            overdue.append((sid, end, (now - end).total_seconds() / 3600.0))
        else:
            pending.append((sid, end))

    print(f"sealed slates: {len(slates)}")
    for sid in graded:
        print(f"  GRADED   {sid}")
    for sid, end in pending:
        print(f"  PENDING  {sid} — settles {end.isoformat()}")
    for sid in unknown:
        print(f"  NO KICKOFFS  {sid} — cannot determine settle time")

    if overdue:
        print()
        print("SEALED BUT NOT GRADED — PRODUCT.md commits to publishing these:")
        for sid, end, hrs in overdue:
            print(f"  {sid}: last kickoff {end.isoformat()}, {hrs:.0f}h ago, "
                  f"no {sid}.graded.json")
        print()
        print("A sealed slate is graded and published whether it wins or loses.")
        print("If publishing this one is inconvenient, the answer PRODUCT.md")
        print("gives is to stop selling the slate, not to leave it ungraded.")
        return 1

    print("\nno sealed slate is overdue for grading")
    return 0


if __name__ == "__main__":
    sys.exit(main())
