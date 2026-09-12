"""Spread and total shopping on the board.

College football is why this exists. The sport's defining feature is the
mismatch — on 2026-09-03 the live board carried Miami at Stanford priced
-3000/+1500 — and a moneyline is not how anyone bets those games. A CFB board
without a spread is a board about the wrong market, so football buys all three
markets and the other sports stay on moneyline.

The two edges a line market carries are kept apart on purpose. Price shopping
at a fixed number is a strictly better version of the same bet. Buying a
better NUMBER is a different bet, and blending the two would assert a
cross-line equivalence nothing here has measured.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import engine.lines as lines
from engine.lines import (DEFAULT_MARKETS, LINE_MARKETS, _consensus_line,
                          _line_market, markets_for)

NOW = datetime(2026, 9, 3, 18, 0, tzinfo=timezone.utc)
KICK = "2026-09-05T01:00:00Z"


def q(book: str, line: float, price: int) -> dict:
    return {"book": book, "line": line, "price": price}


# --------------------------------------------------------------- consensus

def test_the_consensus_line_is_the_mode_not_the_median():
    """A median can name a number no book offers.

    Four books split evenly between -7 and -7.5 have a median of -7.25. No one
    can bet -7.25. The mode is always a real, shoppable number.
    """
    quotes = [q("draftkings", -7.0, -110), q("fanduel", -7.0, -105),
              q("betmgm", -7.5, -110), q("bovada", -7.5, -115)]
    assert _consensus_line(quotes) == -7.0

    quotes = [q("draftkings", -7.0, -110), q("fanduel", -7.5, -110), q("betmgm", -7.5, -105)]
    assert _consensus_line(quotes) == -7.5


def test_no_quotes_has_no_consensus():
    assert _consensus_line([]) is None


# ------------------------------------------------------------ spread shape

def _spread(home_quotes, away_quotes, home="Stanford", away="Miami"):
    return _line_market("spread", {home: home_quotes, away: away_quotes},
                        {home: True, away: True})


def test_the_two_spread_sides_describe_the_same_bet():
    """Home -7 must pair with away +7, never with away +7.5.

    Deriving each side's consensus independently would publish two different
    markets as one, and the de-vig across them would be meaningless.
    """
    m = _spread(
        [q("draftkings", -7.0, -110), q("fanduel", -7.0, -105), q("betmgm", -7.5, -110)],
        [q("draftkings", 7.0, -110), q("fanduel", 7.0, -115), q("betmgm", 7.5, -110)])
    assert m["consensus_line"] == -7.0
    home, away = m["sides"]
    assert home["line"] == -7.0
    assert away["line"] == 7.0, "away side must mirror the home number"


def test_price_shopping_at_the_consensus_line_picks_the_least_juice():
    m = _spread(
        [q("draftkings", -7.0, -110), q("fanduel", -7.0, -102), q("bovada", -7.0, -120)],
        [q("draftkings", 7.0, -110), q("fanduel", 7.0, -110)])
    home = m["sides"][0]
    assert home["best_price"] == -102 and home["best_book"] == "FanDuel"
    assert home["worst_price"] == -120 and home["worst_book"] == "Bovada"
    assert home["n_books"] == 3, "only the three books ON the number count"
    assert home["gain_pts"] > 0


def test_a_book_off_the_consensus_number_is_reported_separately():
    """The better number is a different bet, so it is its own field."""
    m = _spread(
        [q("draftkings", -7.0, -110), q("fanduel", -7.0, -110), q("betmgm", -6.5, -110)],
        [q("draftkings", 7.0, -110), q("fanduel", 7.0, -110), q("betmgm", 7.5, -110)])
    home, away = m["sides"]
    assert home["line"] == -7.0
    assert home["best_line"] == -6.5, "-6.5 is the friendlier number to lay"
    assert home["best_line_book"] == "BetMGM"
    assert home["off_consensus"] is True
    assert away["best_line"] == 7.5, "+7.5 is the friendlier number to take"
    assert away["off_consensus"] is True
    # The quotes AT the consensus number exclude the off-consensus book.
    assert all(x["line"] == -7.0 for x in home["quotes"])


def test_no_better_number_available_is_flagged_false():
    m = _spread([q("draftkings", -7.0, -110), q("fanduel", -7.0, -108)],
                [q("draftkings", 7.0, -110), q("fanduel", 7.0, -112)])
    assert m["sides"][0]["off_consensus"] is False
    assert m["sides"][0]["best_line"] == -7.0


def test_the_fair_price_is_devigged_across_the_two_sides():
    """Raw implied probabilities sum to more than 1; the excess is the vig."""
    m = _spread([q("draftkings", -7.0, -110), q("fanduel", -7.0, -110)],
                [q("draftkings", 7.0, -110), q("fanduel", 7.0, -110)])
    probs = [s["fair_prob"] for s in m["sides"]]
    assert abs(sum(probs) - 1.0) < 1e-9, "de-vigged sides must sum to 1"
    assert all(abs(p - 0.5) < 1e-9 for p in probs), (
        "a -110/-110 market is a coin flip once the vig is removed")


# ------------------------------------------------------------- total shape

def _total(over, under):
    return _line_market("total", {"Over": over, "Under": under},
                        {"Over": False, "Under": True})


def test_over_wants_a_lower_number_and_under_wants_a_higher_one():
    """The two sides of a total prefer opposite directions.

    A spread's sides both want a bigger number on their own axis, so a shared
    direction would have passed the spread tests and still been wrong here.
    """
    m = _total(
        [q("draftkings", 52.5, -110), q("fanduel", 52.5, -110), q("betmgm", 51.5, -110)],
        [q("draftkings", 52.5, -110), q("fanduel", 52.5, -110), q("betmgm", 53.5, -110)])
    over, under = m["sides"]
    assert m["consensus_line"] == 52.5
    assert over["best_line"] == 51.5, "Over wants the lowest number"
    assert under["best_line"] == 53.5, "Under wants the highest number"
    assert under["line"] == 52.5, "both sides of a total quote one number"


def test_a_one_sided_line_market_is_dropped():
    """Half a market cannot be de-vigged and must not reach the board."""
    assert _spread([q("draftkings", -7.0, -110)], []) is None
    assert _total([], [q("draftkings", 52.5, -110)]) is None


def test_a_market_with_no_book_on_the_consensus_pair_is_dropped():
    """Both sides must have quotes at the paired number, not just exist."""
    m = _spread([q("draftkings", -7.0, -110), q("fanduel", -7.0, -110)],
                [q("betmgm", 8.5, -110)])
    assert m is None, "away has no quote at +7.0, so there is no shared bet"


# ------------------------------------------------- per-sport market config

def test_football_buys_line_markets_and_the_rest_do_not():
    assert markets_for(lines.SPORTS["americanfootball_ncaaf"]) == LINE_MARKETS
    assert markets_for(lines.SPORTS["americanfootball_nfl"]) == LINE_MARKETS
    assert markets_for(lines.SPORTS["baseball_mlb"]) == DEFAULT_MARKETS
    assert markets_for({}) == DEFAULT_MARKETS, "absent key means moneyline"


# ------------------------------------------------------- end to end parsing

def _payload(markets: list[dict]) -> list[dict]:
    return [{
        "id": "cfb1", "commence_time": KICK,
        "home_team": "Stanford", "away_team": "Miami",
        "bookmakers": markets,
    }]


def _book(key: str, h2h: tuple[int, int], spread: tuple[float, int, int] | None,
          total: tuple[float, int, int] | None) -> dict:
    ms = [{"key": "h2h", "outcomes": [
        {"name": "Stanford", "price": h2h[0]},
        {"name": "Miami", "price": h2h[1]}]}]
    if spread:
        ln, hp, ap = spread
        ms.append({"key": "spreads", "outcomes": [
            {"name": "Stanford", "price": hp, "point": ln},
            {"name": "Miami", "price": ap, "point": -ln}]})
    if total:
        ln, op, up = total
        ms.append({"key": "totals", "outcomes": [
            {"name": "Over", "price": op, "point": ln},
            {"name": "Under", "price": up, "point": ln}]})
    return {"key": key, "markets": ms}


class _Resp:
    status_code = 200
    headers: dict = {}

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self._payload = payload
        self.params = None

    def get(self, url, params=None, timeout=None):
        self.params = params
        return _Resp(self._payload)


def _run(payload, markets=LINE_MARKETS):
    sess = _Session(payload)
    events, _, _ = lines._one_sport(
        "americanfootball_ncaaf", "k", sess, timedelta(hours=36), NOW, markets)
    return events, sess


def test_a_football_event_carries_moneyline_spread_and_total():
    payload = _payload([
        _book("draftkings", (1400, -3200), (14.5, -110, -110), (52.5, -110, -110)),
        _book("fanduel", (1400, -4000), (14.5, -105, -115), (52.5, -108, -112)),
        _book("betmgm", (1500, -3000), (13.5, -110, -110), (51.5, -110, -110)),
    ])
    events, sess = _run(payload)
    assert sess.params["markets"] == "h2h,spreads,totals"
    assert len(events) == 1
    ev = events[0]

    # The published moneyline contract is untouched.
    assert {s["name"] for s in ev["sides"]} == {"Stanford", "Miami"}
    assert ev["sides"][0]["best_price"] is not None

    kinds = {m["market"]: m for m in ev["markets"]}
    assert set(kinds) == {"spread", "total"}
    assert kinds["spread"]["consensus_line"] == 14.5
    assert kinds["total"]["consensus_line"] == 52.5

    home = kinds["spread"]["sides"][0]
    assert home["name"] == "Stanford" and home["line"] == 14.5
    assert home["best_price"] == -105, "FanDuel is the cheapest at +14.5"
    assert home["best_line"] == 14.5, "no book offers Stanford more than +14.5"

    away = kinds["spread"]["sides"][1]
    assert away["name"] == "Miami" and away["line"] == -14.5
    assert away["best_line"] == -13.5, "BetMGM lays the shorter number"
    assert away["off_consensus"] is True


def test_a_moneyline_only_sport_publishes_no_markets_key():
    """Absent, not empty: readers must not have to distinguish the two."""
    payload = _payload([
        _book("draftkings", (150, -170), None, None),
        _book("fanduel", (155, -175), None, None),
    ])
    events, sess = _run(payload, DEFAULT_MARKETS)
    assert sess.params["markets"] == "h2h"
    assert "markets" not in events[0]
    assert events[0]["sides"], "the moneyline board still builds"


def test_a_book_quoting_only_a_moneyline_does_not_break_the_line_markets():
    """Real payloads have books missing a market. They must be skipped, not
    counted as a quote at a null number."""
    payload = _payload([
        _book("draftkings", (1400, -3200), (14.5, -110, -110), None),
        _book("fanduel", (1400, -4000), (14.5, -105, -115), (52.5, -108, -112)),
        _book("bovada", (1300, -2800), None, (52.5, -110, -110)),
    ])
    events, _ = _run(payload)
    kinds = {m["market"]: m for m in events[0]["markets"]}
    assert kinds["spread"]["sides"][0]["n_books"] == 2
    assert kinds["total"]["sides"][0]["n_books"] == 2
