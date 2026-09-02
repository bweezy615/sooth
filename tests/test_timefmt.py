"""The no-pad date formats must survive being made portable.

engine/timefmt.py exists because `%-d` and `%-I` are glibc extensions: they
work in the ubuntu workflows that mail subscribers and raise
`ValueError: Invalid format string` on the Windows machine sooth is developed
on. The obvious one-character fix is to drop `%-d` to `%d` — and that silently
changes "Sep 9" to "Sep 09" in an email whose earlier copies have already been
delivered, so the archive and the new sends would disagree about the same
kickoff.

These pin the rendered strings. A future "simplification" that pads a number
fails here rather than in someone's inbox.
"""
from __future__ import annotations

from datetime import datetime

from engine.alert_lifecycle import _when
from engine.timefmt import _NO_PAD, strftime


def test_the_seal_email_stamp_is_unpadded():
    """The exact format engine/alert_lifecycle.py mails."""
    d = datetime(2026, 9, 9, 20, 20)
    assert strftime(d, "%a %b %-d, %H:%M UTC") == "Wed Sep 9, 20:20 UTC"
    assert "Sep 09" not in strftime(d, "%a %b %-d, %H:%M UTC")
    # two digits are untouched - no-pad is not "strip a character"
    assert (strftime(datetime(2026, 9, 10, 0, 20), "%a %b %-d, %H:%M UTC")
            == "Thu Sep 10, 00:20 UTC")
    # ...and %H stays padded in the same string
    assert strftime(datetime(2026, 9, 9, 5, 5), "%-d %H:%M") == "9 05:05"


def test_when_renders_the_real_kickoff_through_the_public_helper():
    """_when is what the subscriber actually sees."""
    assert _when("2026-09-10T00:20:00+00:00") == "Thu Sep 10, 00:20 UTC"
    assert _when("2026-09-09T20:20:00+00:00") == "Wed Sep 9, 20:20 UTC"
    assert _when("not a date") == "not a date"      # never blank


def test_twelve_hour_is_a_clock_not_a_stripped_zero():
    """%-I is the card clock. Midnight and noon are 12, not 0."""
    for hour, want in ((0, "12:20AM"), (12, "12:20PM"), (13, "1:20PM"),
                       (9, "9:20AM"), (23, "11:20PM")):
        got = strftime(datetime(2026, 9, 10, hour, 20), "%-I:%M%p").upper()
        assert got == want, f"hour {hour} rendered {got}, expected {want}"


def test_every_no_pad_directive_drops_the_leading_zero():
    d = datetime(2005, 1, 2, 3, 4, 5)          # single digit in every field
    for key in _NO_PAD:
        got = strftime(d, f"%-{key}")
        assert not got.startswith("0"), f"%-{key} rendered padded: {got}"
        assert got == got.lstrip("0") or got == "0"
    assert strftime(d, "%-d/%-m/%-y") == "2/1/5"
    assert strftime(d, "%-H:%-M:%-S") == "3:4:5"
    assert strftime(d, "%-I%p").upper() == "3AM"


def test_a_literal_percent_is_not_a_directive():
    d = datetime(2026, 9, 9, 20, 20)
    assert strftime(d, "100%% sure on %-d") == "100% sure on 9"
    assert strftime(d, "trailing %") == "trailing %"
