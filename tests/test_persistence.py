"""Write-behavior tests: props.json no-clobber, atomic writes, hitrates
player resolution, and the middles keep-previous path.

All network entry points are monkeypatched; nothing here touches the wire.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from engine import hitrates, middles, props


# ---------------------------------------------------------------- helpers

class FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    """Stands in for requests.Session; returns a canned response."""

    def __init__(self, payload, status_code=200):
        self.resp = FakeResp(payload, status_code)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return self.resp


def _no_tmp_left(directory):
    return [p.name for p in directory.iterdir() if p.suffix == ".tmp"] == []


PREV_PROPS_DOC = {
    "generated_at": "2026-08-01T00:00:00+00:00",
    "window_hours": 30,
    "credits_spent": 6,
    "credits_remaining": 400,
    "boards": [{
        "sport": "mlb", "label": "MLB", "n_events": 1, "n_props": 1,
        "avg_gain_pts": 2.0, "max_gain_pts": 2.0,
        "events": [{"id": "ev1", "home": "H", "away": "A",
                    "starts": "2026-08-01T23:00:00Z",
                    "props": [{"market": "batter_hits", "player": "X",
                               "line": 1.5, "gain_pts": 2.0}]}],
    }],
    "totals": {"events": 1, "props": 1, "max_gain_pts": 2.0},
}


def _quiet_props(monkeypatch):
    """props.collect with no live network: one live sport, zero events."""
    monkeypatch.setattr(props, "load_key", lambda: "test-key")
    monkeypatch.setattr(props, "active_sports", lambda k, s: {"baseball_mlb"})
    monkeypatch.setattr(props, "upcoming_events",
                        lambda sport, key, session, window, now: [])


# ---------------------------------------------------------- props.collect

def test_props_collect_keeps_previous_board_when_slate_empty(tmp_path,
                                                             monkeypatch):
    """Empty fetch + existing props on disk -> old props kept, checked_at added."""
    _quiet_props(monkeypatch)
    out = tmp_path / "props.json"
    out.write_text(json.dumps(PREV_PROPS_DOC))

    doc = props.collect(out_dir=tmp_path)

    assert doc["kept_previous"] is True
    on_disk = json.loads(out.read_text())
    # The previous board survives untouched...
    assert on_disk["boards"] == PREV_PROPS_DOC["boards"]
    assert on_disk["totals"]["props"] == 1
    assert on_disk["generated_at"] == PREV_PROPS_DOC["generated_at"]
    # ...but the file records that we looked, with a parseable timestamp.
    assert "checked_at" in on_disk
    datetime.fromisoformat(on_disk["checked_at"])
    # remaining was never learned this run (-1), and gets recorded as such
    assert on_disk["credits_remaining"] == -1
    assert _no_tmp_left(tmp_path)


def test_props_collect_overwrites_previous_file_with_zero_props(tmp_path,
                                                                monkeypatch):
    """A previous file with no props is not worth preserving: overwrite it."""
    _quiet_props(monkeypatch)
    empty_prev = dict(PREV_PROPS_DOC, boards=[],
                      totals={"events": 0, "props": 0, "max_gain_pts": 0})
    out = tmp_path / "props.json"
    out.write_text(json.dumps(empty_prev))

    doc = props.collect(out_dir=tmp_path)

    assert "kept_previous" not in doc
    on_disk = json.loads(out.read_text())
    assert on_disk["generated_at"] == doc["generated_at"]
    assert on_disk["boards"] == []
    assert _no_tmp_left(tmp_path)


def test_props_collect_survives_corrupt_previous_file(tmp_path, monkeypatch):
    """Garbage on disk must not crash the run; the fresh doc replaces it."""
    _quiet_props(monkeypatch)
    out = tmp_path / "props.json"
    out.write_text("{not json")

    doc = props.collect(out_dir=tmp_path)

    assert "kept_previous" not in doc
    on_disk = json.loads(out.read_text())  # valid JSON again
    assert on_disk["generated_at"] == doc["generated_at"]
    assert _no_tmp_left(tmp_path)


def test_props_collect_fresh_write_is_atomic_and_captures(tmp_path,
                                                          monkeypatch):
    """A real board writes props.json plus the capture jsonl, no .tmp litter."""
    monkeypatch.chdir(tmp_path)  # capture files land under tmp, not the repo
    monkeypatch.setattr(props, "load_key", lambda: "test-key")
    monkeypatch.setattr(props, "active_sports", lambda k, s: {"baseball_mlb"})
    event = {"id": "ev9", "home_team": "H", "away_team": "A",
             "commence_time": "2026-08-06T23:00:00Z"}
    monkeypatch.setattr(props, "upcoming_events",
                        lambda sport, key, session, window, now: [event])
    prop = {"market": "batter_hits", "market_label": "Hits", "player": "P",
            "line": 1.5,
            "over": {"best_price": 100, "best_book": "A", "worst_price": -120,
                     "n_books": 3, "gain_pts": 4.5, "fair_price": -105,
                     "edge_vs_fair_pts": 1.0},
            "under": {"best_price": -105, "best_book": "B", "worst_price": -125,
                      "n_books": 3, "gain_pts": 4.4, "fair_price": -115,
                      "edge_vs_fair_pts": 0.5},
            "gain_pts": 4.5}
    monkeypatch.setattr(props, "_event_props",
                        lambda sport, ev, key, session, mk: ([prop], 3, 397))

    out_dir = tmp_path / "site-data"
    doc = props.collect(out_dir=out_dir)

    assert doc["credits_spent"] == 3
    assert doc["credits_remaining"] == 397
    on_disk = json.loads((out_dir / "props.json").read_text())
    assert on_disk["totals"] == {"events": 1, "props": 1, "max_gain_pts": 4.5}
    assert _no_tmp_left(out_dir)
    # capture: one jsonl line per prop, replayable json.
    # -live, because data/capture/mlb-props belongs to engine.props_capture and
    # holds a different row shape. One directory for two schemas is what let a
    # nested row win the representative slot in props_board and blank out a
    # prop's start time, which silently removed it from every rendered view.
    caps = list((tmp_path / "data" / "capture" / "mlb-props-live").glob("*.jsonl"))
    assert len(caps) == 1
    assert not (tmp_path / "data" / "capture" / "mlb-props").exists(), \
        "engine.props must not write into props_capture's directory"
    lines = caps[0].read_text().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event_id"] == "ev9"
    assert row["provenance"] == "own_capture"


def test_props_dry_run_writes_nothing(tmp_path, monkeypatch):
    _quiet_props(monkeypatch)
    doc = props.collect(out_dir=tmp_path / "never", dry_run=True)
    assert not (tmp_path / "never").exists()
    assert doc["boards"] == []


# ------------------------------------------------------ hitrates.find_player

def test_find_player_exact_match_returns_id():
    session = FakeSession({"people": [
        {"id": 101, "fullName": "Jose Ramirez Sr."},
        {"id": 202, "fullName": "José Ramírez"},
    ]})
    # accent-insensitive, case-insensitive exact match
    assert hitrates.find_player("Jose Ramirez", session) == 202


def test_find_player_ambiguous_duplicate_returns_none():
    # Two players normalise to the same name (the two-Luis-Garcias problem):
    # publishing the wrong record is worse than none, so refuse to pick.
    session = FakeSession({"people": [
        {"id": 1, "fullName": "Luis García"},
        {"id": 2, "fullName": "Luis Garcia"},
    ]})
    assert hitrates.find_player("Luis Garcia", session) is None


def test_find_player_no_match_returns_none():
    session = FakeSession({"people": [{"id": 7, "fullName": "Somebody Else"}]})
    assert hitrates.find_player("Luis Garcia", session) is None
    assert hitrates.find_player("Anyone", FakeSession({"people": []})) is None


def test_find_player_http_error_returns_none():
    session = FakeSession({}, status_code=500)
    assert hitrates.find_player("Luis Garcia", session) is None


# --------------------------------------------------------- hitrates.rate

def test_rate_counts_strict_overs():
    vals = [0.0, 1.0, 2.0, 2.0, 3.0]
    r = hitrates.rate(vals, 2.0)
    assert r == {"n": 5, "over": 1}          # a push (== line) is not an over


@pytest.mark.parametrize("line", [-0.5, 0.5, 1.5, 2.5, 10.0])
def test_rate_partition_property(line):
    vals = [0.0, 1.0, 1.0, 2.0, 3.0, 5.0]
    r = hitrates.rate(vals, line)
    assert r["n"] == len(vals)
    # overs + not-overs partition the sample exactly
    assert r["over"] + sum(1 for v in vals if v <= line) == len(vals)
    assert 0 <= r["over"] <= r["n"]


def test_rate_empty_values():
    assert hitrates.rate([], 1.5) == {"n": 0, "over": 0}


# -------------------------------------------------------- middles.collect

PREV_MIDDLES_DOC = {
    "generated_at": "2026-08-01T00:00:00+00:00",
    "window_hours": 36,
    "credits_spent": 4,
    "middles": [{"id": "m1", "home": "H", "away": "A",
                 "market": "total", "numbers": [45], "width": 2.0}],
    "totals": {"middles": 1},
}


def _quiet_middles(monkeypatch, rows=(), spent=0, live={"baseball_mlb"}):
    monkeypatch.setattr(middles, "load_key", lambda: "test-key")
    monkeypatch.setattr(middles, "active_sports", lambda k, s: set(live))
    monkeypatch.setattr(
        middles, "_one_sport",
        lambda sport, key, session, window, now: (list(rows), spent))


def test_middles_all_fetches_failed_keeps_previous(tmp_path, monkeypatch):
    """0 credits + 0 middles + live sports = API trouble: keep the old board."""
    _quiet_middles(monkeypatch)  # every fetch fails: 0 rows, 0 spent
    out = tmp_path / "middles.json"
    out.write_text(json.dumps(PREV_MIDDLES_DOC))

    doc = middles.collect(out_dir=tmp_path)

    assert doc["all_fetches_failed"] is True
    on_disk = json.loads(out.read_text())
    assert on_disk["middles"] == PREV_MIDDLES_DOC["middles"]
    assert on_disk["generated_at"] == PREV_MIDDLES_DOC["generated_at"]
    assert "checked_at" in on_disk
    datetime.fromisoformat(on_disk["checked_at"])
    assert _no_tmp_left(tmp_path)


def test_middles_empty_market_is_not_a_failure(tmp_path, monkeypatch):
    """Credits were spent and no middles exist: that is a real (empty) result,
    and it must replace the stale board rather than freeze it forever."""
    _quiet_middles(monkeypatch, rows=(), spent=2)
    out = tmp_path / "middles.json"
    out.write_text(json.dumps(PREV_MIDDLES_DOC))

    doc = middles.collect(out_dir=tmp_path)

    assert doc["all_fetches_failed"] is False
    on_disk = json.loads(out.read_text())
    assert on_disk["middles"] == []
    assert on_disk["generated_at"] == doc["generated_at"]
    assert _no_tmp_left(tmp_path)


def test_middles_no_live_sports_is_not_a_failure(tmp_path, monkeypatch):
    """Off-season everywhere: nothing fetched, but that is not API trouble."""
    _quiet_middles(monkeypatch, live=set())
    doc = middles.collect(out_dir=tmp_path)
    assert doc["all_fetches_failed"] is False
    on_disk = json.loads((tmp_path / "middles.json").read_text())
    assert on_disk["middles"] == []


def test_middles_failure_with_no_previous_file_still_writes(tmp_path,
                                                            monkeypatch):
    _quiet_middles(monkeypatch)
    doc = middles.collect(out_dir=tmp_path)
    assert doc["all_fetches_failed"] is True
    on_disk = json.loads((tmp_path / "middles.json").read_text())
    assert on_disk["middles"] == []
    assert on_disk["all_fetches_failed"] is True
    assert _no_tmp_left(tmp_path)


def test_middles_fresh_rows_written_and_tagged(tmp_path, monkeypatch):
    row = {"id": "e1", "home": "H", "away": "A",
           "starts": "2026-08-06T23:00:00Z", "market": "total",
           "low_label": "Over 44.5", "high_label": "Under 46.5",
           "low_line": 44.5, "low_price": -110, "low_book": "X",
           "high_line": 46.5, "high_price": -110, "high_book": "Y",
           "width": 2.0, "numbers": [45, 46]}
    _quiet_middles(monkeypatch, rows=[row], spent=2)

    doc = middles.collect(out_dir=tmp_path)

    assert doc["all_fetches_failed"] is False
    on_disk = json.loads((tmp_path / "middles.json").read_text())
    assert on_disk["totals"]["middles"] == 1
    m = on_disk["middles"][0]
    assert (m["sport"], m["label"]) == ("mlb", "MLB")  # tagged from SPORTS
    assert _no_tmp_left(tmp_path)


def test_middles_dry_run_writes_nothing(tmp_path, monkeypatch):
    _quiet_middles(monkeypatch)
    middles.collect(out_dir=tmp_path / "never", dry_run=True)
    assert not (tmp_path / "never").exists()
