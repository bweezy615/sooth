"""The spread play is inside the Merkle commitment.

Until 2026-09-04 the SPREAD PLAY on /picks lived only in the display payload
and the encrypted pro blob. The sealed leaves were moneyline predictions, so
the one claim that reads most like a pick was the one claim we could have
edited after kickoff without breaking the published root.

These tests hold the two halves of the fix together: that such a leaf seals
and verifies at all, and that it grades under the same sign convention as the
code the published ATS figures come from. An inverted sign here would not be a
display bug, it would be a false public record.
"""
from datetime import datetime, timezone

import pandas as pd
import pytest

from engine.commit import commit_slate, leaf_hash, verify_slate
from engine.grade import settle
from engine.models.ensemble import EDGE_THRESHOLD, ats_frame
from engine.schema import Market, Prediction, Sport

KICK = datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)


def _spread(sel, line, margin=None, pm=0.0):
    return Prediction(
        event_id="2026_01_HOU_LAC", sport=Sport.NFL, market=Market.SPREAD,
        selection=sel, line=line, probability=None,
        model_version="ridge-margin-v1", created_at=KICK,
        reference_line=line, predicted_margin=pm)


def test_a_spread_play_seals_and_verifies_without_a_probability(tmp_path):
    ml = Prediction(
        event_id="2026_01_HOU_LAC", sport=Sport.NFL, market=Market.MONEYLINE,
        selection="side_a", line=None, probability=0.61,
        model_version="elo+epa-v1+iso", created_at=KICK)
    c = commit_slate("2026-W01-nfl", "nfl", [ml, _spread("side_b", -4.3, pm=-8.9)],
                     out_dir=tmp_path)
    assert c.n_predictions == 2
    assert verify_slate("2026-W01-nfl", tmp_path) is True


def test_the_sealed_leaf_pins_the_number_the_play_was_made_against():
    # Two plays identical except for the posted line must not share a leaf:
    # otherwise the number we took could be restated after the fact.
    assert leaf_hash(_spread("side_b", -4.3)) != leaf_hash(_spread("side_b", -3.5))
    # ...and the predicted margin is in there too, which is what lets a reader
    # recompute the edge and check that a "qualified" play really qualified.
    assert leaf_hash(_spread("side_b", -4.3, pm=-8.9)) != leaf_hash(
        _spread("side_b", -4.3, pm=-5.0))


@pytest.mark.parametrize("pred_margin,line,actual_margin", [
    (10.0, 3.0, 7.0), (10.0, 3.0, -7.0), (3.0, 10.0, 20.0), (3.0, 10.0, 0.0),
    (0.0, -7.0, -3.0), (-8.9, -4.3, -1.0), (-8.9, -4.3, -9.0), (6.0, 0.0, 4.0),
])
def test_grading_agrees_with_the_rule_the_published_ats_figures_use(
        pred_margin, line, actual_margin):
    d = ats_frame(pd.DataFrame([{"m": pred_margin, "spread_line": line,
                                 "margin": actual_margin, "season": 2026}]), "m")
    selection = "side_a" if bool(d["pick_home"].iloc[0]) else "side_b"
    expected = None if bool(d["push"].iloc[0]) else bool(d["win"].iloc[0])
    assert settle("spread", selection, line, actual_margin) is expected


def test_a_push_is_excluded_rather_than_scored_as_a_loss():
    assert settle("spread", "side_a", -4.3, -4.3) is None
    assert settle("spread", "side_b", -4.3, -4.3) is None


def test_a_spread_row_is_not_graded_by_the_moneyline_rule():
    # HOU at home getting 4.3 is spread_line -4.3 on the home basis. Take them
    # and they lose the game by 1: the moneyline loses, the cover wins. Grade
    # this row with the moneyline rule and a winning play is published as a
    # loss.
    assert settle("spread", "side_a", -4.3, -1.0) is True
    assert settle("moneyline", "side_a", None, -1.0) is False
    # Losing by 9 loses both, so the two rules agree here - they agree by
    # coincidence, never by construction, which is why the market has to be
    # read rather than assumed.
    assert settle("spread", "side_a", -4.3, -9.0) is False
    assert settle("moneyline", "side_a", None, -9.0) is False


def test_the_selectivity_threshold_is_recomputable_from_the_sealed_leaf():
    p = _spread("side_b", -4.3, pm=-8.9)
    edge = p.predicted_margin - p.line
    assert abs(edge) >= EDGE_THRESHOLD          # this one is a qualified play
    assert (p.selection == "side_b") is (edge < 0)
