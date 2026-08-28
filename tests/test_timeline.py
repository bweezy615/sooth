"""timeline.json is where the market's price history is actually published.

It had no tests. The equivalent series used to be computed a second time in
`engine/research.py::movement()` and published inside research.json, where it
was 46% of the payload and read by no code path on the site; the tests for the
"a line move starts a new series" invariant lived on that dead copy. Deleting
the copy without moving its checks here would have retired the only test of a
rule that still governs a published file.

See docs/plans/research-payload-size.md.
"""
from __future__ import annotations

import datetime as dt
import json

from engine.timeline import build_sport

FUTURE = "2099-01-01T00:00:00+00:00"


def obs(book, price, at, sel="side_a", market="spread", line=-3.5, event="E1"):
    return {"event_id": event, "sport": "nfl", "market": market,
            "selection": sel, "book": book, "price": price, "line": line,
            "observed_at": at, "home": "Seattle Seahawks",
            "away": "New England Patriots", "kickoff": FUTURE,
            "season": 2026, "week": 1, "provenance": "own_capture"}


def _root(tmp_path, rows):
    d = tmp_path / "data/capture/nfl"
    d.mkdir(parents=True)
    (d / "obs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _hours_ago(n):
    return (_now() - dt.timedelta(hours=n)).isoformat()


def test_a_line_move_starts_a_new_series(tmp_path):
    """-160 at spread 6.5 is a price for a different bet than -110 at 3.5.

    Folding them into one trace draws a 50-point collapse in implied
    probability that never happened. The dominant line wins the chart and the
    other line's prices must not appear on it.
    """
    rows = []
    for h in (6, 5, 4):
        rows += [obs("DraftKings", -110, _hours_ago(h)),
                 obs("FanDuel", -110, _hours_ago(h))]
    # the number moved; these belong to a different bet
    rows += [obs("DraftKings", -160, _hours_ago(3), line=-6.5),
             obs("FanDuel", -160, _hours_ago(3), line=-6.5)]

    events = build_sport("nfl", _root(tmp_path, rows), _now())
    assert len(events) == 1
    spread = events[0]["markets"]["spread"]
    assert spread["line"] == -3.5, "the dominant line must win the chart"
    assert all(abs(v - 52.38) < 0.01 for _, v in spread["consensus"]), (
        "a price from the 6.5 series leaked onto the 3.5 chart"
    )


def test_a_series_of_one_observation_is_not_published(tmp_path):
    """One point is not a history, and drawing it implies a flat market."""
    rows = [obs("DraftKings", -110, _hours_ago(2))]
    events = build_sport("nfl", _root(tmp_path, rows), _now())
    assert events == [] or "spread" not in events[0]["markets"]


def test_started_games_are_not_published(tmp_path):
    """A timeline is for a bet you can still place."""
    rows = [dict(obs("DraftKings", -110, _hours_ago(h)),
                 kickoff="2020-01-01T00:00:00+00:00") for h in (5, 4)]
    assert build_sport("nfl", _root(tmp_path, rows), _now()) == []
