"""Tests for the props aggregator that feeds props.json.

Three failure modes, each of which would publish a false number:
  - reading a stale price instead of the newest per (prop, book),
  - picking the wrong side's "best" price (a worse payout shown as best),
  - de-vig that doesn't strip the margin (fair sides not summing to 1).
"""

from __future__ import annotations

from engine.props_board import build_props, implied_prob


def obs(book, sel, price, at, line=6.5, player="Tarik Skubal",
        event="E1", market="pitcher_strikeouts"):
    return {"event_id": event, "sport": "mlb", "market": market,
            "selection": sel, "book": book, "price": price, "line": line,
            "observed_at": at, "home": "DET", "away": "CLE",
            "commence_time": "2026-08-08T23:10:00Z", "player": player,
            "provenance": "own_capture"}


def _find(props, side):
    return next(p for p in props if p["side"] == side)


def test_newest_price_wins():
    # same book, two snapshots — the later observed_at is the one that counts
    rows = [
        obs("fanduel", "over", -120, "2026-08-08T22:00:00Z"),
        obs("fanduel", "over", +100, "2026-08-08T22:30:00Z"),  # newer
        obs("draftkings", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    over = _find(build_props(rows), "Over")
    assert over["best_price"] == 100  # the +100, not the stale -120


def test_best_price_is_best_payout():
    rows = [
        obs("fanduel", "over", -115, "2026-08-08T22:30:00Z"),
        obs("draftkings", "over", -105, "2026-08-08T22:30:00Z"),  # better
        obs("betmgm", "over", -130, "2026-08-08T22:30:00Z"),
        obs("fanduel", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    over = _find(build_props(rows), "Over")
    assert over["best_price"] == -105
    assert over["best_book"] == "draftkings"


def test_devig_sides_sum_to_one():
    rows = [
        obs("fanduel", "over", -110, "2026-08-08T22:30:00Z"),
        obs("fanduel", "under", -110, "2026-08-08T22:30:00Z"),
    ]
    props = build_props(rows)
    total = _find(props, "Over")["fair_prob"] + _find(props, "Under")["fair_prob"]
    assert abs(total - 1.0) < 1e-6  # margin stripped


def test_empty_is_empty_not_error():
    assert build_props([]) == []


def test_implied_prob_signs():
    assert abs(implied_prob(100) - 0.5) < 1e-9
    assert abs(implied_prob(-110) - 110 / 210) < 1e-9
