"""Shared worded-quantity detector for the site's honesty guards.

A number spelled in words is still a published number. "Four fifths of the
effect disappears" sat on /props-model unguarded for six days and was wrong on
the day it was written — see docs/plans/2026-09-03-four-fifths.md. This module
is the regex list that catches that, imported by every page-specific guard so
it is defined once rather than copied and left to drift between pages.
"""

from __future__ import annotations

import re

_N = r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen)"
_FRAC = (r"(?:halves|half|thirds?|quarters?|fifths?|sixths?|sevenths?"
         r"|eighths?|ninths?|tenths?)")
WORDED_PATTERNS = [
    # four fifths, a third -- but not "a third party" or "a third-party X",
    # where "third party" names an outside company, not a fraction. Found
    # live on /methodology and /disclaimers, both of which use the phrase
    # this way several times.
    rf"\b(?:a|one|{_N})[\s-]{_FRAC}\b(?!\s*-?\s*part(?:y|ies)\b)",
    r"\b(?:half|most|nearly all|almost all)\s+of\b",  # half of, most of
    rf"\b(?:a|one|{_N})\s+(?:in|out\s+of)\s+(?:every|{_N})\b",  # three in five
    r"\b(?:twice|thrice|doubles?|doubled|triples?|tripled|quadrupled"
    r"|tenfold|orders?\s+of\s+magnitude)\b",          # multipliers
    rf"\b{_N}\b\W{{0,3}}\w+",                         # eleven-point, five more
]


def worded_quantities(text: str) -> dict[int, str]:
    """Every worded quantity in the prose, keyed by position in the text,
    valued by its normalised phrase (the matched words lowercased, with
    punctuation collapsed to single spaces)."""
    out: dict[int, str] = {}
    for pattern in WORDED_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            phrase = re.sub(r"\W+", " ", m.group(0).strip().lower()).strip()
            out.setdefault(m.start(), phrase)
    return out


def visible_text(html: str, start_marker: str, end_marker: str) -> str:
    """The reader-visible prose between two markers, markup stripped.

    Drops HTML comments and any element carrying data-f/data-was (the
    generator's own figure markup, already covered by the digit test) before
    collapsing tags and whitespace.
    """
    body = html.split(start_marker, 1)[1].split(end_marker, 1)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<(\w+)\b[^>]*\bdata-(?:f=\"[^\"]+\"|was)[^>]*>.*?</\1>",
                  " ", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
