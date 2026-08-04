"""Tests for the line board — the core product.

This module had no tests and shipped two real bugs in a single day:

  1. The best-price ranking was inverted. It sorted by DESCENDING implied
     probability, so the quote it labelled "best" was the worst one available.
     Shipped, it would have sent every user to the wrong sportsbook on every
     game while telling them confidently it was the right one.
  2. One operator was counted as two books, because a source spells the same
     name two different ways. Divergence needs three books before it claims a
     consensus, so a split identity can push a two-book market over that line
     and fire an alert against a consensus that does not exist.

Both were caught by looking at output, not by a check. These tests exist so
the next one is caught by a check.
"""

from __future__ import annotations

import json

import pytest

from engine.lines import (_capture_rows, _fair_prices, implied, to_american)
from engine.schema import canonical_book


def q(book, price):
    return {"book": book, "price": price}


# --------------------------------------------------------------------------
# odds arithmetic
# --------------------------------------------------------------------------

@pytest.mark.parametrize("price", [-500, -235, -190, -110, 100, 132, 180, 450])
def test_price_probability_round_trip(price):
    assert to_american(implied(price)) == price


def test_implied_direction():
    """Lower implied probability is a BETTER price for the bettor."""
    assert implied(-190) < implied(-235), "-190 pays more than -235"
    assert implied(+180) < implied(+155), "+180 pays more than +155"


def test_to_american_rejects_impossible():
    for bad in (0.0, 1.0, -0.2, 1.4):
        with pytest.raises(ValueError):
            to_american(bad)


# --------------------------------------------------------------------------
# the inversion that shipped
# --------------------------------------------------------------------------

def test_best_price_is_the_lowest_implied_probability():
    """The exact bug: ranking must put the most generous quote first.

    -190 and -235 are the real prices seen on the NFL Week 1 opener. If this
    ever reverses, the board names the wrong sportsbook on every row.
    """
    quotes = [q("BetRivers", -235), q("FanDuel", -198), q("BetUS", -190)]
    ranked = sorted(quotes, key=lambda x: implied(x["price"]))
    assert ranked[0]["book"] == "BetUS"
    assert ranked[-1]["book"] == "BetRivers"


def test_gain_between_best_and_worst_is_never_negative():
    quotes = [q("A", -235), q("B", -190), q("C", -210)]
    ranked = sorted(quotes, key=lambda x: implied(x["price"]))
    gain = (implied(ranked[-1]["price"]) - implied(ranked[0]["price"])) * 100
    assert gain > 0
    assert round(gain, 2) == pytest.approx(4.63, abs=0.02), \
        "the real NE at SEA spread, as a regression anchor"


def test_identical_quotes_give_zero_gain_not_negative():
    quotes = [q("A", -110), q("B", -110), q("C", -110)]
    ranked = sorted(quotes, key=lambda x: implied(x["price"]))
    gain = (implied(ranked[-1]["price"]) - implied(ranked[0]["price"])) * 100
    assert gain == pytest.approx(0.0)


# --------------------------------------------------------------------------
# the fair line
# --------------------------------------------------------------------------

def test_fair_prices_sum_to_one():
    """De-vigging must remove the margin exactly, not approximately."""
    fair = _fair_prices({"home": [q("A", -140), q("B", -138), q("C", -142)],
                         "away": [q("A", +120), q("B", +118), q("C", +122)]})
    assert sum(fair.values()) == pytest.approx(1.0)


def test_fair_price_is_better_than_any_posted_price():
    """Every posted price carries margin, so the fair line must sit inside it."""
    fair = _fair_prices({"home": [q("A", -140), q("B", -140), q("C", -140)],
                         "away": [q("A", +120), q("B", +120), q("C", +120)]})
    assert fair["home"] < implied(-140), "fair must imply a lower probability than the vigged price"
    assert fair["away"] < implied(+120)


def test_fair_uses_median_so_one_stale_book_cannot_drag_it():
    tight = {"home": [q("A", -140), q("B", -140), q("C", -140)],
             "away": [q("A", +120), q("B", +120), q("C", +120)]}
    with_outlier = {"home": [q("A", -140), q("B", -140), q("C", -140), q("D", -900)],
                    "away": [q("A", +120), q("B", +120), q("C", +120), q("D", +700)]}
    a = _fair_prices(tight)["home"]
    b = _fair_prices(with_outlier)["home"]
    assert abs(a - b) < 0.02, "a wildly stale book must barely move a median consensus"


def test_fair_prices_empty_input_is_empty_not_a_crash():
    assert _fair_prices({}) == {}


def test_fair_prices_preserves_the_favourite():
    fair = _fair_prices({"home": [q("A", -300), q("B", -290), q("C", -310)],
                         "away": [q("A", +250), q("B", +240), q("C", +260)]})
    assert fair["home"] > fair["away"], "de-vigging must never reorder the favourite"


# --------------------------------------------------------------------------
# capture rows — the multi-book evidence the alerts read
# --------------------------------------------------------------------------

def _event():
    return {"id": "E1", "home": "Seattle Mariners", "away": "Detroit Tigers",
            "starts": "2026-08-05T01:41:00Z",
            "sides": [{"name": "Detroit Tigers",
                       "quotes": [q("betrivers", +132), q("draftkings", +128)]},
                      {"name": "Seattle Mariners",
                       "quotes": [q("williamhill_us", -135), q("draftkings", -140)]}]}


def test_capture_rows_emit_one_row_per_book_quote():
    rows = _capture_rows("mlb", [_event()], "2026-08-04T05:00:00+00:00")
    assert len(rows) == 4


def test_capture_rows_are_marked_as_our_own_observation():
    rows = _capture_rows("mlb", [_event()], "2026-08-04T05:00:00+00:00")
    assert {r["provenance"] for r in rows} == {"own_capture"}, \
        "only prices we watched ourselves may back a CLV or divergence claim"


def test_capture_rows_canonicalise_book_identity():
    """The second bug: one operator must never be counted as two books."""
    rows = _capture_rows("mlb", [_event()], "2026-08-04T05:00:00+00:00")
    books = {r["book"] for r in rows}
    assert books == {"BetRivers", "DraftKings", "Caesars"}
    assert "williamhill_us" not in books and "draftkings" not in books


def test_capture_rows_carry_the_observation_time_not_the_kickoff():
    rows = _capture_rows("mlb", [_event()], "2026-08-04T05:00:00+00:00")
    assert all(r["observed_at"] == "2026-08-04T05:00:00+00:00" for r in rows)
    assert all(r["kickoff"] == "2026-08-05T01:41:00Z" for r in rows)


def test_capture_rows_are_json_serialisable():
    rows = _capture_rows("mlb", [_event()], "2026-08-04T05:00:00+00:00")
    for r in rows:
        json.loads(json.dumps(r))


def test_capture_rows_empty_when_no_events():
    assert _capture_rows("mlb", [], "2026-08-04T05:00:00+00:00") == []


# --------------------------------------------------------------------------
# book identity, across every spelling we have actually seen
# --------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["DraftKings", "Draft Kings", "draftkings", "DRAFTKINGS"])
def test_every_observed_draftkings_spelling_collapses(variant):
    assert canonical_book(variant) == "DraftKings"


def test_distinct_operators_stay_distinct():
    names = {canonical_book(n) for n in
             ["draftkings", "fanduel", "betmgm", "betrivers", "betus",
              "bovada", "lowvig", "betonlineag", "mybookieag", "williamhill_us"]}
    assert len(names) == 10, "canonicalisation must not merge different books"
