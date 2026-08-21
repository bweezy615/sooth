"""Fold every published graded slate into one pick-engine record file.

    python scripts/publish_record.py            # live slates only
    python scripts/publish_record.py --rehearsal REPLAY-2025-W0{5,6,7}

site/public/data/pickengine-record.json is the single source picks.html and
record.html read. It is never hand-typed: delete it and this script rebuilds
it byte-identical from the graded artifacts. Rehearsal (replayed) weeks are
carried under an explicit flag and excluded from the season-to-date record —
a replay proves the pipeline, it is not a result we earned in public.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SITE = Path("site/public/data")
INDEPENDENT_PREFIX = "elo+epa-v1"   # matches both live (+iso) and replay tags


def _week(doc: dict, rehearsal: bool) -> dict:
    picks = [p for p in doc.get("picks", [])
             if str(p.get("model", "")).startswith(INDEPENDENT_PREFIX)]
    return {
        "slate_id": doc.get("slate_id"),
        "rehearsal": rehearsal,
        "merkle_root": doc.get("merkle_root"),
        "n_settled": doc.get("n_settled"),
        "clv_coverage": doc.get("clv_coverage"),
        "by_model": doc.get("by_model", {}),
        "picks": picks,
    }


def build(rehearsal_ids: list[str]) -> dict:
    weeks = []
    for f in sorted(SITE.glob("*.graded.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sid = str(doc.get("slate_id", ""))
        weeks.append(_week(doc, sid.startswith("REPLAY-") or sid in rehearsal_ids))

    live = [w for w in weeks if not w["rehearsal"]]
    wins = losses = 0
    clvs: list[float] = []
    clv_have = clv_settled = 0
    for w in live:
        for p in w["picks"]:
            if p["won"] is True:
                wins += 1
            elif p["won"] is False:
                losses += 1
            if p["won"] is not None:
                clv_settled += 1
                if p["clv"] is not None:
                    clv_have += 1
                    clvs.append(float(p["clv"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "python scripts/publish_record.py",
        "note": ("Independent model only - the one that never sees the line. "
                 "Rehearsal weeks replay settled games through the live "
                 "pipeline and are excluded from the record."),
        "rehearsal": (len(weeks) - len(live)) or False,
        "independent_record": f"{wins}-{losses}" if (wins or losses) else None,
        "mean_clv": (round(sum(clvs) / len(clvs) * 100, 2) if clvs else None),
        "clv_coverage": (round(clv_have / clv_settled, 4) if clv_settled else None),
        "weeks": weeks,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehearsal", nargs="*", default=[],
                    help="slate ids to force-mark as rehearsal")
    args = ap.parse_args()
    doc = build(list(args.rehearsal))
    out = SITE / "pickengine-record.json"
    out.write_text(json.dumps(doc, indent=2))
    n_weeks = len(doc["weeks"])
    print(f"{out}  ({n_weeks} week{'s' if n_weeks != 1 else ''}, "
          f"record {doc['independent_record']}, "
          f"rehearsal weeks: {doc['rehearsal'] or 0})")


if __name__ == "__main__":
    main()
