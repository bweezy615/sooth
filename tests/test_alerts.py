"""Tests for line-movement detection.

An alert system fails in two directions and both are expensive: silence on a
real move wastes the product, and noise on a tick trains people to ignore it.
These test both directions, plus the arithmetic mistake that would quietly
break everything.
"""

from __future__ import annotations

import json

import pytest

from engine.alerts import (DEFAULT_MIN_MOVE, find_divergence, find_drift,
                           implied, load_observations, scan)


# Far enough out that these rows always read as "not started". Real game-line
# capture carries kickoff on every row (all 116k of them in data/capture at the
# time of writing), so a fixture without one was never representative — and it
# hid the fact that a row we cannot date used to be published as a live edge.
FUTURE = "2099-01-01T00:00:00+00:00"


def obs(book, price, at, sel="side_a", event="E1", market="moneyline",
        provenance="own_capture", kickoff=FUTURE):
    return {"event_id": event, "sport": "nfl", "market": market,
            "selection": sel, "book": book, "price": price,
            "observed_at": at, "home": "SEA", "away": "NE",
            "kickoff": kickoff, "provenance": provenance}


# --------------------------------------------------------------------------
# arithmetic: the mistake that would break every alert silently
# --------------------------------------------------------------------------

def test_started_and_undateable_games_are_never_published_as_edges():
    """An alert we cannot date must not be published under the word "now".

    The guard used to run `if kickoff:` and fell through when the field was
    empty, so rows captured without a start time were advertised as live
    opportunities indefinitely. On 2026-08-11 the Edges tab was showing eight
    of them, every one for an MLB game finished 19-45 hours earlier.
    """
    started = [obs("DraftKings", -110, "2026-01-01T00:00:00+00:00", kickoff="2000-01-01T00:00:00+00:00"),
               obs("FanDuel", +200, "2026-01-01T00:00:00+00:00", kickoff="2000-01-01T00:00:00+00:00"),
               obs("BetMGM", -105, "2026-01-01T00:00:00+00:00", kickoff="2000-01-01T00:00:00+00:00")]
    assert find_divergence(started) == [], "a finished game is not an edge"

    undateable = [dict(r, kickoff="") for r in started]
    assert find_divergence(undateable) == [], "an undateable row must fail closed"

    # Drift needs two observations on the SAME series to fire at all, so give
    # it a real move — otherwise the assertion passes for the wrong reason.
    def moved(kick):
        return [obs("DraftKings", -110, "2026-01-01T00:00:00+00:00", kickoff=kick),
                obs("DraftKings", +150, "2026-01-01T01:00:00+00:00", kickoff=kick)]

    assert find_drift(moved(FUTURE)), "a real move on an upcoming game must still fire"
    assert find_drift(moved("2000-01-01T00:00:00+00:00")) == [], "finished game is history"
    assert find_drift(moved("")) == [], "drift must fail closed on an undateable row"


def test_player_props_never_enter_the_game_line_scan(tmp_path):
    """Prop quotes are a different market and belong on a different page.

    The default glob data/capture/*/*.jsonl also matches data/capture/
    mlb-props, so strikeout quotes were folded into the game-line consensus
    and published as "books off the pack".
    """
    (tmp_path / "mlb").mkdir()
    (tmp_path / "mlb-props").mkdir()
    row = obs("DraftKings", -110, "2026-01-01T00:00:00+00:00")
    (tmp_path / "mlb" / "d.jsonl").write_text(json.dumps(row) + "\n")
    (tmp_path / "mlb-props" / "d.jsonl").write_text(json.dumps(row) + "\n")
    rows = load_observations(str(tmp_path / "*" / "*.jsonl"))
    assert len(rows) == 1, "prop captures must not reach the game-line scan"


def test_move_is_measured_in_probability_not_raw_odds():
    """American odds are non-linear and discontinuous across +/-100.

    A 10-cent step is a different real move at different places on the scale.
    Measuring in raw odds makes a detector fire on nothing and miss everything.
    """
    near = abs(implied(-110) - implied(-120)) * 100
    far = abs(implied(+400) - implied(+410)) * 100
    assert near > far * 3, "same 10-cent step must not be treated as the same move"


def test_implied_crosses_even_money_correctly():
    assert implied(+100) == pytest.approx(0.5)
    assert implied(-200) == pytest.approx(2 / 3)


# --------------------------------------------------------------------------
# drift: fires on a real move, silent on a tick
# --------------------------------------------------------------------------

def test_drift_fires_on_a_real_move():
    rows = [obs("DraftKings", -105, "2026-08-03T03:53:21"),
            obs("DraftKings", -115, "2026-08-03T21:12:00")]
    alerts = find_drift(rows, DEFAULT_MIN_MOVE)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.kind == "drift"
    assert a.from_price == -105 and a.to_price == -115
    assert a.move_pts > 0, "shortening odds must read as a positive move"
    assert "shortened" in a.detail


def test_drift_is_silent_on_a_one_cent_tick():
    rows = [obs("DraftKings", -110, "2026-08-03T03:53:21"),
            obs("DraftKings", -111, "2026-08-03T21:12:00")]
    assert find_drift(rows, DEFAULT_MIN_MOVE) == []


def test_drift_signs_the_direction():
    out = find_drift([obs("BetUS", -115, "2026-08-03T01:00:00"),
                      obs("BetUS", -105, "2026-08-03T02:00:00")], DEFAULT_MIN_MOVE)
    assert len(out) == 1 and out[0].move_pts < 0
    assert "drifted out" in out[0].detail


def test_drift_catches_a_slow_walk_at_the_crossing_step():
    """Many small steps must still raise one alert, not none."""
    rows = [obs("BetMGM", -100, "2026-08-03T01:00:00"),
            obs("BetMGM", -105, "2026-08-03T02:00:00"),
            obs("BetMGM", -125, "2026-08-03T03:00:00")]
    alerts = find_drift(rows, DEFAULT_MIN_MOVE)
    assert len(alerts) == 1
    assert alerts[0].from_price == -105 and alerts[0].to_price == -125


def test_drift_never_compares_across_books():
    rows = [obs("DraftKings", -105, "2026-08-03T01:00:00"),
            obs("BetRivers", -140, "2026-08-03T02:00:00")]
    assert find_drift(rows, DEFAULT_MIN_MOVE) == [], \
        "two books quoting differently is divergence, never drift"


# --------------------------------------------------------------------------
# divergence: needs a real consensus behind it
# --------------------------------------------------------------------------

def test_divergence_fires_when_one_book_pays_more():
    rows = [obs("A", -140, "2026-08-03T02:00:00"),
            obs("B", -138, "2026-08-03T02:00:00"),
            obs("C", -142, "2026-08-03T02:00:00"),
            obs("D", -110, "2026-08-03T02:00:00")]
    alerts = find_divergence(rows, DEFAULT_MIN_MOVE)
    assert [a.book for a in alerts] == ["D"]
    assert alerts[0].move_pts > 0


def test_divergence_ignores_a_book_paying_less_than_consensus():
    """A worse price is not an opportunity and must never alert."""
    rows = [obs("A", -110, "2026-08-03T02:00:00"),
            obs("B", -112, "2026-08-03T02:00:00"),
            obs("C", -108, "2026-08-03T02:00:00"),
            obs("D", -175, "2026-08-03T02:00:00")]
    assert [a.book for a in find_divergence(rows, DEFAULT_MIN_MOVE)] == []


def test_divergence_requires_at_least_three_books():
    rows = [obs("A", -140, "2026-08-03T02:00:00"),
            obs("B", -110, "2026-08-03T02:00:00")]
    assert find_divergence(rows, DEFAULT_MIN_MOVE) == [], \
        "two books disagreeing is not a consensus to diverge from"


def test_divergence_uses_each_book_latest_price():
    rows = [obs("A", -140, "2026-08-03T01:00:00"),
            obs("B", -138, "2026-08-03T01:00:00"),
            obs("C", -142, "2026-08-03T01:00:00"),
            obs("D", -190, "2026-08-03T01:00:00"),
            obs("D", -110, "2026-08-03T05:00:00")]   # D later becomes the outlier
    alerts = find_divergence(rows, DEFAULT_MIN_MOVE)
    assert [a.book for a in alerts] == ["D"]
    assert alerts[0].to_price == -110


# --------------------------------------------------------------------------
# provenance gate
# --------------------------------------------------------------------------

def test_only_our_own_captures_can_raise_an_alert(tmp_path):
    """espn_open is someone else's claim about a price we did not watch."""
    p = tmp_path / "nfl"
    p.mkdir(parents=True)
    f = p / "day.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in [
        obs("DraftKings", -105, "2026-08-03T01:00:00", provenance="espn_open"),
        obs("DraftKings", -160, "2026-08-03T02:00:00", provenance="espn_open"),
    ]))
    rows = load_observations(str(tmp_path / "*" / "*.jsonl"))
    assert rows == []
    assert scan(str(tmp_path / "*" / "*.jsonl"))["drift"] == []


# --- retired sports stop being published, without their evidence being deleted


def test_only_sports_the_board_still_fetches_are_published():
    """UFC came off the board on 2026-08-28 and its capture history stayed on
    disk, as evidence always does. /edges kept publishing 232 UFC "moves"
    computed from prices nobody was refreshing any more - frozen movement
    presented as current movement, for a sport the site no longer claims."""
    from engine.alerts import published_sports
    from engine.lines import SPORTS

    assert published_sports() == {m["slug"] for m in SPORTS.values()}
    assert "ufc" not in published_sports()
    assert "ncaaf" in published_sports()


def test_a_retired_sports_rows_are_skipped(tmp_path):
    from engine.alerts import load_observations

    def write(sport, price):
        d = tmp_path / sport
        d.mkdir()
        row = {"observed_at": "2026-08-28T00:00:00+00:00", "event_id": "1",
               "sport": sport, "kickoff": "2099-01-01T00:00:00+00:00",
               "home": "A", "away": "B", "book": "DraftKings",
               "market": "moneyline", "selection": "A", "line": None,
               "price": price, "provenance": "own_capture"}
        (d / "2026-08-28.jsonl").write_text(json.dumps(row) + "\n")

    write("nfl", -110)
    write("ufc", -120)
    pattern = str(tmp_path / "*" / "*.jsonl")

    kept = load_observations(pattern)
    assert {r["sport"] for r in kept} == {"nfl"}

    # ...but the rows are still readable on request. We stopped publishing the
    # sport; we did not lose it.
    both = load_observations(pattern, sports=frozenset({"nfl", "ufc"}))
    assert {r["sport"] for r in both} == {"nfl", "ufc"}
