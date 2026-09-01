"""Tests for the parts where a silent bug becomes a false public claim.

These are not chosen for coverage. Each one targets a failure mode that either
bit us or would have, and every one of those was a check reporting something
false rather than code crashing:

  - a leaked post-game column makes a backtest look excellent and lose live
  - a broken de-vig flatters us against the market
  - odds conversion errors corrupt every CLV number silently
  - a Merkle proof that accepts a tampered slate destroys the whole product
  - a closing-window filter that lets in the wrong game invents closing lines
  - an ID-space mismatch reports CLV as "unavailable" forever, which looks
    exactly like a genuine data gap
  - a commitment that overwrites its predecessor is indistinguishable from
    tampering

Run: pytest -q
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engine.adapters.nfl import BANNED_FEATURES, NFLAdapter
from engine.backfill import WINDOW, _rows_from_snapshot
from engine.commit import (Commitment, commit_slate, commitment_history,
                           leaf_hash, merkle_proof, merkle_root, verify_proof,
                           verify_slate)
from engine.grade import CLV_PROVENANCE, _resolve_game_id
from engine.schema import (Market, Prediction, Sport, american_to_prob, devig,
                           prob_to_american)

UTC = timezone.utc


# --------------------------------------------------------------------------
# odds maths
# --------------------------------------------------------------------------

@pytest.mark.parametrize("price", [-1000, -300, -198, -110, 100, 164, 450, 2000])
def test_american_prob_round_trip(price):
    """Converting to probability and back must return the same price.

    CLV is a difference of two implied probabilities. A rounding error here
    does not crash anything - it quietly shifts every CLV number we publish.
    """
    assert prob_to_american(american_to_prob(price)) == price


def test_american_to_prob_sign_convention():
    assert american_to_prob(-200) == pytest.approx(2 / 3)
    assert american_to_prob(+100) == pytest.approx(0.5)
    assert american_to_prob(+300) == pytest.approx(0.25)


def test_prob_to_american_rejects_impossible():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            prob_to_american(bad)


def test_devig_sums_to_one_and_preserves_order():
    """The vigged pair sums to >1; de-vigged must sum to exactly 1.

    We compare ourselves against the DE-VIGGED market because beating a vigged
    line is trivial and meaningless. If this silently failed we would look
    better than we are.
    """
    a, b = american_to_prob(-110), american_to_prob(-110)
    assert a + b > 1.0
    da, db = devig(a, b)
    assert da + db == pytest.approx(1.0)
    assert da == pytest.approx(0.5)

    fav, dog = devig(american_to_prob(-300), american_to_prob(+250))
    assert fav + dog == pytest.approx(1.0)
    assert fav > dog  # de-vigging must not reorder the favourite


def test_devig_rejects_degenerate():
    with pytest.raises(ValueError):
        devig(0.0, 0.0)


# --------------------------------------------------------------------------
# leakage guard
# --------------------------------------------------------------------------

def test_banned_features_cover_the_known_offenders():
    """nflverse temp/wind are POST-GAME readings, not forecasts.

    Training on them produces a beautiful backtest and a losing live model.
    This is how most 'AI picks' models are accidentally built.
    """
    for col in ("temp", "wind", "home_score", "away_score", "result"):
        assert col in BANNED_FEATURES


def test_feature_frame_rejects_leaked_column(monkeypatch):
    """The guard must fail loudly, not warn."""
    adapter = NFLAdapter.__new__(NFLAdapter)
    real = NFLAdapter.feature_frame

    def leaky(self, events, asof):
        df = real(self, events, asof)
        df["temp"] = 72.0  # a post-game reading sneaking in
        leaked = BANNED_FEATURES & set(df.columns)
        if leaked:
            raise AssertionError(f"leaked post-game columns: {leaked}")
        return df

    with pytest.raises(AssertionError, match="leaked"):
        leaky(adapter, [], datetime.now(UTC))


# --------------------------------------------------------------------------
# merkle commitments
# --------------------------------------------------------------------------

def _preds(n: int, prob_base: float = 0.5) -> list[Prediction]:
    return [Prediction(
        event_id=f"G{i}", sport=Sport.NFL, market=Market.MONEYLINE,
        selection="side_a", line=None, probability=round(prob_base + i / 200, 4),
        model_version="test-v1",
        created_at=datetime(2026, 9, 9, 17, 0, tzinfo=UTC),
        reference_price=-150) for i in range(n)]


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 16, 17])
def test_merkle_proof_verifies_every_leaf(n):
    """Odd counts duplicate the tail; an off-by-one there breaks proofs."""
    leaves = [leaf_hash(p) for p in _preds(n)]
    root = merkle_root(leaves)
    for i in range(n):
        assert verify_proof(leaves[i], merkle_proof(leaves, i), root)


def test_merkle_proof_rejects_foreign_leaf():
    leaves = [leaf_hash(p) for p in _preds(8)]
    root = merkle_root(leaves)
    other = leaf_hash(_preds(1, prob_base=0.99)[0])
    assert not verify_proof(other, merkle_proof(leaves, 3), root)


def test_merkle_root_rejects_empty_slate():
    with pytest.raises(ValueError):
        merkle_root([])


def test_tampering_with_one_prediction_breaks_verification(tmp_path):
    """The single most important test in the repo.

    If this ever passes while a prediction has been altered, the product is a
    lie.
    """
    commit_slate("T-1", "nfl", _preds(12), out_dir=tmp_path)
    assert verify_slate("T-1", tmp_path) is True

    reveal = tmp_path / "T-1.reveal.v1.json"
    data = json.loads(reveal.read_text())
    data["predictions"][4]["probability"] = 0.99
    reveal.write_bytes(json.dumps(data, sort_keys=True,
                                  separators=(",", ":")).encode())
    assert verify_slate("T-1", tmp_path) is False


def test_removing_a_prediction_breaks_verification(tmp_path):
    """Deleting a loss must be as detectable as editing one."""
    commit_slate("T-2", "nfl", _preds(10), out_dir=tmp_path)
    reveal = tmp_path / "T-2.reveal.v1.json"
    data = json.loads(reveal.read_text())
    data["predictions"].pop(0)
    data["leaves"].pop(0)
    reveal.write_bytes(json.dumps(data, sort_keys=True,
                                  separators=(",", ":")).encode())
    assert verify_slate("T-2", tmp_path) is False


# --------------------------------------------------------------------------
# commitment versioning
# --------------------------------------------------------------------------

def test_recommitting_changed_predictions_versions_rather_than_overwrites(tmp_path):
    """A root that vanishes is indistinguishable from tampering."""
    c1 = commit_slate("T-3", "nfl", _preds(6), out_dir=tmp_path)
    c2 = commit_slate("T-3", "nfl", _preds(6, prob_base=0.6), out_dir=tmp_path)

    assert c1.version == 1 and c2.version == 2
    assert c2.supersedes == c1.root
    assert c1.root != c2.root

    hist = commitment_history("T-3", tmp_path)
    assert [h["version"] for h in hist] == [1, 2]

    # both remain independently verifiable
    assert verify_slate("T-3", tmp_path, version=1) is True
    assert verify_slate("T-3", tmp_path, version=2) is True
    assert verify_slate("T-3", tmp_path) is True  # defaults to latest


def test_recommitting_identical_predictions_does_not_mint_a_version(tmp_path):
    preds = _preds(6)
    commit_slate("T-4", "nfl", preds, out_dir=tmp_path)
    commit_slate("T-4", "nfl", preds, out_dir=tmp_path)
    assert len(commitment_history("T-4", tmp_path)) == 1


# --------------------------------------------------------------------------
# closing-window filter
# --------------------------------------------------------------------------

def _snapshot(commence_iso: str) -> dict:
    return {"data": [{
        "id": "abc", "home_team": "Kansas City Chiefs",
        "away_team": "Detroit Lions", "commence_time": commence_iso,
        "bookmakers": [{"key": "fanduel", "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Kansas City Chiefs", "price": -150},
                {"name": "Detroit Lions", "price": 130}]}]}]}]}


def test_closing_window_accepts_game_inside_window():
    snap = datetime(2024, 9, 8, 16, 55, tzinfo=UTC)
    rows = _rows_from_snapshot(
        _snapshot((snap + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")),
        snap, 2024, 1)
    assert rows and all(r.provenance == "oddsapi_historical_close" for r in rows)


def test_closing_window_rejects_a_later_slate():
    """A snapshot at 17:00 says nothing about a game kicking off at 01:00.

    Without this the backfill would invent closing lines for every game in the
    response, which is the difference between a record and a fabrication.
    """
    snap = datetime(2024, 9, 8, 16, 55, tzinfo=UTC)
    late = snap + WINDOW + timedelta(minutes=1)
    rows = _rows_from_snapshot(
        _snapshot(late.isoformat().replace("+00:00", "Z")), snap, 2024, 1)
    assert rows == []


def test_closing_window_rejects_game_already_started():
    snap = datetime(2024, 9, 8, 16, 55, tzinfo=UTC)
    rows = _rows_from_snapshot(
        _snapshot((snap - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")),
        snap, 2024, 1)
    assert rows == []


# --------------------------------------------------------------------------
# id-space resolution (the bug that would have disabled CLV forever)
# --------------------------------------------------------------------------

def test_resolve_game_id_maps_full_names_to_nflverse_id():
    index = {(2024, "KC", "DET"): "2024_01_DET_KC"}
    row = {"season": 2024, "home": "Kansas City Chiefs",
           "away": "Detroit Lions"}
    assert _resolve_game_id(row, index) == "2024_01_DET_KC"


def test_resolve_game_id_accepts_already_abbreviated():
    index = {(2024, "KC", "DET"): "2024_01_DET_KC"}
    assert _resolve_game_id({"season": 2024, "home": "KC", "away": "DET"},
                            index) == "2024_01_DET_KC"


def test_resolve_game_id_returns_none_when_unmatched():
    assert _resolve_game_id({"season": 2024, "home": "Nowhere United",
                             "away": "Elsewhere FC"}, {}) is None


def test_clv_provenance_is_restricted():
    """Only prices we captured or paid for may produce a published CLV."""
    assert CLV_PROVENANCE == {"own_capture", "oddsapi_historical_close"}
    for untrusted in ("espn_open", "espn_close", "nflverse_consensus"):
        assert untrusted not in CLV_PROVENANCE


def test_kickoff_converts_eastern_gametime_to_utc():
    """nflverse gametime is the Eastern league clock, not UTC.

    Stamping it as UTC shipped every NFL kickoff four hours early in summer
    (2026 W1 TB-CIN read 8 AM Central on /picks against noon on /market) and
    would have been five hours early in January. Both halves are asserted so a
    hardcoded -4 offset fails here too.
    """
    summer = {"gameday": pd.Timestamp("2026-09-13"), "gametime": "13:00"}
    winter = {"gameday": pd.Timestamp("2027-01-03"), "gametime": "13:00"}

    assert NFLAdapter._kickoff(summer) == datetime(
        2026, 9, 13, 17, 0, tzinfo=timezone.utc)      # EDT, UTC-4
    assert NFLAdapter._kickoff(winter) == datetime(
        2027, 1, 3, 18, 0, tzinfo=timezone.utc)       # EST, UTC-5

    # A late kickoff crosses midnight into the next UTC day.
    night = {"gameday": pd.Timestamp("2026-09-09"), "gametime": "20:20"}
    assert NFLAdapter._kickoff(night) == datetime(
        2026, 9, 10, 0, 20, tzinfo=timezone.utc)

    # Missing gametime still lands on the right Eastern date.
    dateonly = {"gameday": pd.Timestamp("2026-09-13"), "gametime": None}
    assert NFLAdapter._kickoff(dateonly) == datetime(
        2026, 9, 13, 4, 0, tzinfo=timezone.utc)
