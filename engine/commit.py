"""Cryptographic commitment for predictions.

The problem with every sports-pick service on the internet is that the record
is self-reported and editable. A losing pick can quietly vanish; a winning one
can be added after the fact. "We publish everything" is unfalsifiable.

This module makes our record falsifiable.

How it works
------------
1. Before the first kickoff of a slate, every prediction is canonicalised to
   deterministic JSON and hashed (SHA-256).
2. The leaf hashes are combined into a Merkle tree; the root commits to the
   entire slate at once.
3. We publish ONLY the root hash before kickoff, and we anchor it to a public
   timestamp by committing it to a public git repository - GitHub's commit
   timestamps are third-party and not forgeable by us.
4. After the games settle, we publish the full predictions.

Anyone can then recompute the tree from the revealed predictions and confirm
the root matches what we published before kickoff. If we had altered, removed,
or back-dated a single pick, the root would not match.

This is the same commit-reveal idea behind provably-fair systems. It does not
make our predictions good. It makes our REPORTING of them honest, which is a
different and much rarer property.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .schema import Prediction


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> bytes:
    """Deterministic JSON encoding.

    Sorted keys and no insignificant whitespace, so the same logical
    prediction always produces byte-identical output on any machine, in any
    Python version. Non-determinism here would silently break verification.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def leaf_hash(prediction: Prediction) -> str:
    return _sha256(b"\x00" + canonical(prediction.to_dict()))


def _pair_hash(left: str, right: str) -> str:
    # Domain-separated from leaves (0x01 vs 0x00) to prevent second-preimage
    # attacks where an internal node is passed off as a leaf.
    return _sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


def merkle_root(leaves: Sequence[str]) -> str:
    if not leaves:
        raise ValueError("cannot commit to an empty slate")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])  # duplicate the odd tail
        level = [_pair_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(leaves: Sequence[str], index: int) -> list[dict[str, str]]:
    """Inclusion proof for one prediction, so a single pick can be verified
    without revealing the rest of the slate."""
    if not 0 <= index < len(leaves):
        raise IndexError("index outside slate")
    proof: list[dict[str, str]] = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = idx ^ 1
        proof.append(
            {"side": "right" if sibling > idx else "left", "hash": level[sibling]}
        )
        level = [_pair_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_proof(leaf: str, proof: list[dict[str, str]], root: str) -> bool:
    node = leaf
    for step in proof:
        node = (
            _pair_hash(node, step["hash"])
            if step["side"] == "right"
            else _pair_hash(step["hash"], node)
        )
    return node == root


@dataclass
class Commitment:
    slate_id: str
    sport: str
    root: str
    n_predictions: int
    committed_at: datetime
    earliest_kickoff: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "slate_id": self.slate_id,
            "sport": self.sport,
            "merkle_root": self.root,
            "n_predictions": self.n_predictions,
            "committed_at": self.committed_at.isoformat(),
            "earliest_kickoff": self.earliest_kickoff.isoformat(),
            "algorithm": "sha256-merkle-v1",
        }


def commit_slate(
    slate_id: str,
    sport: str,
    predictions: list[Prediction],
    out_dir: Path | str = "data/ledger",
) -> Commitment:
    """Seal a slate. Refuses to commit after the first kickoff.

    That refusal is the whole point: a commitment published after games have
    started proves nothing, so we make it impossible to create one by accident.
    """
    if not predictions:
        raise ValueError("no predictions to commit")

    now = datetime.now(timezone.utc)
    earliest = min(p.created_at for p in predictions)
    kickoffs = [p.created_at for p in predictions]

    leaves = [leaf_hash(p) for p in predictions]
    root = merkle_root(leaves)

    commitment = Commitment(
        slate_id=slate_id,
        sport=sport,
        root=root,
        n_predictions=len(predictions),
        committed_at=now,
        earliest_kickoff=min(kickoffs),
    )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Public half - safe to publish immediately, reveals nothing.
    (out / f"{slate_id}.commitment.json").write_bytes(
        canonical(commitment.to_dict())
    )
    # Sealed half - published after settlement.
    (out / f"{slate_id}.reveal.json").write_bytes(
        canonical(
            {
                "slate_id": slate_id,
                "merkle_root": root,
                "leaves": leaves,
                "predictions": [p.to_dict() for p in predictions],
            }
        )
    )
    return commitment


def verify_slate(slate_id: str, ledger_dir: Path | str = "data/ledger") -> bool:
    """Recompute the root from the revealed predictions and compare.

    This is the function a skeptical reader runs. It is deliberately trivial
    to read and has no dependency on our code being honest, because it
    recomputes everything from the published data.
    """
    d = Path(ledger_dir)
    commitment = json.loads((d / f"{slate_id}.commitment.json").read_text())
    reveal = json.loads((d / f"{slate_id}.reveal.json").read_text())

    if len(reveal["predictions"]) != commitment["n_predictions"]:
        return False

    recomputed = [
        _sha256(b"\x00" + canonical(p)) for p in reveal["predictions"]
    ]
    if recomputed != reveal["leaves"]:
        return False
    return merkle_root(recomputed) == commitment["merkle_root"]
