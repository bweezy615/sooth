"""Each sport's capture gate reads its OWN calendar.

`--within-minutes` exists so a capture can fire near a kickoff instead of
around the clock. It used to refuse every sport but the NFL, and that refusal
was right: the lookup could only read the nflverse schedule, so letting college
football through would have gated Saturday's capture on when the NFL happened
to play.

It is now dispatched per sport, which matters because
docs/plans/2026-09-09-cfb-closing-line-evidence.md measured only 27% of played
college games having a price inside thirty minutes of kickoff and named a
kickoff-triggered capture as the cheapest fix. That fix was impossible while
this function could not see a college calendar.

The refusal is kept for sports with no schedule wired up. Falling back to the
NFL's kickoffs would be the original bug with a friendlier face.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import engine.capture as capture

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)

COLUMNS = ("game_id,season,week,season_type,start_date,completed,neutral_site,"
           "conference_game,attendance,venue,home_id,home_team,home_division,"
           "home_conference,home_points,home_post_win_prob,home_pregame_elo,"
           "home_postgame_elo,away_id,away_team,away_division,away_conference,"
           "away_points,away_pregame_elo,excitement_index")


def row(gid, start, done, home, away, hdiv="fbs", adiv="fbs", pts=""):
    return (f"{gid},2026,3,regular,{start},{done},False,True,50000,Field,1,"
            f"{home},{hdiv},ACC,{pts},0.7,1600,1610,2,{away},{adiv},SEC,{pts},"
            f"1500,5.5")


@pytest.fixture
def cfb(tmp_path, monkeypatch):
    """A played game, an FBS-vs-FCS opener soon, and a later FBS game."""
    soon = NOW + timedelta(minutes=25)
    later = NOW + timedelta(hours=8)
    past = NOW - timedelta(days=2)
    csv = "\n".join([
        COLUMNS,
        row(1, past.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "True", "UCF",
            "Bethune-Cookman", adiv="fcs", pts=42),
        row(2, soon.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "False", "Rutgers",
            "Merrimack", adiv="fcs"),
        row(3, later.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "False",
            "Georgia Tech", "Clemson"),
    ]) + "\n"
    (tmp_path / "ncaaf_schedule_2026.csv").write_text(csv, encoding="utf-8")

    # Point the adapter at the fixture instead of data/raw. The real code runs
    # untouched; only where it reads its cache from changes, so no network.
    import engine.adapters.ncaaf as mod

    class Cached(mod.NCAAFAdapter):
        def __init__(self, cache_dir=None):
            super().__init__(cache_dir=tmp_path)

    monkeypatch.setattr(mod, "NCAAFAdapter", Cached)
    return tmp_path


def test_college_football_is_gated_on_its_own_next_kickoff(cfb):
    mins = capture.minutes_to_next_kickoff(2026, NOW, sport="ncaaf")
    assert mins == pytest.approx(25.0, abs=0.5)


def test_an_fcs_visitor_still_opens_the_gate(cfb):
    """engine.capture reads ESPN group 80, which carries an FBS host's game
    whoever visits, and those openers cluster on exactly the weekends this
    gate would be used. A kickoff we skip cannot be bought back later."""
    assert capture.minutes_to_next_kickoff(2026, NOW, sport="ncaaf") is not None


def test_a_game_already_played_does_not_open_the_gate(cfb):
    """Late enough that only the finished game is behind us and nothing is
    ahead: the answer must be None, not a negative number."""
    late = NOW + timedelta(days=30)
    assert capture.minutes_to_next_kickoff(2026, late, sport="ncaaf") is None


def test_a_sport_with_no_schedule_is_refused_not_guessed():
    """Falling back to the NFL calendar is the original bug with a nicer face."""
    with pytest.raises(ValueError, match="no kickoff schedule"):
        capture.minutes_to_next_kickoff(2026, NOW, sport="mlb")


def test_the_default_sport_does_not_touch_the_college_branch(monkeypatch):
    """The NFL is the path in production use and must be reached by default.

    Asserted by making the college branch fail loudly if it is consulted: a
    test that patched the function under test and then called it would only
    have checked the mock.
    """
    def must_not_run(season, now):
        raise AssertionError("the NFL default reached the college branch")

    monkeypatch.setattr(capture, "_minutes_to_next_ncaaf_kickoff", must_not_run)
    monkeypatch.setattr(capture, "NFLAdapter", _StubNFL)
    assert capture.minutes_to_next_kickoff(2026, NOW) == pytest.approx(120.0)


class _StubNFL:
    """One unplayed NFL game two hours out, in the nflverse shape."""

    def __init__(self, *a, **k):
        pass

    @property
    def games(self):
        import pandas as pd
        ko = (NOW + timedelta(hours=2)).astimezone(ZoneInfo("America/New_York"))
        return pd.DataFrame([{
            "season": 2026, "home_score": None,
            "gameday": ko.strftime("%Y-%m-%d"),
            "gametime": ko.strftime("%H:%M"),
        }])


def test_an_unreadable_schedule_yields_no_opinion(monkeypatch):
    """A schedule we cannot fetch must not take the capture down. None means
    'no opinion', and the caller then skips rather than crashing."""
    import engine.adapters.ncaaf as mod

    class Broken(mod.NCAAFAdapter):
        def seasons(self, *a, **k):
            raise OSError("no network")

    monkeypatch.setattr(mod, "NCAAFAdapter", Broken)
    assert capture._minutes_to_next_ncaaf_kickoff(2026, NOW) is None
