"""Odds math: engine/lines.py conversion + de-vig, engine/props.py grouping.

Deterministic and offline. The props test drives _event_props through a fake
requests.Session so the real parsing/grouping/fair-price code runs on a
hand-built API payload without any network.
"""

from __future__ import annotations

import pytest

from engine.lines import implied, to_american, _fair_prices
from engine import props as props_mod
from engine.props import _event_props, MIN_BOOKS


# ---------------------------------------------------------------- implied()

class TestImplied:
    def test_boundary_plus_minus_100_both_half(self):
        # +100 and -100 are the same coin flip written two ways.
        assert implied(100) == pytest.approx(0.5)
        assert implied(-100) == pytest.approx(0.5)

    def test_negative_positive_symmetry_sums_to_one(self):
        # implied(-x) + implied(+x) = x/(x+100) + 100/(x+100) = 1 exactly.
        for x in (100, 105, 110, 150, 200, 350, 900, 10000):
            assert implied(-x) + implied(x) == pytest.approx(1.0)

    def test_range_open_interval(self):
        # Any valid American price maps strictly inside (0, 1).
        for price in (-100000, -500, -110, -100, 100, 110, 500, 100000):
            p = implied(price)
            assert 0.0 < p < 1.0

    def test_monotone_decreasing_in_price(self):
        # Bigger favorite (more negative) -> higher probability; bigger
        # underdog payout -> lower probability. -100 and +100 tie at 0.5.
        prices = [-1000, -300, -110, -100, 100, 110, 300, 1000]
        probs = [implied(p) for p in prices]
        for a, b in zip(probs, probs[1:]):
            assert a >= b
        # Strictly decreasing once the ±100 tie is skipped.
        assert probs[3] == probs[4]
        strict = probs[:4] + probs[5:]
        for a, b in zip(strict, strict[1:]):
            assert a > b

    def test_known_juice_pair(self):
        # -110 both sides: each side implies 110/210, overround ~4.76%.
        assert implied(-110) == pytest.approx(110 / 210)
        assert implied(-110) + implied(-110) > 1.0


# ------------------------------------------------------------- to_american()

class TestToAmerican:
    def test_half_is_plus_100(self):
        # prob == 0.5 takes the underdog branch -> +100, not -100.
        assert to_american(0.5) == 100

    def test_rejects_out_of_range(self):
        for bad in (0.0, 1.0, -0.2, 1.5):
            with pytest.raises(ValueError):
                to_american(bad)

    def test_favorites_negative_underdogs_positive(self):
        assert to_american(0.7) < 0
        assert to_american(0.3) > 0
        # Magnitude at least 100 in both directions (valid American odds).
        for p in (0.01, 0.3, 0.499, 0.5, 0.501, 0.7, 0.99):
            assert abs(to_american(p)) >= 100

    def test_round_trip_with_implied_within_rounding(self):
        # implied(to_american(p)) recovers p up to integer-rounding of the
        # American price. Near ±100 the price grid is coarsest: one price
        # step moves the probability by <0.0025, so half a step is <0.00125.
        for i in range(1, 100):
            p = i / 100.0
            back = implied(to_american(p))
            assert back == pytest.approx(p, abs=0.005)

    def test_round_trip_symmetry(self):
        # p and 1-p convert to mirrored prices (sign flip, same magnitude)
        # away from the 0.5 boundary.
        for p in (0.2, 0.35, 0.42, 0.6, 0.75, 0.9):
            assert to_american(p) == -to_american(1.0 - p) or \
                abs(abs(to_american(p)) - abs(to_american(1.0 - p))) <= 1


# ------------------------------------------------------------ _fair_prices()

def _q(*prices):
    return [{"book": f"b{i}", "price": p} for i, p in enumerate(prices)]


class TestFairPrices:
    def test_sides_sum_to_one(self):
        fair = _fair_prices({"Home": _q(-110, -115, -105),
                             "Away": _q(-110, -105, -120)})
        assert sum(fair.values()) == pytest.approx(1.0)
        assert set(fair) == {"Home", "Away"}
        for p in fair.values():
            assert 0.0 < p < 1.0

    def test_vig_removed_is_positive_for_real_book_pair(self):
        # Standard -110/-110 market: raw implied sums to ~1.0476. The
        # normalisation must strip that overround, so each fair prob is
        # strictly below its raw implied and the stripped vig is positive.
        quotes = {"Over": _q(-110, -110, -110), "Under": _q(-110, -110, -110)}
        raw_sum = implied(-110) * 2
        fair = _fair_prices(quotes)
        vig = raw_sum - sum(fair.values())
        assert vig > 0
        assert vig == pytest.approx(raw_sum - 1.0)
        for side in fair:
            assert fair[side] < implied(-110)
        # Symmetric market de-vigs to a coin flip.
        assert fair["Over"] == pytest.approx(0.5)
        assert fair["Under"] == pytest.approx(0.5)

    def test_median_robust_to_one_outlier(self):
        # One stale/fat-fingered +900 quote must not move the consensus.
        clean = {"Home": _q(-110, -110, -110), "Away": _q(-110, -110, -110)}
        dirty = {"Home": _q(-110, -110, -110, 900),
                 "Away": _q(-110, -110, -110)}
        f_clean = _fair_prices(clean)
        f_dirty = _fair_prices(dirty)
        assert f_dirty["Home"] == pytest.approx(f_clean["Home"])
        assert f_dirty["Away"] == pytest.approx(f_clean["Away"])
        # A mean-based consensus WOULD have moved: prove the outlier bites.
        mean_home = (3 * implied(-110) + implied(900)) / 4
        assert mean_home != pytest.approx(implied(-110))

    def test_empty_and_all_empty_sides(self):
        assert _fair_prices({}) == {}
        # Sides with no quotes are dropped, not divided by zero.
        fair = _fair_prices({"Home": _q(-120), "Away": []})
        assert set(fair) == {"Home"}
        assert fair["Home"] == pytest.approx(1.0)


# ------------------------------------------- props._event_props via fake API

class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


class _FakeSession:
    """Stands in for requests.Session; records calls, never touches network."""

    def __init__(self, payload, status_code=200, headers=None):
        self._resp = _FakeResponse(payload, status_code, headers)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return self._resp


def _outcome(side, player, line, price):
    return {"name": side, "description": player, "point": line, "price": price}


def _payload():
    """Minimal API event-odds payload exercising every grouping rule."""
    def book(key, outcomes, mkey="player_pass_yds"):
        return {"key": key, "markets": [{"key": mkey, "outcomes": outcomes}]}

    return {
        "id": "ev1",
        "bookmakers": [
            # Alpha 250.5: three books both sides -> published.
            # Gamma 4.5: three books both sides, wider spread -> published,
            #   and must sort ABOVE Alpha (bigger gain_pts).
            book("draftkings", [
                _outcome("Over", "Alpha QB", 250.5, -110),
                _outcome("Under", "Alpha QB", 250.5, -110),
                _outcome("Over", "Gamma WR", 4.5, -105),
                _outcome("Under", "Gamma WR", 4.5, -125),
            ]),
            book("fanduel", [
                _outcome("Over", "Alpha QB", 250.5, -115),
                _outcome("Under", "Alpha QB", 250.5, -105),
                _outcome("Over", "Gamma WR", 4.5, -150),
                _outcome("Under", "Gamma WR", 4.5, 120),
            ]),
            book("betmgm", [
                _outcome("Over", "Alpha QB", 250.5, -105),
                _outcome("Under", "Alpha QB", 250.5, -120),
                _outcome("Over", "Gamma WR", 4.5, -120),
                _outcome("Under", "Gamma WR", 4.5, -110),
                # Different line for Alpha -> its own group, only 1 book:
                # must be dropped by the MIN_BOOKS gate, not merged.
                _outcome("Over", "Alpha QB", 260.5, 100),
                _outcome("Under", "Alpha QB", 260.5, -130),
                # Malformed outcomes: no point / no price / bad side.
                _outcome("Over", "NoLine TE", None, -110),
                {"name": "Over", "description": "NoPrice RB", "point": 10.5},
                _outcome("Yes", "WrongSide K", 1.5, -110),
            ]),
            # Market not requested -> ignored entirely.
            book("bovada",
                 [_outcome("Over", "Alpha QB", 250.5, -200)],
                 mkey="player_rush_yds"),
        ],
    }


LABELS = {"player_pass_yds": "Passing yards"}
HEADERS = {"x-requests-last": "3", "x-requests-remaining": "17"}


class TestEventProps:
    def _run(self):
        session = _FakeSession(_payload(), headers=HEADERS)
        props, spent, remaining = _event_props(
            "americanfootball_nfl", {"id": "ev1"}, "test-key",
            session, LABELS)
        return props, spent, remaining, session

    def test_grouping_and_min_books_gate(self):
        props, _, _, _ = self._run()
        published = {(p["player"], p["line"]) for p in props}
        assert published == {("Alpha QB", 250.5), ("Gamma WR", 4.5)}
        for p in props:
            assert p["over"]["n_books"] >= MIN_BOOKS
            assert p["under"]["n_books"] >= MIN_BOOKS
            assert p["market_label"] == "Passing yards"

    def test_credits_headers_and_request_shape(self):
        props, spent, remaining, session = self._run()
        assert spent == 3
        assert remaining == 17
        assert len(session.calls) == 1
        params = session.calls[0]["params"]
        assert params["markets"] == "player_pass_yds"
        assert params["oddsFormat"] == "american"

    def test_fair_math_properties(self):
        props, _, _, _ = self._run()
        for p in props:
            for side in ("over", "under"):
                s = p[side]
                # Best price for a bettor = lowest implied probability.
                assert implied(s["best_price"]) <= implied(s["worst_price"])
                assert s["gain_pts"] >= 0
                assert s["gain_pts"] == pytest.approx(
                    (implied(s["worst_price"]) - implied(s["best_price"])) * 100,
                    abs=0.01)
            # De-vigged sides reconstruct a ~fair market: implied probs of
            # the two fair prices sum to 1 up to to_american rounding.
            total = implied(p["over"]["fair_price"]) \
                + implied(p["under"]["fair_price"])
            assert total == pytest.approx(1.0, abs=0.01)

    def test_alpha_symmetric_market_devigs_to_coinflip(self):
        props, _, _, _ = self._run()
        alpha = next(p for p in props if p["player"] == "Alpha QB")
        # Both sides median at -110 -> fair prob 0.5 -> fair price +100.
        assert alpha["over"]["fair_price"] == 100
        assert alpha["under"]["fair_price"] == 100
        assert alpha["over"]["best_price"] == -105
        assert alpha["over"]["best_book"] == "BetMGM"
        # Edge vs fair = 0.5 - implied(-105), in points.
        assert alpha["over"]["edge_vs_fair_pts"] == pytest.approx(
            (0.5 - implied(-105)) * 100, abs=0.01)

    def test_sorted_by_gain_desc(self):
        props, _, _, _ = self._run()
        gains = [p["gain_pts"] for p in props]
        assert gains == sorted(gains, reverse=True)
        # Gamma's book spread is wider by construction, so it leads.
        assert props[0]["player"] == "Gamma WR"

    def test_non_200_returns_empty_but_keeps_headers(self):
        session = _FakeSession({}, status_code=429, headers=HEADERS)
        props, spent, remaining = _event_props(
            "americanfootball_nfl", {"id": "ev1"}, "k", session, LABELS)
        assert props == []
        assert spent == 3
        assert remaining == 17

    def test_module_wiring(self):
        # _event_props must share the exact same odds math as the game board.
        assert props_mod.implied is implied
        assert props_mod.to_american is to_american
