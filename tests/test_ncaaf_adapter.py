"""The college football adapter.

Adding a sport is supposed to mean implementing engine/adapters/base.py and
nothing else. This checks the contract holds for college football, and pins
the three things about the source that are easy to get quietly wrong:

  * kickoffs are already UTC and must not be re-zoned (PLAN.md documents the
    NFL adapter doing exactly that and publishing every kickoff four hours
    early);
  * a schedule feed carries no odds, so it must not manufacture a closing
    line, which base.py says silently corrupts every CLV number downstream;
  * FBS-vs-FCS games are not predicted, because a rating for a team with one
    game against the division is an estimate of nothing.

No network: every test runs against a fixture written to a temp cache, which
is also the only way the assertions can pin exact values.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from engine.adapters.ncaaf import NCAAFAdapter
from engine.schema import Sport, Status

COLUMNS = ("game_id,season,week,season_type,start_date,completed,neutral_site,"
           "conference_game,attendance,venue,home_id,home_team,home_division,"
           "home_conference,home_points,home_post_win_prob,home_pregame_elo,"
           "home_postgame_elo,away_id,away_team,away_division,away_conference,"
           "away_points,away_pregame_elo,excitement_index")


def row(gid, week, start, done, home, away, hp, ap, *,
        hdiv="fbs", adiv="fbs", neutral="False", conf="True",
        helo=1600, aelo=1500, stype="regular"):
    hp = "" if hp is None else hp
    ap = "" if ap is None else ap
    return (f"{gid},2025,{week},{stype},{start},{done},{neutral},{conf},50000,"
            f"Field,1,{home},{hdiv},ACC,{hp},0.7,{helo},1610,2,{away},{adiv},"
            f"SEC,{ap},{aelo},5.5")


@pytest.fixture
def adapter(tmp_path):
    """One season: three finished FBS games, an FCS visitor, a future game."""
    csv = "\n".join([
        COLUMNS,
        # Sat 2025-08-30, both FBS, finished
        row(1, 1, "2025-08-30T16:00:00.000Z", "True", "Georgia Tech",
            "Florida State", 24, 21, neutral="True"),
        # an FBS host against an FCS visitor — must never be modelled
        row(2, 1, "2025-08-30T23:00:00.000Z", "True", "UCF",
            "Bethune-Cookman", 56, 3, adiv="fcs"),
        # same two FBS teams a week later, for the rest-days calculation
        row(3, 2, "2025-09-06T16:00:00.000Z", "True", "Florida State",
            "Georgia Tech", 17, 30),
        # not yet played
        row(4, 3, "2025-09-13T16:00:00.000Z", "False", "Georgia Tech",
            "Clemson", None, None),
    ]) + "\n"
    (tmp_path / "ncaaf_schedule_2025.csv").write_text(csv, encoding="utf-8")
    return NCAAFAdapter(cache_dir=tmp_path)


# ------------------------------------------------------------------ history

def test_history_is_fbs_versus_fbs_and_finished_only(adapter):
    hist = adapter.load_history(2025, 2025)
    assert [e.event_id for e in hist] == ["1", "3"], (
        "the FCS visitor and the unplayed game must both be out")
    assert all(e.sport is Sport.NCAAF for e in hist)
    assert all(e.status is Status.FINAL for e in hist)


def test_kickoffs_stay_on_the_utc_instant_the_source_states(adapter):
    """The NFL adapter re-zoned a local clock and shipped every kickoff four
    hours early. This source is already UTC; re-zoning it would be the same
    bug wearing a different hat."""
    e = adapter.load_history(2025, 2025)[0]
    assert e.start_time == datetime(2025, 8, 30, 16, 0, tzinfo=timezone.utc)
    assert e.start_time.tzinfo is not None


def test_home_is_side_a_and_neutral_sites_are_carried(adapter):
    e = adapter.load_history(2025, 2025)[0]
    assert (e.side_a, e.side_b) == ("Georgia Tech", "Florida State")
    assert e.neutral_site is True


def test_results_key_by_event_id_with_home_first(adapter):
    hist = adapter.load_history(2025, 2025)
    res = adapter.load_results(hist)
    assert set(res) == {"1", "3"}
    assert (res["1"].score_a, res["1"].score_b) == (24.0, 21.0)


def test_an_unplayed_game_has_no_result(adapter):
    """load_results is keyed by what settled, not by what was asked for."""
    up = adapter.upcoming(datetime(2025, 9, 1, tzinfo=timezone.utc))
    assert adapter.load_results(up) == {}


# -------------------------------------------------------------------- lines

def test_a_schedule_feed_reports_no_lines_rather_than_inventing_one(adapter):
    """base.py: guessing is_closing silently corrupts every CLV number. The
    source carries no odds at all, so the honest answer is nothing — and it is
    why college football stays In calibration under HANDOFF §9."""
    hist = adapter.load_history(2025, 2025)
    assert adapter.load_historical_lines(hist) == []
    assert adapter.current_lines(hist) == []


# ----------------------------------------------------------------- upcoming

def test_upcoming_is_future_unplayed_fbs_in_kickoff_order(adapter):
    up = adapter.upcoming(datetime(2025, 9, 1, tzinfo=timezone.utc))
    assert [e.event_id for e in up] == ["4"]
    assert up[0].status is Status.SCHEDULED


def test_upcoming_excludes_games_already_kicked_off(adapter):
    assert adapter.upcoming(datetime(2025, 12, 1, tzinfo=timezone.utc)) == []


# ----------------------------------------------------------------- features

def test_features_carry_no_banned_post_game_column(adapter):
    hist = adapter.load_history(2025, 2025)
    f = adapter.feature_frame(hist, asof=datetime(2025, 12, 1, tzinfo=timezone.utc))
    from engine.adapters.ncaaf import BANNED_FEATURES
    assert not (BANNED_FEATURES & set(f.columns))
    assert {"home_pregame_elo", "away_pregame_elo", "neutral_site",
            "conference_game", "rest_diff"} <= set(f.columns)


def test_rest_days_come_from_the_previous_game(adapter):
    hist = adapter.load_history(2025, 2025)
    f = adapter.feature_frame(hist, asof=datetime(2025, 12, 1, tzinfo=timezone.utc))
    wk2 = f[f["event_id"] == "3"].iloc[0]
    assert wk2["home_rest"] == pytest.approx(7.0), (
        "Florida State played 7 days earlier")
    assert wk2["away_rest"] == pytest.approx(7.0)
    assert pd.isna(f[f["event_id"] == "1"].iloc[0]["home_rest"]), (
        "the season opener has no previous game")


def test_asof_bounds_the_rest_calculation(adapter):
    """A game that has not happened at asof must not inform the features.

    Rest days are the one column here derived from other rows, so they are the
    one column that can quietly reach forward in time.
    """
    hist = adapter.load_history(2025, 2025)
    f = adapter.feature_frame(hist, asof=datetime(2025, 8, 31, tzinfo=timezone.utc))
    wk2 = f[f["event_id"] == "3"].iloc[0]
    assert wk2["home_rest"] == pytest.approx(7.0), (
        "week 1 was before asof and is legitimately visible")

    f0 = adapter.feature_frame(hist, asof=datetime(2025, 8, 1, tzinfo=timezone.utc))
    assert pd.isna(f0[f0["event_id"] == "3"].iloc[0]["home_rest"]), (
        "nothing had been played at asof, so no rest is knowable")
