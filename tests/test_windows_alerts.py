"""Tests for engine.middles._windows and engine.alerts drift/divergence.

All offline: _windows is pure math, and the alert finders are exercised on
synthetic own-capture rows built in-memory. No requests are made (the only
network-capable import in engine.middles is never triggered by _windows).
"""

from __future__ import annotations

import math

from engine.alerts import (
    DEFAULT_MIN_MOVE,
    _series,
    find_drift,
    find_divergence,
    implied,
)
from engine.middles import _windows

# ---------------------------------------------------------------------------
# helpers


def q(line: float, price: int = -110, book: str = "bookA") -> dict:
    """A quote as _windows expects it."""
    return {"line": line, "price": price, "book": book}


FUTURE_KICK = "2099-01-01T18:00:00Z"   # far future: never "already started"
PAST_KICK = "2020-01-01T18:00:00Z"     # long past: always started


def row(book: str, price: int, observed_at: str,
        line: float | None = 47.5, kickoff: str = FUTURE_KICK,
        selection: str = "Over", market: str = "totals",
        event_id: str = "ev1") -> dict:
    """A capture row as the alert finders expect it."""
    return {
        "event_id": event_id, "market": market, "selection": selection,
        "line": line, "book": book, "price": price,
        "observed_at": observed_at, "kickoff": kickoff,
        "sport": "nfl", "home": "Home", "away": "Away",
        "provenance": "own_capture",
    }


# ---------------------------------------------------------------------------
# _windows


class TestWindows:
    def test_positive_total_window(self):
        w = _windows([q(44.5)], [q(46.5, book="bookB")])
        assert w is not None
        assert w["numbers"] == [45, 46]
        assert w["low_line"] == 44.5 and w["high_line"] == 46.5
        assert w["width"] == 2.0
        assert w["low_book"] == "bookA" and w["high_book"] == "bookB"

    def test_negative_half_point_window(self):
        # -1.5 .. 1.5 must include -1, 0, 1 — int() truncation would lose -1.
        w = _windows([q(-1.5)], [q(1.5)])
        assert w is not None
        assert w["numbers"] == [-1, 0, 1]

    def test_all_negative_window(self):
        w = _windows([q(-3.5)], [q(-2.5)])
        assert w is not None
        assert w["numbers"] == [-3]

    def test_straddling_window(self):
        w = _windows([q(-1.5)], [q(2.5)])
        assert w is not None
        assert w["numbers"] == [-1, 0, 1, 2]

    def test_no_integer_inside_returns_none(self):
        # 2.5 .. 3.0: floor(2.5)+1 = 3, ceil(3.0) = 3, range(3, 3) is empty.
        assert _windows([q(2.5)], [q(3.0)]) is None

    def test_hi_at_or_below_lo_returns_none(self):
        assert _windows([q(46.5)], [q(44.5)]) is None
        assert _windows([q(44.5)], [q(44.5)]) is None

    def test_empty_sides_return_none(self):
        assert _windows([], [q(46.5)]) is None
        assert _windows([q(44.5)], []) is None

    def test_widest_window_chosen(self):
        # Lowest low-line and highest high-line define the window.
        w = _windows([q(45.5, book="x"), q(43.5, book="y")],
                     [q(46.5, book="z"), q(47.5, book="w")])
        assert w is not None
        assert w["low_line"] == 43.5 and w["low_book"] == "y"
        assert w["high_line"] == 47.5 and w["high_book"] == "w"
        assert w["numbers"] == [44, 45, 46, 47]

    def test_property_numbers_are_exactly_strict_interior_integers(self):
        # Over a grid of half-point and whole lines, numbers must equal every
        # integer strictly between the two lines, and None exactly when there
        # are none (or when the window is inverted/degenerate).
        grid = [x / 2.0 for x in range(-14, 15)]   # -7.0 .. 7.0 by 0.5
        for lo in grid:
            for hi in grid:
                w = _windows([q(lo)], [q(hi)])
                expected = [n for n in range(math.floor(lo) - 1,
                                             math.ceil(hi) + 2)
                            if lo < n < hi]
                if hi <= lo or not expected:
                    assert w is None, (lo, hi)
                else:
                    assert w is not None, (lo, hi)
                    assert w["numbers"] == expected, (lo, hi)
                    assert w["width"] == round(hi - lo, 1)


# ---------------------------------------------------------------------------
# alerts: _series identity


class TestSeries:
    def test_line_is_part_of_series_key(self):
        rows = [row("bookA", -105, "2026-01-01T00:00:00Z", line=47.5),
                row("bookA", -140, "2026-01-01T01:00:00Z", line=48.5)]
        series = _series(rows)
        assert len(series) == 2
        for key in series:
            assert len(key) == 5           # event, market, selection, line, book
        lines = {key[3] for key in series}
        assert lines == {"47.5", "48.5"}

    def test_series_sorted_by_observed_at(self):
        rows = [row("bookA", -120, "2026-01-01T02:00:00Z"),
                row("bookA", -110, "2026-01-01T00:00:00Z")]
        (obs,) = _series(rows).values()
        assert [r["price"] for r in obs] == [-110, -120]


# ---------------------------------------------------------------------------
# alerts: drift


class TestDrift:
    def test_no_drift_across_different_lines(self):
        # Same book re-posts at a new line: that is a line move, not a juice
        # move, and must not raise a drift alert however big the price gap.
        rows = [row("bookA", -105, "2026-01-01T00:00:00Z", line=47.5),
                row("bookA", -160, "2026-01-01T01:00:00Z", line=48.5)]
        assert find_drift(rows) == []

    def test_drift_fires_above_threshold_on_same_line(self):
        rows = [row("bookA", -110, "2026-01-01T00:00:00Z"),
                row("bookA", -140, "2026-01-01T01:00:00Z")]
        alerts = find_drift(rows)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "drift"
        assert a.book == "bookA"
        assert a.from_price == -110 and a.to_price == -140
        expected = (implied(-140) - implied(-110)) * 100
        assert expected >= DEFAULT_MIN_MOVE
        assert a.move_pts == round(expected, 2)
        assert a.move_pts > 0 and "shortened" in a.detail

    def test_drift_below_threshold_is_silent(self):
        # -110 -> -112 is ~0.45 pts of implied probability: a tick, not a move.
        rows = [row("bookA", -110, "2026-01-01T00:00:00Z"),
                row("bookA", -112, "2026-01-01T01:00:00Z")]
        gap = abs(implied(-112) - implied(-110)) * 100
        assert gap < DEFAULT_MIN_MOVE
        assert find_drift(rows) == []
        # The same pair fires once the caller lowers the threshold below it.
        assert len(find_drift(rows, min_move=gap / 2)) == 1

    def test_drift_out_is_negative_and_labelled(self):
        rows = [row("bookA", -140, "2026-01-01T00:00:00Z"),
                row("bookA", +110, "2026-01-01T01:00:00Z")]
        (a,) = find_drift(rows)
        assert a.move_pts < 0
        assert "drifted out" in a.detail

    def test_consecutive_steps_compared_not_endpoints(self):
        # Three observations, each step above threshold: two alerts, one per
        # consecutive pair.
        rows = [row("bookA", -110, "2026-01-01T00:00:00Z"),
                row("bookA", -140, "2026-01-01T01:00:00Z"),
                row("bookA", -170, "2026-01-01T02:00:00Z")]
        alerts = find_drift(rows)
        assert len(alerts) == 2
        pairs = {(a.from_price, a.to_price) for a in alerts}
        assert pairs == {(-110, -140), (-140, -170)}

    def test_different_books_never_compared(self):
        rows = [row("bookA", -110, "2026-01-01T00:00:00Z"),
                row("bookB", -180, "2026-01-01T01:00:00Z")]
        assert find_drift(rows) == []


# ---------------------------------------------------------------------------
# alerts: divergence


def _consensus_setup(outlier_price: int = +120, kickoff: str = FUTURE_KICK,
                     line: float = 47.5, n_consensus: int = 3,
                     outlier_observed: str = "2026-01-01T00:00:00Z") -> list[dict]:
    rows = [row(f"book{i}", -110, "2026-01-01T00:00:00Z",
                line=line, kickoff=kickoff) for i in range(n_consensus)]
    rows.append(row("outlier", outlier_price, outlier_observed,
                    line=line, kickoff=kickoff))
    return rows


class TestDivergence:
    def test_outlier_against_three_book_consensus(self):
        alerts = find_divergence(_consensus_setup())
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "divergence"
        assert a.book == "outlier"
        assert a.from_price is None and a.to_price == +120
        expected = (implied(-110) - implied(+120)) * 100   # median is -110
        assert a.move_pts == round(expected, 2)
        assert a.move_pts >= DEFAULT_MIN_MOVE

    def test_book_paying_less_than_consensus_never_alerts(self):
        # Divergence is one-sided: a worse-than-consensus price is not an
        # opportunity.
        alerts = find_divergence(_consensus_setup(outlier_price=-160))
        assert alerts == []

    def test_needs_three_books_at_same_line(self):
        # Two books at 47.5 plus two at 48.5: four books, but no line has the
        # three quotes a consensus requires.
        rows = [row("bookA", -110, "2026-01-01T00:00:00Z", line=47.5),
                row("outlier", +150, "2026-01-01T00:00:00Z", line=47.5),
                row("bookC", -110, "2026-01-01T00:00:00Z", line=48.5),
                row("bookD", -110, "2026-01-01T00:00:00Z", line=48.5)]
        assert find_divergence(rows) == []
        # Same books pooled onto one line do produce a consensus and an alert.
        pooled = [dict(r, line=47.5) for r in rows]
        assert len(find_divergence(pooled)) == 1

    def test_kickoff_passed_rows_excluded(self):
        assert find_divergence(_consensus_setup(kickoff=PAST_KICK)) == []

    def test_stale_quote_excluded_from_consensus(self):
        # Outlier last seen 8h before the freshest observation: dropped, and
        # the remaining three identical prices carry no divergence.
        rows = _consensus_setup(outlier_price=+150,
                                outlier_observed="2025-12-31T16:00:00Z")
        assert find_divergence(rows) == []

    def test_quote_within_seven_hours_still_counts(self):
        # 6h old is inside two capture cycles of the newest: still in play.
        rows = _consensus_setup(outlier_price=+150,
                                outlier_observed="2025-12-31T18:00:00Z")
        alerts = find_divergence(rows)
        assert len(alerts) == 1
        assert alerts[0].book == "outlier"

    def test_latest_observation_per_book_wins(self):
        # The outlier later re-priced back to the consensus: no alert, the
        # earlier outlying price is history, not a current quote.
        rows = _consensus_setup(outlier_price=+150)
        rows.append(row("outlier", -110, "2026-01-01T02:00:00Z"))
        assert find_divergence(rows) == []


# ---------------------------------------------------------------------------
# implied() sanity


class TestImplied:
    def test_even_money_both_signs(self):
        assert implied(+100) == 0.5
        assert implied(-100) == 0.5

    def test_known_values(self):
        assert math.isclose(implied(-110), 110 / 210)
        assert math.isclose(implied(+120), 100 / 220)

    def test_monotonic_in_price(self):
        # Shorter (more negative / less positive) prices imply more probability.
        prices = [+300, +150, +100, -110, -150, -300]
        probs = [implied(p) for p in prices]
        assert probs == sorted(probs)
