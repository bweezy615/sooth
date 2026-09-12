"""Only games that have been played say anything about capture closeness.

`scripts/capture_closeness.py` decides whether a sport's own capture is good
enough to grade against. Its first version scored every event we held an
observation for, including ones whose kickoff was still days away — where
"minutes from our last observation to kickoff" measures how far off the game
is, not how close we got. That reported college football at a 3,294-minute p75
and the NFL at a 15,864-minute median while NFL week 1 had not been played.

The corrected figure for the same college data was a p75 of 99 minutes. An
error of that size in the direction of "our evidence is useless" is how a sport
gets written off, so the rule gets a test.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.capture_closeness import measure

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def row(event_id, kickoff, observed, provenance="own_capture"):
    return {"event_id": event_id, "kickoff": kickoff.strftime("%Y-%m-%dT%H:%MZ"),
            "observed_at": observed.isoformat(), "provenance": provenance,
            "sport": "ncaaf", "book": "DraftKings", "market": "spread"}


@pytest.fixture
def capture(tmp_path, monkeypatch):
    """Two played games and one still days away."""
    d = tmp_path / "data/capture/ncaaf"
    d.mkdir(parents=True)
    played = NOW - timedelta(days=2)
    future = NOW + timedelta(days=5)
    rows = [
        # played, last seen 20 minutes out
        row("A", played, played - timedelta(hours=6)),
        row("A", played, played - timedelta(minutes=20)),
        # played, last seen 2 hours out
        row("B", played, played - timedelta(hours=2)),
        # NOT played: last seen 5 days out because it has not happened yet
        row("C", future, NOW - timedelta(minutes=10)),
    ]
    (d / "2026-09-07.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return d


def test_an_unplayed_game_is_not_scored(capture):
    """The bug this file exists for. Event C has a perfectly good observation
    ten minutes old; it is five days from kickoff and says nothing yet."""
    m = measure("ncaaf", "own_capture", now=NOW)
    assert m["events_seen"] == 3
    assert m["events_played"] == 2
    assert len(m["gaps"]) == 2
    assert max(m["gaps"]) < 200, (
        "a game five days out must not contribute a 7,200-minute gap")


def test_the_gap_is_to_the_latest_observation_not_the_first(capture):
    """Event A was seen at six hours and again at twenty minutes. Only the
    last one describes how close we got."""
    m = measure("ncaaf", "own_capture", now=NOW)
    assert min(m["gaps"]) == pytest.approx(20.0)


def test_both_played_games_are_counted(capture):
    m = measure("ncaaf", "own_capture", now=NOW)
    assert sorted(round(g) for g in m["gaps"]) == [20, 120]


def test_provenance_filters_out_someone_elses_claim(capture, tmp_path):
    """HANDOFF §4.3: only own_capture and oddsapi_historical_close may back a
    CLV figure. espn_open is ESPN's number, not ours."""
    played = NOW - timedelta(days=2)
    (tmp_path / "data/capture/ncaaf/2026-09-08.jsonl").write_text(
        json.dumps(row("D", played, played - timedelta(minutes=5),
                       provenance="espn_open")) + "\n", encoding="utf-8")
    assert measure("ncaaf", "own_capture", now=NOW)["events_played"] == 2
    assert measure("ncaaf", "", now=NOW)["events_played"] == 3


def test_an_observation_after_kickoff_is_not_a_pre_game_price(capture, tmp_path):
    played = NOW - timedelta(days=2)
    (tmp_path / "data/capture/ncaaf/2026-09-08.jsonl").write_text(
        json.dumps(row("E", played, played + timedelta(minutes=30))) + "\n",
        encoding="utf-8")
    m = measure("ncaaf", "own_capture", now=NOW)
    assert m["events_played"] == 2, "E was only ever seen after it kicked off"
