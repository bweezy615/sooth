"""One consensus close per GAME, never per matchup.

`engine.closing.consensus` used to group the paid backfill on
`["season", "home_abbr", "away_abbr"]`. That is a matchup, not a game, so when
two teams met twice in a season the regular-season game and the playoff rematch
fell into one group and the function returned the median closing price across
both. 855 games came back as 841 rows.

It then reached the site twice, because both consumers merged on that same
non-unique key and fanned out - the /methodology line-provenance figure and
every ATS record in Evaluation B. Nothing looked wrong: `matched_games` stayed
at 855 the whole time, because the fan-out restores exactly the count the
blending removed. Only the values inside 28 rows were wrong.

See docs/plans/rematch-consensus-close.md.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.closing import GAME_KEY, compare_to_nflverse, consensus


def _quotes(event_id: str, season: int, week: int, home: str, away: str,
            ml_home: int, ml_away: int, spread: float,
            books: tuple[str, ...] = ("a", "b", "c")) -> list[dict]:
    rows = []
    for book in books:
        rows += [
            {"event_id": event_id, "season": season, "week": week,
             "home_abbr": home, "away_abbr": away, "book": book,
             "market": "moneyline", "selection": "side_a",
             "price": ml_home, "line": None},
            {"event_id": event_id, "season": season, "week": week,
             "home_abbr": home, "away_abbr": away, "book": book,
             "market": "moneyline", "selection": "side_b",
             "price": ml_away, "line": None},
            {"event_id": event_id, "season": season, "week": week,
             "home_abbr": home, "away_abbr": away, "book": book,
             "market": "spread", "selection": "side_a",
             "price": -110, "line": spread},
            {"event_id": event_id, "season": season, "week": week,
             "home_abbr": home, "away_abbr": away, "book": book,
             "market": "total", "selection": "over",
             "price": -110, "line": 44.5},
        ]
    return rows


# The real 2025 case: San Francisco at Seattle in week 1 and again in week 20,
# with a different favourite each time. Averaging these two closes produces a
# price that was never on any board.
REMATCH = pd.DataFrame(
    _quotes("g1", 2025, 1, "SEA", "SF", ml_home=112, ml_away=-132, spread=2.5)
    + _quotes("g2", 2025, 20, "SEA", "SF", ml_home=-300, ml_away=240, spread=-6.5)
)


def test_a_rematch_is_two_games_not_one():
    cons = consensus(REMATCH)
    assert len(cons) == 2, (
        "the regular-season game and the playoff rematch were merged into one "
        "consensus row; their closes have been averaged together")
    assert sorted(cons["week"]) == [1, 20]


def test_each_game_keeps_its_own_close():
    cons = consensus(REMATCH).set_index("week")
    # close_spread is stated from the home side with the sign flipped, so week
    # 1 (home handicap +2.5) is -2.5 and week 20 (home handicap -6.5) is +6.5.
    assert cons.loc[1, "close_spread"] == pytest.approx(-2.5)
    assert cons.loc[20, "close_spread"] == pytest.approx(6.5)
    # Seattle is the dog in week 1 and a heavy favourite in week 20. If these
    # two ever come back equal the games have been blended again.
    assert cons.loc[1, "close_p_home"] < 0.5 < cons.loc[20, "close_p_home"]


def test_the_game_key_is_unique_or_the_build_stops():
    """A merge that can fan out is the mechanism of this bug, not a detail of
    it. If two rows ever share GAME_KEY, fail here rather than in a figure."""
    cons = consensus(REMATCH)
    assert not cons.duplicated(GAME_KEY).any()

    collided = REMATCH.copy()
    collided.loc[collided["event_id"] == "g2", "week"] = 1   # two ids, one key
    with pytest.raises(RuntimeError, match="1:1"):
        consensus(collided)


def test_comparing_to_nflverse_does_not_double_count_a_rematch():
    games = pd.DataFrame([
        {"season": 2025, "week": 1, "home_team": "SEA", "away_team": "SF",
         "spread_line": -2.5, "total_line": 44.5, "home_moneyline": 112,
         "away_moneyline": -132, "home_score": 20, "away_score": 17},
        {"season": 2025, "week": 20, "home_team": "SEA", "away_team": "SF",
         "spread_line": 6.5, "total_line": 44.5, "home_moneyline": -300,
         "away_moneyline": 240, "home_score": 31, "away_score": 13},
    ])
    prov = compare_to_nflverse(consensus(REMATCH), games)
    assert prov["matched_games"] == 2, (
        "the merge fanned out: each consensus row matched both nflverse rows "
        "for the same matchup")
    # Both closes were built to agree with nflverse exactly, so any disagreement
    # here is the merge pairing the wrong game with the wrong line.
    assert prov["pct_spread_differs"] == 0.0
