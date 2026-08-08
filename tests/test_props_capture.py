"""Props capture — the two failure modes that would silently poison the record.

  - a parser that drops the pitcher name or the line writes an ungradeable row
  - a credit cap that leaks turns a "free tier" cron into a surprise bill

Run: pytest -q
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from engine import props_capture as pc

UTC = timezone.utc

# One /events/{id}/odds response with two pitchers across two books.
EVENT_ODDS = {
    "id": "evt1",
    "commence_time": "2026-08-08T23:05:00Z",
    "home_team": "New York Yankees",
    "away_team": "Boston Red Sox",
    "bookmakers": [
        {"key": "draftkings", "markets": [
            {"key": "pitcher_strikeouts", "outcomes": [
                {"name": "Over", "description": "Gerrit Cole", "price": -115, "point": 6.5},
                {"name": "Under", "description": "Gerrit Cole", "price": -105, "point": 6.5},
            ]},
            {"key": "h2h", "outcomes": [  # noise — must be ignored
                {"name": "New York Yankees", "price": -150},
            ]},
        ]},
        {"key": "fanduel", "markets": [
            {"key": "pitcher_strikeouts", "outcomes": [
                {"name": "Over", "description": "Brayan Bello", "price": 100, "point": 5.5},
                {"name": "Under", "description": "Brayan Bello", "price": -120, "point": 5.5},
            ]},
        ]},
    ],
}


def test_parser_keeps_player_line_and_ignores_other_markets():
    rows = pc._rows_from_event(EVENT_ODDS, "2026-08-08T22:30:00+00:00")
    assert len(rows) == 4  # 2 pitchers x over/under; h2h dropped
    cole_over = next(r for r in rows if r.player == "Gerrit Cole" and r.selection == "over")
    assert cole_over.line == 6.5 and cole_over.price == -115
    assert cole_over.book == "draftkings"
    assert cole_over.provenance == "own_capture"
    assert all(r.market == "pitcher_strikeouts" for r in rows)


def test_closing_window_excludes_games_outside_the_pre_pitch_window():
    now = datetime(2026, 8, 8, 22, 30, tzinfo=UTC)
    events = [
        {"id": "soon", "commence_time": "2026-08-08T23:05:00Z"},   # +35 min -> in
        {"id": "later", "commence_time": "2026-08-09T02:00:00Z"},  # hours -> out
        {"id": "past", "commence_time": "2026-08-08T22:00:00Z"},   # started -> out
    ]
    keep = {e["id"] for e in pc._closing_events(events, now)}
    assert keep == {"soon"}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


class _FakeSession:
    """Returns the event list, then EVENT_ODDS for every per-event call."""
    def __init__(self):
        self.event_calls = 0
    def get(self, url, params=None, timeout=None):
        if url == pc.EVENTS:
            now = "2026-08-08T22:30:00Z"  # base; commence times set below
            return _FakeResp([
                {"id": f"g{i}", "commence_time": "2026-08-08T23:00:00Z"}
                for i in range(10)  # 10 games all inside the window
            ])
        self.event_calls += 1
        return _FakeResp(EVENT_ODDS)


def test_credit_ceiling_refuses_to_exceed_max_credits(monkeypatch, tmp_path):
    session = _FakeSession()
    monkeypatch.setattr(pc, "load_key", lambda: "test-key")
    monkeypatch.setattr(pc.requests, "Session", lambda: session)
    now = datetime(2026, 8, 8, 22, 30, tzinfo=UTC)

    pc.capture_props(now, max_credits=3, out_dir=tmp_path)

    assert session.event_calls == 3  # stopped at the ceiling, not 10
    lines = (tmp_path / "mlb-props" / "2026-08-08.jsonl").read_text().splitlines()
    assert len(lines) == 3 * 4  # 3 games x 4 prop rows each, appended
