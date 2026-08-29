"""The college football adapter's silent failure modes.

Every check here is something that produces a plausible-looking frame rather
than an error, which is the only kind of defect worth a test in a backtest
path. Nothing here touches the network: the fixtures are small frames in the
cfbfastR-data column shape, verified against the real 2024 file on 2026-08-29.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from engine.adapters.ncaaf import (BANNED_FEATURES, UNVERIFIABLE_PREGAME,
                                   NCAAFAdapter, pooled_name)
from engine.models.elo import NCAAF_ELO, EloConfig
from engine.schema import Sport, Status

COLUMNS = [
    "game_id", "season", "week", "season_type", "start_date", "completed",
    "neutral_site", "conference_game", "attendance", "venue", "home_team",
    "home_division", "home_conference", "home_points", "home_post_win_prob",
    "home_pregame_elo", "home_postgame_elo", "away_team", "away_division",
    "away_conference", "away_points", "away_post_win_prob", "away_pregame_elo",
    "away_postgame_elo", "excitement_index", "highlights",
]


def game(gid, season, week, date, home, away, hp=None, ap=None,
         home_div="fbs", away_div="fbs", neutral="FALSE", conf="TRUE"):
    return {
        "game_id": gid, "season": season, "week": week,
        "season_type": "regular", "start_date": date, "completed": "TRUE",
        "neutral_site": neutral, "conference_game": conf, "attendance": 80000,
        "venue": "Somewhere", "home_team": home, "home_division": home_div,
        "home_conference": "SEC", "home_points": hp, "home_post_win_prob": 0.9,
        "home_pregame_elo": 1600, "home_postgame_elo": 1650,
        "away_team": away, "away_division": away_div, "away_conference": "SEC",
        "away_points": ap, "away_post_win_prob": 0.1, "away_pregame_elo": 1500,
        "away_postgame_elo": 1450, "excitement_index": 5.5, "highlights": "x",
    }


def frame(rows):
    return NCAAFAdapter._prepare(pd.DataFrame(rows, columns=COLUMNS))


def adapter_over(rows, **kw):
    a = NCAAFAdapter(**kw)
    a._games = frame(rows)
    return a


# -- scope -----------------------------------------------------------------

def test_lower_division_fixtures_are_dropped_but_fcs_games_are_kept():
    """A D-III fixture is not FBS football; an FBS-vs-FCS game is.

    Dropping the FCS games too would silently delete a chunk of most teams'
    Septembers, and every rating built on the remainder would be wrong in a
    way nothing reports.
    """
    df = frame([
        game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "W Carolina",
             38, 3, away_div="fcs"),
        game(2, 2024, 1, "2024-08-31T16:00:00.000Z", "Hillsdale", "Ferris St",
             10, 20, home_div="ii", away_div="ii"),
        game(3, 2024, 1, "2024-08-31T16:00:00.000Z", "Amherst", "Williams",
             7, 14, home_div="iii", away_div="iii"),
    ])
    assert set(df["game_id"]) == {1}


def test_non_fbs_opponents_pool_into_one_synthetic_rating_key():
    assert pooled_name("W Carolina", "fcs") == "__FCS__"
    assert pooled_name("Hillsdale", "ii") == "__DII__"
    assert pooled_name("Alabama", "fbs") == "Alabama"


# -- the rest pass ---------------------------------------------------------

def test_rest_days_never_go_negative_when_week_order_contradicts_dates():
    """The bug this test exists for shipped and was caught by assertion.

    College week numbers are not chronological: a game labelled week 2 can
    kick off before one labelled week 1. Walking the frame in (season, week)
    order therefore recorded a team's "previous" game as one not yet played,
    and produced 157 negative rest values across 2002-2025 — a plausible
    small number in a column nobody eyeballs.
    """
    df = frame([
        # week 2 in the file, but played FIRST
        game(1, 2024, 2, "2024-08-24T16:00:00.000Z", "Georgia Tech", "Florida St", 24, 21),
        game(2, 2024, 1, "2024-08-31T16:00:00.000Z", "Georgia Tech", "Georgia St", 35, 12),
    ])
    rest = pd.to_numeric(df["home_rest"], errors="coerce").dropna()
    assert not (rest < 0).any()
    late = df[df["game_id"] == 2].iloc[0]
    assert late["home_rest"] == pytest.approx(7.0)


def test_a_teams_first_game_has_no_rest_rather_than_an_invented_zero():
    df = frame([game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "Auburn", 30, 10)])
    row = df.iloc[0]
    assert pd.isna(row["home_rest"]) and pd.isna(row["away_rest"])


def test_pooled_opponents_get_no_rest_day():
    """"The FCS" is not a team and does not have a bye week."""
    df = frame([
        game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "W Carolina",
             38, 3, away_div="fcs"),
        game(2, 2024, 2, "2024-09-07T16:00:00.000Z", "Alabama", "Mercer",
             42, 7, away_div="fcs"),
    ])
    assert pd.isna(df.iloc[1]["away_rest"])
    assert df.iloc[1]["home_rest"] == pytest.approx(7.0)


# -- the leakage boundary --------------------------------------------------

def test_no_banned_column_reaches_the_feature_frame():
    a = adapter_over([game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "Auburn", 30, 10)])
    events = a.load_history(2024, 2024)
    cols = set(a.feature_frame(events, datetime(2024, 8, 31, tzinfo=timezone.utc)).columns)
    assert not (BANNED_FEATURES & cols)


def test_third_party_pregame_elo_is_kept_for_audit_but_is_not_a_feature():
    """It is excluded on provenance, not because it is post-game.

    The column may well be pre-game, but cfbfastR-data is rebuilt
    historically and nothing in the file demonstrates that a given row was
    computed from strictly prior games. base.py requires each feature be
    justifiable as knowable at asof; it stays in meta so a later session can
    audit it, and out of the frame until someone does.
    """
    a = adapter_over([game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "Auburn", 30, 10)])
    events = a.load_history(2024, 2024)
    assert events[0].meta["home_pregame_elo"] == 1600
    cols = set(a.feature_frame(events, datetime(2024, 8, 31, tzinfo=timezone.utc)).columns)
    assert not (UNVERIFIABLE_PREGAME & cols)


# -- what this source cannot support --------------------------------------

def test_historical_lines_are_empty_rather_than_invented():
    """cfbfastR has no market data. The honest return is nothing.

    If this ever returns rows, a college backtest can produce a closing-line
    -value or ATS number, and every one of them would be graded against a
    price this source never carried.
    """
    a = adapter_over([game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "Auburn", 30, 10)])
    assert a.load_historical_lines(a.load_history(2024, 2024)) == []


def test_live_capture_does_not_leak_into_the_historical_path(tmp_path):
    """Our own capture is a live series, not an archive.

    Returning it from load_historical_lines would let a 2002-2025 backtest
    appear to have market data for the handful of 2026 days we have captured,
    unlabelled and ungradeable.
    """
    cap = tmp_path / "ncaaf"
    cap.mkdir()
    (cap / "2026-08-29.jsonl").write_text(json.dumps({
        "observed_at": "2026-08-29T01:53:24.596712+00:00", "event_id": "abc",
        "sport": "ncaaf", "kickoff": "2026-08-29T21:30:00Z", "home": "Alabama",
        "away": "Auburn", "book": "Bovada", "market": "moneyline",
        "selection": "Alabama", "line": None, "price": -250,
        "provenance": "own_capture",
    }) + "\n")
    a = adapter_over(
        [game(1, 2026, 1, "2026-08-29T21:30:00.000Z", "Alabama", "Auburn")],
        capture_dir=cap)
    events = a.upcoming(datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert a.load_historical_lines(events) == []
    live = a.current_lines(events)
    assert [l.price for l in live] == [-250]
    assert live[0].selection == "side_a"
    assert live[0].is_closing is False, "a poll is not a close"


def test_a_capture_row_that_does_not_match_an_event_is_dropped(tmp_path):
    """A moneyline filed against the wrong game is worse than one we lack."""
    cap = tmp_path / "ncaaf"
    cap.mkdir()
    (cap / "2026-08-29.jsonl").write_text(json.dumps({
        "observed_at": "2026-08-29T01:53:24.596712+00:00", "event_id": "abc",
        "sport": "ncaaf", "kickoff": "2026-08-29T21:30:00Z",
        "home": "Ohio State", "away": "Michigan", "book": "Bovada",
        "market": "moneyline", "selection": "Ohio State", "line": None,
        "price": -250, "provenance": "own_capture",
    }) + "\n")
    a = adapter_over(
        [game(1, 2026, 1, "2026-08-29T21:30:00.000Z", "Alabama", "Auburn")],
        capture_dir=cap)
    assert a.current_lines(a.upcoming(datetime(2026, 8, 1, tzinfo=timezone.utc))) == []


def test_espn_long_team_names_still_join_to_cfbfastr_short_names(tmp_path):
    """The two sources spell the same team differently, by design of neither.

    Capture carries ESPN's "North Dakota State Bison"; cfbfastR carries
    "North Dakota State". An exact-string join would silently return nothing
    for every game, which looks identical to "no prices captured yet".
    """
    cap = tmp_path / "ncaaf"
    cap.mkdir()
    (cap / "d.jsonl").write_text(json.dumps({
        "observed_at": "2026-08-29T01:53:24.596712+00:00", "event_id": "x",
        "sport": "ncaaf", "home": "North Dakota State Bison",
        "away": "Jacksonville State Gamecocks", "book": "Bovada",
        "market": "moneyline", "selection": "North Dakota State Bison",
        "line": None, "price": -250, "provenance": "own_capture",
    }) + "\n")
    a = adapter_over(
        [game(1, 2026, 1, "2026-08-29T21:30:00.000Z",
              "North Dakota State", "Jacksonville State")],
        capture_dir=cap)
    # The join is normalised on both sides, so the long ESPN form still lands.
    assert len(a.current_lines(a.upcoming(datetime(2026, 8, 1, tzinfo=timezone.utc)))) == 1


# -- the schema contract ---------------------------------------------------

def test_events_carry_the_college_sport_and_a_utc_kickoff():
    a = adapter_over([game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "Auburn", 30, 10)])
    e = a.load_history(2024, 2024)[0]
    assert e.sport is Sport.NCAAF
    assert e.status is Status.FINAL
    assert e.start_time == datetime(2024, 8, 31, 16, 0, tzinfo=timezone.utc)
    assert e.side_a == "Alabama" and e.side_b == "Auburn"


def test_results_are_keyed_by_event_and_signed_from_the_home_side():
    a = adapter_over([game(1, 2024, 1, "2024-08-31T16:00:00.000Z", "Alabama", "Auburn", 30, 10)])
    events = a.load_history(2024, 2024)
    assert a.load_results(events)["1"].margin == 20.0


# -- the refit -------------------------------------------------------------

def test_college_elo_does_not_inherit_the_nfl_constants():
    """docs/plans/college-football.md calls reusing them "a fabricated model".

    Every searched constant must differ from the NFL default. If a refit ever
    lands one back on the NFL value, that is a result worth looking at rather
    than a coincidence to ship silently.
    """
    nfl = EloConfig()
    for f in ("k", "home_advantage", "season_carryover", "elo_per_point"):
        assert getattr(NCAAF_ELO, f) != getattr(nfl, f), f


# -- the two join mechanisms, measured on real captured names --------------

def test_a_qualifier_remainder_blocks_the_wrong_school():
    """"Ohio State Buckeyes" must not resolve to `Ohio`.

    This is a wrong-match, not an ambiguity: in a week where Ohio plays and
    Ohio State does not, the captured Ohio State row prefix-matches `Ohio`
    UNIQUELY, so a uniqueness check alone accepts it and files the price
    against the wrong game with nothing reporting it.

    Measured on 2026-08-29: of 188 distinct captured team names checked
    against the 230 teams in the 2025 schedule, a bare prefix rule left 18
    ambiguous; requiring the remainder to look like a mascot leaves 4.
    """
    from engine.adapters.ncaaf import _prefixes
    assert not _prefixes("ohio", "ohiostatebuckeyes")
    assert _prefixes("ohiostate", "ohiostatebuckeyes")
    assert _prefixes("ohio", "ohiobobcats")


def test_the_more_specific_school_wins_when_both_are_on_the_slate():
    """The remaining collisions are hyphenated or parenthesised names.

    "Arkansas-Pine Bluff Golden Lions" prefixes both `Arkansas` and
    `Arkansas-Pine Bluff`. Specificity resolves it to the right one rather
    than dropping it; QUALIFIERS covers the other direction. The two
    mechanisms are complementary and both are needed.
    """
    from engine.adapters.ncaaf import _resolve

    class E:
        def __init__(self, n): self.event_id = n

    short, long_ = E("short"), E("long")
    keyed = [("arkansas", "opponent", short),
             ("arkansaspinebluff", "opponent", long_)]
    assert _resolve(keyed, "arkansaspinebluffgoldenlions", "opponentmascot") is long_


def test_an_exact_specificity_tie_is_dropped_rather_than_guessed():
    from engine.adapters.ncaaf import _resolve

    class E:
        def __init__(self, n): self.event_id = n

    keyed = [("aa", "bb", E("one")), ("aa", "bb", E("two"))]
    assert _resolve(keyed, "aamascot", "bbmascot") is None
