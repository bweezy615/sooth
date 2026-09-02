"""strftime without the directives only glibc understands.

`%-d`, `%-I` and their siblings mean "this number, no leading zero". They are a
GNU extension: they work on Linux and MSVC's strftime rejects the whole format
string, raising `ValueError: Invalid format string`. Two live paths used them —
the subscriber emails in alert_lifecycle.py and the card clock in xcards.py —
so those modules ran fine in the ubuntu workflows that mail people and could
not run at all on the Windows machine sooth is developed on. The runbook
command `python -m engine.alert_lifecycle --selfcheck` had never once executed
here, and tests/test_alert_lifecycle.py said so in its docstring.

This expands those directives itself and hands every other directive to the
platform's strftime, so the OUTPUT DOES NOT CHANGE — on Linux it is what glibc
already produced, and Windows now produces the same bytes. That property is the
whole point. The tempting one-character "fix" is to drop `%-d` to `%d`, which
silently turns "Sep 9" into "Sep 09" in mail that has already gone out;
tests/test_timefmt.py pins the output so that cannot happen quietly.

    strftime(d, "%a %b %-d, %H:%M UTC")  ->  "Wed Sep 9, 20:20 UTC"
"""

from __future__ import annotations

from datetime import datetime

# Every no-pad directive glibc supports, and what it actually means. %-I is not
# %-H with the zero stripped: it is the 12-hour clock, on which midnight and
# noon are both 12, so it gets its own rule rather than inheriting one.
_NO_PAD = {
    "d": lambda d: d.day,
    "m": lambda d: d.month,
    "H": lambda d: d.hour,
    "I": lambda d: d.hour % 12 or 12,
    "j": lambda d: d.timetuple().tm_yday,
    "M": lambda d: d.minute,
    "S": lambda d: d.second,
    "y": lambda d: d.year % 100,
}


def strftime(d: datetime, fmt: str) -> str:
    """Format `d`, expanding %-X ourselves and delegating the rest."""
    out: list[str] = []
    i = 0
    while i < len(fmt):
        if fmt[i] != "%" or i + 1 >= len(fmt):
            out.append(fmt[i])
            i += 1
        elif fmt[i + 1] == "-" and fmt[i + 2:i + 3] and fmt[i + 2] in _NO_PAD:
            out.append(str(_NO_PAD[fmt[i + 2]](d)))
            i += 3
        else:
            # Includes %% -> "%", which must not be mistaken for a directive.
            out.append(d.strftime(fmt[i:i + 2]))
            i += 2
    return "".join(out)
