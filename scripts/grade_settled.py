"""Grade every settled slate and publish the running record.

Runs unattended. Until Week 1 settles there is nothing to grade, and the
correct output in that state is an explicit zero, not an empty file and not a
placeholder. A record that says "0 graded" is information; a record that says
nothing invites someone to fill the silence.

What it does:

  1. Find every committed slate in data/ledger/.
  2. Grade the ones whose games have finished.
  3. Write a per-slate graded artefact beside the commitment, append-only.
  4. Write a rollup to site/public/data/record.json for the site to read.

The rollup carries ``graded: 0`` honestly when nothing has settled, and the
site is expected to render that as "no graded picks yet" rather than hiding
the section.

    python scripts/grade_settled.py
    python scripts/grade_settled.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.commit import commitment_history          # noqa: E402
from engine.grade import grade_slate                  # noqa: E402

LEDGER = ROOT / "data/ledger"
PUBLIC = ROOT / "site/public/data"


def slate_ids() -> list[str]:
    ids = {p.name.split(".commitment")[0]
           for p in LEDGER.glob("*.commitment.v*.json")}
    if not ids:
        ids = {p.name.split(".commitment")[0]
               for p in LEDGER.glob("*.commitment.json")}
    return sorted(ids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    slates, totals = [], {"graded": 0, "wins": 0, "losses": 0}
    by_model: dict[str, dict] = {}

    for sid in slate_ids():
        history = commitment_history(sid, LEDGER)
        kickoff = history[-1]["earliest_kickoff"] if history else None
        try:
            g = grade_slate(sid, ledger_dir=LEDGER,
                            out_dir=None if args.dry_run else LEDGER)
        except (FileNotFoundError, KeyError) as exc:
            print(f"  {sid}: skipped ({exc.__class__.__name__})")
            continue

        entry = {
            "slate_id": sid,
            "merkle_root": g.merkle_root,
            "earliest_kickoff": kickoff,
            "predictions": g.n_predictions,
            "settled": g.n_settled,
            "by_model": g.by_model,
            "clv_coverage": g.clv_coverage,
        }
        slates.append(entry)
        totals["graded"] += g.n_settled

        for name, m in g.by_model.items():
            acc = by_model.setdefault(name, {"n": 0, "wins": 0, "losses": 0})
            acc["n"] += m["n"]
            wins = int(m["record"].split("-")[0])
            acc["wins"] += wins
            acc["losses"] += m["n"] - wins

        state = "settled" if g.n_settled else "sealed, not yet played"
        print(f"  {sid}: {g.n_predictions} predictions, {state}")

    for name, acc in by_model.items():
        played = acc["wins"] + acc["losses"]
        acc["win_pct"] = round(acc["wins"] / played, 4) if played else None
        totals["wins"] += acc["wins"]
        totals["losses"] += acc["losses"]

    doc = {
        "generated_at": now.isoformat(),
        "graded_predictions": totals["graded"],
        "record": {"wins": totals["wins"], "losses": totals["losses"]},
        "by_model": by_model,
        "slates": slates,
        "note": ("Live record of predictions sealed before kickoff and graded "
                 "after. Zero means nothing has settled yet, not that results "
                 "are withheld. Backtest figures are separate and live on the "
                 "methodology page."),
    }

    if not args.dry_run:
        PUBLIC.mkdir(parents=True, exist_ok=True)
        (PUBLIC / "record.json").write_text(json.dumps(doc, indent=1))

    print()
    print(f"slates             : {len(slates)}")
    print(f"graded predictions : {totals['graded']}")
    print(f"live record        : {totals['wins']}-{totals['losses']}")
    if not totals["graded"]:
        print("nothing has settled yet — publishing an explicit zero")
    if args.dry_run:
        print("(dry run, nothing written)")


if __name__ == "__main__":
    main()
