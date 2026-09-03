"""One sport must not be able to spend the whole props run.

Until college football was added, engine.props walked PROP_MARKETS in dict
order against a single shared ceiling, first come first served. That is
invisible while one sport at a time is in season and wrong the moment two are:
every run from 2026-08-31 to 2026-09-03 spent the full 12 credits and
published MLB alone, because NFL week 1 was still outside the 30-hour window
and MLB, next in the dict, took everything that was left.

Adding a fifth sport to that scheme would not have shared the budget. It would
only have changed which sport won it — and on a Thursday in September the
winner would have been college football, silently emptying the baseball board
that had been the entire props product for a week.
"""

from __future__ import annotations

import engine.props as props


class _Resp:
    status_code = 200

    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class _Session:
    """Every sport has plenty of events, and every event returns one prop.

    The point is the budget, so the payload is the smallest thing that counts
    as a real answer: two books a side at one line, which clears MIN_BOOKS
    only if MIN_BOOKS allows it. It does not — so props come back empty and
    the empties counter would stop us after two events. That is the wrong
    thing to measure here, so the fetch is stubbed instead and only the
    accounting is under test.
    """

    def __init__(self):
        self.events_for = []

    def get(self, url, params=None, timeout=None):
        if url.endswith("/events"):
            self.events_for.append(url)
            return _Resp([{"id": f"e{i}", "commence_time": "2026-09-04T00:00:00Z",
                           "home_team": "H", "away_team": "A"} for i in range(20)])
        return _Resp([], {})


def _run(monkeypatch, live, max_credits):
    """Collect with a stubbed per-event fetch that always costs and always
    returns one prop, so no sport stops early for lack of content."""
    spend_log = []

    def fake_event_props(sport_key, event, key, session, market_labels):
        spend_log.append(sport_key)
        cost = len(market_labels)
        return ([{"market": "m", "player": "p", "line": 1.5, "gain_pts": 1.0}],
                cost, 5000)

    monkeypatch.setattr(props, "load_key", lambda: "k")
    monkeypatch.setattr(props, "active_sports", lambda *a, **k: live)
    monkeypatch.setattr(props, "_event_props", fake_event_props)
    monkeypatch.setattr(props.requests, "Session", lambda: _Session())
    doc = props.collect(window_hours=30, max_credits=max_credits, dry_run=True)
    return doc, spend_log


def test_two_sports_in_season_split_the_run(monkeypatch):
    """The case this file exists for: a Thursday with college football
    tonight and baseball tonight."""
    doc, log = _run(monkeypatch,
                    {"americanfootball_ncaaf", "baseball_mlb"}, 18)
    assert log.count("americanfootball_ncaaf") == 3
    assert log.count("baseball_mlb") == 3, (
        "baseball must not be emptied by the sport that comes first")
    assert doc["credits_spent"] == 18


def test_one_sport_in_season_still_gets_its_half(monkeypatch):
    """The cap is a ceiling, not a quota — an idle night is not padded, but a
    lone sport is not throttled to a share of a budget nobody else wants
    beyond its own half."""
    doc, log = _run(monkeypatch, {"baseball_mlb"}, 18)
    assert log.count("baseball_mlb") == 3
    assert doc["credits_spent"] == 9


def test_the_run_ceiling_is_still_absolute(monkeypatch):
    """Per-sport caps must never add up past --max-credits."""
    live = {"americanfootball_nfl", "americanfootball_ncaaf", "baseball_mlb",
            "basketball_nba", "icehockey_nhl"}
    doc, _ = _run(monkeypatch, live, 18)
    assert doc["credits_spent"] <= 18


def test_a_budget_too_small_to_split_still_buys_one_event(monkeypatch):
    """max_credits // 2 can fall below the cost of a single event. The cap
    must not round down to zero and publish nothing at all."""
    doc, log = _run(monkeypatch, {"baseball_mlb"}, 4)
    assert log.count("baseball_mlb") == 1
    assert doc["credits_spent"] == 3


def test_college_football_is_a_props_sport(monkeypatch):
    assert "americanfootball_ncaaf" in props.PROP_MARKETS
    assert props.PROP_MARKETS["americanfootball_ncaaf"]["slug"] == "ncaaf"
    assert props.PROP_MARKETS["americanfootball_ncaaf"]["label"] == "CFB"
