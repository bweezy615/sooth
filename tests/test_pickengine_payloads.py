"""The payload split is the paywall's foundation: the public file must never
contain a pick before first kickoff, and the pro file must always be complete."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.pipeline.weekly import _pickengine_payloads
from engine import prosec

# the pro payload ships encrypted; tests hold their own throwaway key
os.environ.setdefault("PRO_PAYLOAD_KEY", "11" * 32)


def _read_pro(tmp_path, name):
    return json.loads(prosec.decrypt(
        (tmp_path / "data/pro" / name).read_text()))


def _payload(kickoff):
    return {
        "slate_id": "2099-W01-nfl", "sport": "nfl", "season": 2099, "week": 1,
        "status": "committed", "models": {}, "confidence_cap": 0.85,
        "merkle_root": "ab" * 32, "committed_at": "2099-01-01T00:00:00+00:00",
        "earliest_kickoff": kickoff.isoformat(), "n_predictions": 4,
        "disclaimer": "test",
        "games": [
            {"game_id": "g1", "kickoff": kickoff.isoformat(),
             "home": "SEA", "away": "NE", "spread_line": 3.5,
             "independent": {"pick": "SEA", "prob": 0.64, "fair_odds": -178},
             "consensus": {"pick": "SEA", "prob": 0.70, "fair_odds": -233},
             "market_prob": 0.62, "models_disagree": False,
             "independent_vs_market": False},
            {"game_id": "g2", "kickoff": kickoff.isoformat(),
             "home": "DET", "away": "NO", "spread_line": -7.0,
             "independent": {"pick": "NO", "prob": 0.55, "fair_odds": -122},
             "consensus": {"pick": "DET", "prob": 0.61, "fair_odds": -156},
             "market_prob": 0.66, "models_disagree": True,
             "independent_vs_market": True},
        ],
    }


def test_publishes_the_full_slate_before_kickoff(tmp_path):
    """The slate is published as soon as it is sealed, not held until kickoff.

    This test asserted the opposite until 2026-08-22. The redaction it guarded
    existed to sell TIMING for the paid tier; with that tier deleted it was
    withholding for its own sake. It was never what made the commitment
    trustworthy: commit-reveal integrity rests on the hash being published and
    externally timestamped BEFORE the event, and the reveal time does not enter
    into it. The reveal file has carried every prediction in the clear the whole
    time regardless.
    """
    kick = datetime.now(timezone.utc) + timedelta(days=2)
    pub = _pickengine_payloads(tmp_path, _payload(kick))
    assert pub["locked"] is False
    for g in pub["games"]:
        assert g["independent"] is not None
        assert g["divergence"] is not None
        assert g["divergence_rank"] in (1, 2)
    # g2 diverges more (|0.45-0.66| = .21 vs |0.64-0.62| = .02) -> rank 1
    by_id = {g["game_id"]: g for g in pub["games"]}
    assert by_id["g2"]["divergence_rank"] == 1

    pro = _read_pro(tmp_path, "2099-W01-nfl.pro.enc")
    assert pro["games"][0]["game_id"] == "g2"          # sorted by divergence
    assert pro["games"][0]["divergence"] == 0.21
    assert pro["games"][0]["independent"]["pick"] == "NO"
    latest = _read_pro(tmp_path, "latest.pro.enc")
    assert latest["slate_id"] == "2099-W01-nfl"


def test_open_after_kickoff(tmp_path):
    kick = datetime.now(timezone.utc) - timedelta(hours=1)
    pub = _pickengine_payloads(tmp_path, _payload(kick))
    assert pub["locked"] is False
    assert pub["games"][0]["independent"] is not None


def test_no_best_lines_is_honest_nulls(tmp_path):
    kick = datetime.now(timezone.utc) + timedelta(days=2)
    _pickengine_payloads(tmp_path, _payload(kick))
    pro = _read_pro(tmp_path, "latest.pro.enc")
    assert pro["games"][0]["best_price"] is None
    assert pro["games"][0]["best_book"] is None


def test_ciphertext_never_leaks_a_pick(tmp_path):
    """The repo is public; the committed blob must be opaque."""
    kick = datetime.now(timezone.utc) + timedelta(days=2)
    _pickengine_payloads(tmp_path, _payload(kick))
    blob = (tmp_path / "data/pro/latest.pro.enc").read_text()
    assert "SEA" not in blob and "pick" not in blob
    meta = json.loads((tmp_path / "data/pro/latest.meta.json").read_text())
    assert meta["game_count"] == 2
    assert "prob" not in json.dumps(meta)
