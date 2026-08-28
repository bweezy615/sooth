"""Which games reach the board when a season is opening.

`engine.lines._choose` decides what a sport contributes to board.json. It used
to be all-or-nothing: one game inside the 36h window suppressed the look-ahead
entirely. That is invisible for a sport in mid-season and wrong exactly at a
season opening, where the first game to come inside the window is the only one.

Measured on 2026-08-28, the eve of college football week 1: the API listed the
whole slate, one game (UNC at TCU) was 33 hours out, and the board published
one college football game with the sport rail reading "CFB 1". The previous
day, with nothing in window, it had published eight.
"""

from __future__ import annotations

from engine.lines import LOOKAHEAD_EVENTS, _choose


def ev(name: str, starts: str, in_window: bool) -> dict:
    return {"id": name, "starts": starts, "in_window": in_window}


def test_a_lone_in_window_game_no_longer_hides_the_slate():
    """The college-football-week-1 case, which is why this file exists."""
    games = [ev("unc-tcu", "2026-08-29T16:00:00Z", True)] + [
        ev(f"sat-{i}", f"2026-08-29T{18 + i:02d}:00:00Z", False) for i in range(20)
    ]
    chosen = _choose(games)
    assert len(chosen) == LOOKAHEAD_EVENTS, (
        f"one in-window game left the board with {len(chosen)} of a 21-game slate")
    assert chosen[0]["id"] == "unc-tcu", "the in-window game must come first"
    assert chosen[0]["upcoming"] is False
    assert all(e["upcoming"] for e in chosen[1:]), (
        "a topped-up game must be flagged upcoming, or the page presents a "
        "game days away as tonight's")


def test_a_full_in_window_slate_is_not_truncated():
    """Mid-season must be untouched: every live game reaches the board."""
    games = [ev(f"g{i}", f"2026-08-28T{i:02d}:00:00Z", True) for i in range(13)]
    chosen = _choose(games)
    assert len(chosen) == 13
    assert not any(e["upcoming"] for e in chosen)


def test_an_out_of_season_sport_still_shows_the_soonest_few():
    """The behaviour the look-ahead was added for, unchanged."""
    games = [ev(f"g{i}", f"2026-10-{i + 1:02d}T00:00:00Z", False) for i in range(20)]
    chosen = _choose(games)
    assert len(chosen) == LOOKAHEAD_EVENTS
    assert [e["id"] for e in chosen] == [f"g{i}" for i in range(LOOKAHEAD_EVENTS)], (
        "the look-ahead must take the SOONEST games, not the first listed")
    assert all(e["upcoming"] for e in chosen)


def test_the_scratch_flag_never_reaches_the_payload():
    """in_window is internal. Leaking it would publish a second, staler answer
    to the same question the card's kickoff time already answers."""
    games = [ev("a", "2026-08-29T16:00:00Z", True),
             ev("b", "2026-09-05T16:00:00Z", False)]
    _choose(games)
    assert all("in_window" not in e for e in games)
