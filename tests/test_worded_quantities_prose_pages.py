"""/methodology and /disclaimers may not carry a worded quantity nobody has
reviewed.

test_props_model_note.py built this guard for /props-model after "four fifths
of the effect disappears" sat there unreviewed and wrong
(docs/plans/2026-09-03-four-fifths.md). It never covered these two pages
because the fraction pattern false-positived on "a third party" — both pages
use that phrase, meaning an outside company, several times. That match is now
excluded in tests/_worded_quantities.py (a "third party" is never followed by
"party"/"parties" the way an actual fraction is). This file is what covering
these two pages with the fixed pattern looks like.

Every phrase below was read against the page it comes from on 2026-09-07 and
is either a self-contained count (the reader can check it against the section
immediately around it) or checked here against the generated figures it
describes. Nothing here says a phrase is right forever — it says a human has
looked at it and written down why it was right on the day it was reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests._worded_quantities import visible_text, worded_quantities

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "site/content/_figures.json"
METHODOLOGY = ROOT / "site/public/methodology.html"
DISCLAIMERS = ROOT / "site/public/disclaimers.html"

REVIEWED_METHODOLOGY = {
    "two things": "the 'What we claim' section is a numbered list of exactly "
                  "two claims",
    "two evaluations": "sections A and B immediately below are the two "
                       "evaluations named",
    "five this": "'one game in five' — checked against the live-rate figures "
                 "below",
    "four of": "'Four of ten seasons are losing seasons' — checked against "
              "selectivity.evaluation_a.by_season below",
    "ten seasons": "the ten-season backtest window; matches both 'Four of ten "
                   "seasons' and 'Ten seasons of out-of-sample results' — "
                   "checked against by_season below",
    "four point": "'the four-point bar' is the shipped selection threshold, "
                  "already pinned by test_the_edge_bar_is_spelled_the_same_"
                  "way_in_the_copy in test_figures_published.py",
    "two line": "'the two line sources' — nflverse and the real consensus "
               "close, both named in the sentences around it",
    "ten probability": "the calibration bins — checked against "
                       "engine.calibrate.expected_calibration_error's default "
                       "below",
    "two honest": "exactly two notes follow, marked 'First' and 'Second'",
    "two facts": "refers back to the two gap figures named in the immediately "
                "preceding sentence",
    "four hashes": "log2(16) for the 16-game NFL Week 1 slate this sentence "
                   "names explicitly",
    "four sports": "college football, MLB, NBA and NHL — named by name in "
                   "the same sentence",
}

REVIEWED_DISCLAIMERS = {
    "nine disclosures": "this page's own numbered sections run 1 through 9",
    "seven days": "'24 hours a day, seven days a week' — the stated hours of "
                 "an external hotline, not a measurement of anything Sooth "
                 "does",
}


def test_no_worded_quantities_left_in_methodology():
    html = METHODOLOGY.read_text(encoding="utf-8")
    text = visible_text(html, '<div class="prose">', "<script")
    unreviewed = sorted(set(worded_quantities(text).values())
                        - set(REVIEWED_METHODOLOGY))
    assert not unreviewed, (
        f"worded quantities in /methodology prose that nobody has reviewed: "
        f"{unreviewed}. Add each to REVIEWED_METHODOLOGY here with the reason "
        f"it may stay, or fix the prose. Spelling a figure out is not a way "
        f"around the digit test.")


def test_no_worded_quantities_left_in_disclaimers():
    html = DISCLAIMERS.read_text(encoding="utf-8")
    text = visible_text(html, '<div class="prose">', "<script")
    unreviewed = sorted(set(worded_quantities(text).values())
                        - set(REVIEWED_DISCLAIMERS))
    assert not unreviewed, (
        f"worded quantities in /disclaimers prose that nobody has reviewed: "
        f"{unreviewed}. Add each to REVIEWED_DISCLAIMERS here with the reason "
        f"it may stay, or fix the prose.")


def test_the_methodology_worded_quantities_that_track_a_figure_still_match():
    """Four of the reviewed /methodology phrases describe a figure. If a
    rerun moves one of these, the prose that spells it out goes stale
    silently — which is the entire failure this file exists to prevent."""
    fig = json.loads(CONTENT.read_text(encoding="utf-8"))
    sel = fig["selectivity"]["evaluation_a"]

    by_season = sel["by_season"]
    assert len(by_season) == 10, (
        "the page says 'Four of ten seasons are losing seasons' and 'Ten "
        f"seasons of out-of-sample results' but by_season now has "
        f"{len(by_season)} seasons")
    losing = sum(1 for s in by_season.values() if s["pct"] < 0.5)
    assert losing == 4, (
        "the page says 'Four of ten seasons are losing seasons' but "
        f"{losing} of them now have pct < 0.5")

    live_per_season = sel["live"]["per_season"]
    all_per_season = sel["thresholds"][0]["all"]["per_season"]
    ratio = live_per_season / all_per_season
    assert round(1 / ratio) == 5, (
        "the page says the shipped bar plays 'one game in five' but "
        f"live.per_season / thresholds[0].all.per_season is now {ratio:.3f} "
        f"(1 in {1 / ratio:.1f})")

    from engine.calibrate import expected_calibration_error
    assert expected_calibration_error.__defaults__[0] == 10, (
        "the page says ECE is measured 'across ten probability bands' but "
        "engine.calibrate.expected_calibration_error's default bin count "
        "has changed")
