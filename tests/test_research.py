"""Tests for the matchup researcher.

Two rules carry this module and both have already been got wrong once:

1. **Two sides of one bet must group together, two different lines must not.**
   A spread is written from both ends (-3.5 / +3.5); a total is written once
   (46.5 / 46.5). Grouping on the raw number files each spread side alone and
   reports "no market". Grouping too loosely pairs 46.5 with 47.5 and invents a
   juice move — the defect fixed in 196f720.

2. **One book is not a market.** With a single price, best-minus-fair is that
   book's hold. Publishing it as a shopping edge would invert the sign of the
   only claim this site makes.
"""

from __future__ import annotations

from engine.alerts import _series
from engine.research import (_line_group, build_facts, movement, price_block,
                             upcoming_events)

FUTURE = "2099-01-01T00:00:00+00:00"


def obs(book, price, at, sel="side_a", market="spread", line=-3.5, event="E1"):
    return {"event_id": event, "sport": "nfl", "market": market,
            "selection": sel, "book": book, "price": price, "line": line,
            "observed_at": at, "home": "Seattle Seahawks",
            "away": "New England Patriots", "kickoff": FUTURE,
            "season": 2026, "week": 1, "provenance": "own_capture"}


class TestLineGrouping:
    def test_spread_sides_pair(self):
        assert _line_group("spread", "-3.5") == _line_group("spread", "3.5")

    def test_different_spreads_stay_apart(self):
        assert _line_group("spread", "-3.5") != _line_group("spread", "-4.5")

    def test_totals_are_not_folded_by_sign(self):
        # A total never goes negative, so abs() must not touch it; 46.5 and
        # 47.5 are different bets and must never share a series.
        assert _line_group("total", "46.5") != _line_group("total", "47.5")

    def test_moneyline_has_no_line(self):
        assert _line_group("moneyline", "None") == "None"

    def test_spread_market_is_priced(self):
        """The 47-of-48 regression: both sides present, one market found."""
        rows = [obs("DraftKings", -110, "2026-08-20T10:00:00+00:00"),
                obs("DraftKings", -110, "2026-08-20T10:00:00+00:00",
                    sel="side_b", line=3.5)]
        blk = price_block(_series(rows), "E1", "spread")
        assert blk is not None
        assert set(blk["sides"]) == {"side_a", "side_b"}
        # Quoted from the home side, the way a spread is written.
        assert blk["line"] == -3.5
        assert blk["sides"]["side_a"]["label"] == "home"

    def test_one_sided_market_is_not_priced(self):
        rows = [obs("DraftKings", -110, "2026-08-20T10:00:00+00:00")]
        assert price_block(_series(rows), "E1", "spread") is None


class TestSingleBookHonesty:
    def _one_book(self):
        rows = [obs("DraftKings", -110, "2026-08-20T10:00:00+00:00"),
                obs("DraftKings", -110, "2026-08-20T10:00:00+00:00",
                    sel="side_b", line=3.5)]
        return price_block(_series(rows), "E1", "spread")

    def test_no_gain_is_claimed_from_one_price(self):
        blk = self._one_book()
        assert blk["shoppable"] is False
        assert all(s["gain_pts"] is None for s in blk["sides"].values())

    def test_the_hold_is_reported_instead(self):
        blk = self._one_book()
        assert blk["vig_pts"] > 0                     # -110/-110 is ~4.76 pts
        assert blk["fair_basis"] == "single book, margin removed"

    def test_two_books_produce_a_real_gap(self):
        rows = [obs("DraftKings", -110, "2026-08-20T10:00:00+00:00"),
                obs("FanDuel", -105, "2026-08-20T10:00:00+00:00"),
                obs("DraftKings", -110, "2026-08-20T10:00:00+00:00",
                    sel="side_b", line=3.5),
                obs("FanDuel", -115, "2026-08-20T10:00:00+00:00",
                    sel="side_b", line=3.5)]
        blk = price_block(_series(rows), "E1", "spread")
        assert blk["shoppable"] is True
        assert blk["sides"]["side_a"]["best_price"] == -105   # the better number
        assert blk["sides"]["side_a"]["best_book"] == "FanDuel"
        assert blk["sides"]["side_a"]["gain_pts"] is not None

    def test_facts_do_not_advertise_an_edge_on_one_book(self):
        """One book: no price fact at all. The thin-market state is carried
        once, at report level (the ``market`` field) and as a single page
        notice — not restated as a bullet on all 48 cards, which read as
        advertising for the one book that happened to post."""
        blk = self._one_book()
        facts = build_facts(
            {"home": "Seattle Seahawks", "away": "New England Patriots"},
            {}, {}, {"spread": blk}, {}, {})
        kinds = {f["kind"] for f in facts}
        assert "price_gap" not in kinds
        assert "dispersion" not in kinds


class TestReportHygiene:
    def test_started_games_are_dropped(self):
        past = [dict(obs("DraftKings", -110, "2026-08-20T10:00:00+00:00"),
                     kickoff="2020-01-01T00:00:00+00:00")]
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        assert upcoming_events(past, now) == {}

    def test_movement_needs_two_observations(self):
        rows = [obs("DraftKings", -110, "2026-08-20T10:00:00+00:00"),
                obs("DraftKings", -110, "2026-08-20T10:00:00+00:00",
                    sel="side_b", line=3.5)]
        assert movement(_series(rows), "E1", "spread") is None

    def test_movement_never_mixes_two_lines(self):
        """A line move must start a new series, not read as a price move."""
        rows = [obs("DraftKings", -110, "2026-08-20T10:00:00+00:00"),
                obs("DraftKings", -110, "2026-08-20T10:00:00+00:00",
                    sel="side_b", line=3.5),
                obs("DraftKings", -110, "2026-08-20T11:00:00+00:00"),
                obs("DraftKings", -110, "2026-08-20T11:00:00+00:00",
                    sel="side_b", line=3.5),
                # The number moved. These rows belong to a different bet.
                obs("DraftKings", -160, "2026-08-20T12:00:00+00:00", line=-6.5),
                obs("DraftKings", +140, "2026-08-20T12:00:00+00:00",
                    sel="side_b", line=6.5)]
        mv = movement(_series(rows), "E1", "spread")
        assert mv["line"] == -3.5                     # the dominant line wins
        # -160 belongs to the 6.5 series and must not appear on this chart.
        assert all(abs(p["side_a"] - 52.38) < 0.01 for p in mv["points"])
