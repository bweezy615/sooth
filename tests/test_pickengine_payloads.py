"""The payload split is the paywall's foundation: the public file must never
contain a pick before first kickoff, and the pro file must always be complete."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.pipeline.weekly import _pickengine_payloads


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


def test_redacts_before_kickoff(tmp_path):
    kick = datetime.now(timezone.utc) + timedelta(days=2)
    pub = _pickengine_payloads(tmp_path, _payload(kick))
    assert pub["locked"] is True
    for g in pub["games"]:
        assert g["independent"] is None and g["consensus"] is None
        assert g["divergence"] is None
        assert g["divergence_rank"] in (1, 2)
    # g2 diverges more (|0.45-0.66| = .21 vs |0.64-0.62| = .02) -> rank 1
    by_id = {g["game_id"]: g for g in pub["games"]}
    assert by_id["g2"]["divergence_rank"] == 1

    pro = json.loads((tmp_path / "data/pro/2099-W01-nfl.pro.json").read_text())
    assert pro["games"][0]["game_id"] == "g2"          # sorted by divergence
    assert pro["games"][0]["divergence"] == 0.21
    assert pro["games"][0]["independent"]["pick"] == "NO"
    latest = json.loads((tmp_path / "data/pro/latest.pro.json").read_text())
    assert latest["slate_id"] == "2099-W01-nfl"


def test_open_after_kickoff(tmp_path):
    kick = datetime.now(timezone.utc) - timedelta(hours=1)
    pub = _pickengine_payloads(tmp_path, _payload(kick))
    assert pub["locked"] is False
    assert pub["games"][0]["independent"] is not None


def test_no_best_lines_is_honest_nulls(tmp_path):
    kick = datetime.now(timezone.utc) + timedelta(days=2)
    _pickengine_payloads(tmp_path, _payload(kick))
    pro = json.loads((tmp_path / "data/pro/latest.pro.json").read_text())
    assert pro["games"][0]["best_price"] is None
    assert pro["games"][0]["best_book"] is None
