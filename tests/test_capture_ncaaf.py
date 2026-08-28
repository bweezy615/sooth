"""The capture bugs that would silently lose college football games.

Every check here exists because the NFL shape does not carry over to college
football, and because each failure mode is invisible in the output: you get a
smaller file, not an error.

Endpoint facts pinned below were read from the live ESPN core API on
2026-08-28 and are recorded in docs/plans/college-football.md.
"""

from __future__ import annotations

import pytest
import requests

from engine.capture import LEAGUES, PAGE, core, week_event_ids, weeks_with_events
from engine.schema import Sport


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    """Serves a paginated ESPN week-events response and records the URLs."""

    def __init__(self, total: int, page_size: int):
        self.total = total
        self.page_size = page_size
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        page = 1
        for part in url.split("?", 1)[-1].split("&"):
            if part.startswith("page="):
                page = int(part.split("=", 1)[1])
        start = (page - 1) * self.page_size
        ids = range(start, min(start + self.page_size, self.total))
        page_count = -(-self.total // self.page_size)
        return FakeResponse({
            "count": self.total,
            "pageIndex": page,
            "pageCount": page_count,
            "items": [{"$ref": f"http://x/events/{i}?lang=en"} for i in ids],
        })


def test_ncaaf_is_a_sport():
    assert Sport.NCAAF.value == "ncaaf"
    # engine/xcards.py's LIQUID set already spells it this way; a different
    # slug here would have split college football across two names.
    from engine.xcards import LIQUID
    assert "ncaaf" in LIQUID


def test_college_football_uses_its_own_league_path():
    assert core("nfl").endswith("/football/leagues/nfl")
    assert core("ncaaf").endswith("/football/leagues/college-football")


def test_week_numbering_is_not_shared_with_the_nfl():
    # Live endpoint, 2026-08-28: NFL regular season is types/2 weeks 1-18,
    # college football is types/2 weeks 1-15 with bowls under types/3.
    assert weeks_with_events("nfl") == list(range(1, 19))
    assert weeks_with_events("ncaaf") == list(range(1, 16))


def test_college_football_asks_for_the_fbs_group():
    # Without groups=80 the live week-1 endpoint returns 25 curated "featured"
    # games instead of the 99 FBS games that exist, and says nothing about it.
    assert LEAGUES["ncaaf"]["groups"] == "80"
    assert LEAGUES["nfl"]["groups"] is None

    session = FakeSession(total=99, page_size=PAGE)
    week_event_ids(2026, 1, session, "ncaaf")
    assert all("groups=80" in u for u in session.urls)

    session = FakeSession(total=16, page_size=PAGE)
    week_event_ids(2026, 1, session, "nfl")
    assert not any("groups=" in u for u in session.urls)


def test_a_slate_bigger_than_one_page_is_not_truncated():
    """The bug: limit=50 against a 99-game week returned 50 and no error."""
    session = FakeSession(total=99, page_size=50)
    ids, expected = week_event_ids(2026, 1, session, "ncaaf")
    assert expected == 99
    assert len(ids) == 99
    assert len(set(ids)) == 99


def test_duplicate_ids_across_pages_are_collapsed_not_counted():
    class Dupes(FakeSession):
        def get(self, url, **kwargs):
            self.urls.append(url)
            return FakeResponse({
                "count": 3, "pageCount": 2, "pageIndex": 1,
                "items": [{"$ref": "http://x/events/1"},
                          {"$ref": "http://x/events/1"}],
            })

    ids, expected = week_event_ids(2026, 1, Dupes(3, 2), "ncaaf")
    assert ids == ["1"]
    assert expected == 3


def test_a_short_week_is_reported_not_swallowed():
    """ESPN says 99, we could only list 40: the caller must be able to tell."""
    class Short(FakeSession):
        def get(self, url, **kwargs):
            self.urls.append(url)
            return FakeResponse({
                "count": 99, "pageCount": 1, "pageIndex": 1,
                "items": [{"$ref": f"http://x/events/{i}"} for i in range(40)],
            })

    ids, expected = week_event_ids(2026, 1, Short(99, 50), "ncaaf")
    assert len(ids) == 40 and expected == 99


def test_an_http_error_mid_pagination_keeps_what_it_already_has():
    class Flaky(FakeSession):
        def get(self, url, **kwargs):
            self.urls.append(url)
            if "page=2" in url:
                raise requests.HTTPError("boom")
            return FakeResponse({
                "count": 99, "pageCount": 2, "pageIndex": 1,
                "items": [{"$ref": f"http://x/events/{i}"} for i in range(50)],
            })

    ids, expected = week_event_ids(2026, 1, Flaky(99, 50), "ncaaf")
    assert len(ids) == 50 and expected == 99  # short -> caller reports it


def test_rows_carry_their_own_sport():
    """The old _extract hardcoded sport="nfl", which would have filed every
    college game into the NFL series."""
    from engine.capture import _extract
    item = {"provider": {"name": "DraftKings"},
            "homeTeamOdds": {"current": {"pointSpread": {"value": -38.5},
                                         "spread": {"american": "-110"}}}}
    meta = {"event_id": "1", "season": 2026, "week": 1, "kickoff": "x",
            "home": "USC Trojans", "away": "San Jose State Spartans"}
    rows = list(_extract(item, meta=meta, observed_at="t", sport="ncaaf"))
    assert rows and all(r.sport == "ncaaf" for r in rows)
    rows = list(_extract(item, meta=meta, observed_at="t"))
    assert rows and all(r.sport == "nfl" for r in rows)
