"""Tests for the props aggregator that feeds props.json.

The failure modes each publish a false number:
  - reading a stale price instead of the newest per (prop, book),
  - picking the wrong side's "best" price (a worse payout shown as best),
  - de-vig that doesn't strip the margin (fair sides not summing to 1),
  - and — the bug this shape fixes — splitting a prop's two sides apart so the
    grid, which renders Over and Under on one row, can't reassemble them.
"""

from __future__ import annotations

from datetime import datetime, timezone

from engine.props_board import (
    build_document, build_props, fair_american, implied_prob, market_label,
)


def obs(book, sel, price, at, line=6.5, player="Tarik Skubal",
        event="E1", market="pitcher_strikeouts"):
    return {"event_id": event, "sport": "mlb", "market": market,
            "selection": sel, "book": book, "price": price, "line": line,
            "observed_at": at, "home": "DET", "away": "CLE",
            "commence_time": "2026-08-08T23:10:00Z", "player": player,
            "provenance": "own_capture"}


def _one(props):
    assert len(props) == 1, props
    return props[0]


def test_newest_price_wins():
    # same book, two snapshots — the later observed_at is the one that counts
    rows = [
        obs("fanduel", "over", -120, "2026-08-08T22:00:00Z"),
        obs("fanduel", "over", +100, "2026-08-08T22:30:00Z"),  # newer
        obs("draftkings", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    assert _one(build_props(rows))["over"]["best_price"] == 100  # +100, not stale -120


def test_best_price_is_best_payout():
    rows = [
        obs("fanduel", "over", -115, "2026-08-08T22:30:00Z"),
        obs("draftkings", "over", -105, "2026-08-08T22:30:00Z"),  # better
        obs("betmgm", "over", -130, "2026-08-08T22:30:00Z"),
        obs("fanduel", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    over = _one(build_props(rows))["over"]
    assert over["best_price"] == -105
    # props_board canonicalises on read, so historical rows captured before
    # props_capture did the same still resolve to one spelling per operator.
    assert over["best_book"] == "DraftKings"
    assert over["n_books"] == 3  # all three over quotes counted


def test_devig_sides_sum_to_one():
    rows = [
        obs("fanduel", "over", -110, "2026-08-08T22:30:00Z"),
        obs("fanduel", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    p = _one(build_props(rows))
    assert abs(p["over"]["fair_prob"] + p["under"]["fair_prob"] - 1.0) < 1e-6


def test_sides_stay_together_and_labelled():
    # the regression this whole change fixes: one pivoted prop, both sides on it,
    # a human market label, and a prop-level gain the grid sorts on.
    rows = [
        obs("fanduel", "over", -110, "2026-08-08T22:30:00Z"),
        obs("draftkings", "under", -105, "2026-08-08T22:30:00Z"),
    ]
    p = _one(build_props(rows))
    assert p["over"] and p["under"]
    assert p["market_label"] == "Strikeouts"
    assert isinstance(p["over"]["fair_price"], int)
    assert p["gain_pts"] == max(p["over"]["edge_vs_fair_pts"],
                                p["under"]["edge_vs_fair_pts"])


def test_document_is_nested_boards_events_props():
    rows = [
        obs("fanduel", "over", -110, "2026-08-08T22:30:00Z"),
        obs("fanduel", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    doc = build_document(rows)
    assert doc["n_props"] == 1
    board = doc["boards"][0]
    assert board["label"] == "MLB" and board["n_props"] == 1
    ev = board["events"][0]
    assert ev["home"] == "DET" and ev["away"] == "CLE"
    assert ev["props"][0]["player"] == "Tarik Skubal"


def test_empty_document_has_no_boards():
    doc = build_document([])
    assert doc["boards"] == [] and doc["n_props"] == 0


def test_empty_is_empty_not_error():
    assert build_props([]) == []


def test_window_drops_finished_games():
    # a game that started a day ago must not linger on the grid
    now = datetime(2026, 8, 8, 23, 0, tzinfo=timezone.utc)
    def pair(player, ct):  # both sides, so the prop survives the both-priced rule
        return [obs("fanduel", "over", -110, ct, player=player, event=player),
                obs("fanduel", "under", -110, ct, player=player, event=player)]
    stale = [dict(r, commence_time="2026-08-07T20:00:00Z")     # ~27h before now
             for r in pair("Old Guy", "2026-08-07T20:00:00Z")]
    live = [dict(r, commence_time="2026-08-08T23:30:00Z")      # 30 min ahead
            for r in pair("Live Guy", "2026-08-08T23:30:00Z")]
    players = {p["player"] for p in build_props(stale + live, now=now)}
    assert players == {"Live Guy"}


def test_no_now_means_no_filter():
    old = [dict(r, commence_time="2020-01-01T00:00:00Z") for r in (
        obs("fanduel", "over", -110, "2020-01-01T00:00:00Z"),
        obs("fanduel", "under", -110, "2020-01-01T00:00:00Z"))]
    assert build_props(old) != []


def test_implied_prob_signs():
    assert abs(implied_prob(100) - 0.5) < 1e-9
    assert abs(implied_prob(-110) - 110 / 210) < 1e-9


def test_fair_american_and_label_helpers():
    assert fair_american(0.5) == -100
    assert fair_american(0.8) == -400      # heavy favourite prices negative
    assert fair_american(0.2) == 400       # longshot prices positive
    assert market_label("batter_hits") == "Batter Hits"  # unknown market prettifies


# ------------------------------------------------------- props_model thresholds

def test_over_threshold_treats_a_whole_line_as_pushable():
    """ceil() is right for half lines and wrong for whole ones.

    At 6.0 a six-strikeout start is a push — stake back, not a win — so the
    over needs 7. Counting it as a win inflated p_over, and p_over is half of
    the delta the page prints as our model against the market.
    """
    from engine.props_model import over_threshold

    assert over_threshold(5.5) == 6
    assert over_threshold(6.5) == 7
    assert over_threshold(6.0) == 7      # was 6: a push scored as an over
    assert over_threshold(4.0) == 5
