"""Dry-run a slate before it seals for real. Seals nothing.

    python scripts/slate_probe.py --season 2026 --week 2
    python scripts/slate_probe.py --season 2026 --week 2 --mocks

`engine.pipeline.weekly.build_slate` takes an `out_root` and writes everything
under it — data/ledger, data/pro, site/public/data — so pointing it at a temp
directory produces the real payload without touching the real ledger. The real
data/ledger is fingerprinted before and after and the run aborts if it moved.
PRO_PAYLOAD_KEY is set to a throwaway random key, so the live one is never read.

Why bother: W02 2026 is the first slate to carry the `ats` block (predicted
margin, edge against the number, and whether the edge clears the published bar)
and the first to render the SPREAD PLAY column on /picks. A slate seals once —
its Merkle root is anchored to a public commit and re-sealing is not a thing we
do — so the payload has to be right the first time.

`--mocks` additionally writes three fixtures into site/public/data (all matching
the gitignored `_mock-*.json` pattern) so the page can be driven against them:

    /picks.html?mock=/data/_mock-w02-open.json      the slate as a reader sees it
    /picks.html?mock=/data/_mock-w02-locked.json    the fail-closed teaser
    /picks.html?mock=/data/_mock-w02-zero.json      a week with no qualified play

Delete them when you are done; they are ignored by git but they are still
sitting in the directory the site serves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(d).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def write_mocks(out: Path, tag: str) -> list[Path]:
    """Fixtures for driving picks.html. Named so .gitignore catches them."""
    data = ROOT / "site/public/data"
    slate_file = next((out / "site/public/data").glob("*-nfl.json"))
    slate = json.loads(slate_file.read_text(encoding="utf-8"))
    meta = json.loads((out / "data/pro/latest.meta.json").read_text(encoding="utf-8"))

    # The slate id is rewritten to the mock name because the locked view fetches
    # /data/{slate_id}.json for its schedule; under the real id that fetch would
    # land on a file git does not ignore.
    slate["slate_id"] = f"_mock-{tag}"
    written = []

    def put(name: str, doc: dict) -> None:
        p = data / name
        p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        written.append(p)

    put(f"_mock-{tag}.json", slate)
    put(f"_mock-{tag}-open.json", dict(slate, locked=False))
    put(f"_mock-{tag}-locked.json", {
        "locked": True, "slate_id": f"_mock-{tag}",
        "game_count": meta["game_count"], "sealed_at": meta["sealed_at"],
        "merkle_root": meta["merkle_root"], "unlocks_at": meta["earliest_kickoff"],
        "top_divergence_matchup": meta["top_divergence_matchup"],
        "qualified_plays": meta["qualified_plays"],
        "note": "slate_probe fixture - nothing here is sealed",
    })

    # A week where the engine says nothing. Edges are scaled under the bar
    # rather than only flipping `qualified`: leaving a 4.35-point edge on a
    # slate marked no-play makes the page say "nothing sits 4 points off the
    # number - the furthest we get is 4.3", and a fixture that contradicts
    # itself teaches you nothing about the copy.
    zero = json.loads(json.dumps(slate))
    for g in zero["games"]:
        a = g.get("ats") or {}
        if a.get("edge") is not None and abs(a["edge"]) >= 4:
            a["edge"] = round(a["edge"] * 0.8, 2)
            a["pred_margin"] = round(g["spread_line"] + a["edge"], 2)
        a["qualified"] = False
        g["ats_rank"] = None
    put(f"_mock-{tag}-zero.json", dict(zero, locked=False))
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--mocks", action="store_true",
                    help="also write picks.html fixtures into site/public/data")
    ap.add_argument("--keep", action="store_true",
                    help="keep the throwaway root instead of deleting it")
    a = ap.parse_args()

    real_ledger = ROOT / "data/ledger"
    before = fingerprint(real_ledger)

    out = Path(tempfile.mkdtemp(prefix=f"slate-probe-{a.season}W{a.week:02d}-"))
    (out / "site/content").mkdir(parents=True)
    (out / "site/public/data").mkdir(parents=True)
    shutil.copy2(ROOT / "site/content/_figures.json", out / "site/content/")
    shutil.copy2(ROOT / "site/public/data/best_lines.json", out / "site/public/data/")

    os.environ["PRO_PAYLOAD_KEY"] = secrets.token_hex(32)   # throwaway, never the real one
    os.chdir(ROOT)          # the read-only nflverse caches are relative to the repo
    sys.path.insert(0, str(ROOT))
    from engine.pipeline.weekly import build_slate

    payload = build_slate(a.season, a.week, out_root=out)

    if fingerprint(real_ledger) != before:
        raise SystemExit("ABORT: the real data/ledger changed. Nothing should "
                         "have been written there.")

    games = payload["games"]
    qualified = [g for g in games if (g.get("ats") or {}).get("qualified")]
    print(f"real data/ledger unchanged  ({before[:16]}...)")
    print(f"slate       : {payload['slate_id']}  ({len(games)} games, "
          f"{payload['n_predictions']} sealed predictions)")
    print(f"merkle root : {payload['merkle_root']}   <- NOT anchored, throwaway")
    print(f"first kick  : {payload['earliest_kickoff']}")
    print(f"qualified   : {len(qualified)} of {len(games)}")
    for g in sorted(games, key=lambda g: -abs((g.get("ats") or {}).get("edge") or 0)):
        t = g.get("ats") or {}
        mark = "PLAY" if t.get("qualified") else "    "
        print(f"  {mark} {g['away']:>3} at {g['home']:<3} "
              f"line {str(g['spread_line']):>6}  margin {str(t.get('pred_margin')):>7}"
              f"  edge {str(t.get('edge')):>7}  "
              f"{'' if not t.get('pick') else t['pick']}"
              f"{' (dog)' if t.get('underdog') else ''}")

    if a.mocks:
        print("\nfixtures (gitignored, delete when done):")
        for p in write_mocks(out, f"w{a.week:02d}"):
            print(f"  {p.relative_to(ROOT).as_posix()}")

    if a.keep:
        print(f"\nthrowaway root kept: {out}")
    else:
        shutil.rmtree(out, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
