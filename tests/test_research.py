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

import json
from pathlib import Path

from engine.alerts import _series
from engine.research import (_line_group, build_facts, price_block,
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



class TestPublishedPayload:
    """What ships in site/public/data/research.json.

    Every visitor to /research and /game downloads and parses this file whole.
    """

    PATH = Path(__file__).resolve().parents[1] / "site/public/data/research.json"

    def _reports(self):
        return json.loads(self.PATH.read_text(encoding="utf-8"))["reports"]

    def test_movement_carries_only_line_history(self):
        """The consensus point series does not come back.

        It was 46% of the payload — 40 hourly points per market, each point
        re-keyed by the full team name — and no code on the site read it. The
        only subscripts of `movement` anywhere are `{market}_line`. The series
        itself is published by engine/timeline.py, for more events and in a
        tighter encoding, and both pages that fetch research.json already fetch
        timeline.json beside it. Size is the symptom; publishing a second copy
        of something nobody reads is the defect.
        """
        stray = sorted({k for r in self._reports()
                        for k in (r.get("movement") or {})
                        if not k.endswith("_line")})
        assert not stray, (
            f"research.json is publishing movement series nothing reads: "
            f"{stray}. See docs/plans/research-payload-size.md."
        )

    def test_the_fields_the_pages_read_are_still_there(self):
        """The other half of the same change: nothing the UI reads was cut."""
        for r in self._reports():
            for k in ("event_id", "home", "away", "kickoff", "season", "week",
                      "records", "stats", "injuries", "odds", "facts",
                      "movement"):
                assert k in r, f"report {r.get('event_id')} lost {k}"
            assert "n_out" in r["injuries"]["home"]
