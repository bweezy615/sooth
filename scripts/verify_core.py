"""Prove the two core claims: commitments detect tampering, calibration helps."""
import json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.schema import Prediction, Sport, Market
from engine.commit import commit_slate, verify_slate, merkle_root, merkle_proof, verify_proof, leaf_hash
from engine.calibrate import walk_forward_calibrate, expected_calibration_error, reliability
from engine.backtest import run

print("=" * 62)
print("1. COMMITMENT SCHEME")
print("=" * 62)
preds = [
    Prediction(event_id=f"2026_01_G{i}", sport=Sport.NFL, market=Market.MONEYLINE,
               selection="side_a", line=None, probability=0.5 + i / 100,
               model_version="elo-mov-v1",
               created_at=datetime(2026, 9, 9, 17, 0, tzinfo=timezone.utc),
               reference_price=-150)
    for i in range(16)
]
# This demo SEALS a slate and then deliberately TAMPERS with the reveal to
# prove verification catches it. Both of those are writes, so they happen in a
# throwaway directory under a throwaway slate id — never data/ledger.
#
# It used to run against the real ledger with the real slate id. Running it
# re-sealed 2026-W01-nfl (minting a commitment that "supersedes" the published
# one, which is indistinguishable from an operator quietly re-sealing picks)
# and left predictions[3].probability rewritten to 0.99 on disk. One `git add`
# after a demo run would have published a ledger that fails its own verifier.
DEMO_SLATE = "demo-commitment-check"
with tempfile.TemporaryDirectory() as ledger:
    c = commit_slate(DEMO_SLATE, "nfl", preds, out_dir=ledger)
    print(f"slate committed   : {c.n_predictions} predictions")
    print(f"merkle root       : {c.root}")
    print(f"verify_slate()    : {verify_slate(DEMO_SLATE, ledger)}")

    # single-pick inclusion proof
    leaves = [leaf_hash(p) for p in preds]
    proof = merkle_proof(leaves, 7)
    print(f"inclusion proof #7: {verify_proof(leaves[7], proof, c.root)} ({len(proof)} steps)")

    # tamper test: silently change a losing pick after the fact
    # commit_slate only writes versioned files; the unversioned reveal.json the
    # old code opened existed solely because the REAL slate had been published
    # there — which is how this demo ended up tampering with production data.
    p = Path(ledger) / f"{DEMO_SLATE}.reveal.v1.json"
    d = json.loads(p.read_text())
    d["predictions"][3]["probability"] = 0.99
    p.write_bytes(json.dumps(d, sort_keys=True, separators=(",", ":")).encode())
    print(f"after tampering   : {verify_slate(DEMO_SLATE, ledger)}  <- must be False")

print()
print("=" * 62)
print("2. CALIBRATION (walk-forward, fitted only on prior seasons)")
print("=" * 62)
rep = run()
f = walk_forward_calibrate(rep.frame)
y = f["home_won"].to_numpy(float)
raw, cal = f["p_home"].to_numpy(float), f["p_home_cal"].to_numpy(float)
mkt = f["market_p_home"].to_numpy(float)

print(f"n                     : {len(f)}")
print(f"ECE raw model         : {expected_calibration_error(raw, y):.5f}")
print(f"ECE calibrated        : {expected_calibration_error(cal, y):.5f}")
print(f"ECE market (devig)    : {expected_calibration_error(mkt, y):.5f}")
print()
print(f"Brier raw             : {np.mean((raw-y)**2):.5f}")
print(f"Brier calibrated      : {np.mean((cal-y)**2):.5f}")
print(f"Brier market          : {np.mean((mkt-y)**2):.5f}")
print()
print("calibrated reliability:")
print(reliability(cal, y).to_string(index=False))
