"""/props-model may not carry a number the evidence on disk cannot produce.

This is the page that publishes our prop model failing, and until 2026-08-28
all ~44 of its figures were typed in by hand from an analysis that no longer
existed. The checks below keep that from happening again:

  - every figure the page displays is present in the payload, character for
    character, so a hand edit to either one fails;
  - the payload can be rebuilt from committed inputs alone, offline, and comes
    out the same, so the generator cannot rot underneath the page;
  - the conclusion the page argues still follows from the payload;
  - the pinned analysis window has not been left behind by the capture;
  - no bare number is left loose in the page's prose.

(2) is why data/mlb/pitching_logs_2026.json is committed rather than fetched.
A test that hits statsapi.mlb.com would fail on a plane, and worse, would let
the reader's ability to reproduce the page depend on a third party still
serving 2026 game logs.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from scripts.props_model_note import (CAPTURE, STALE_AFTER_DAYS,
                                      WINDOW_THROUGH, build, page_figures)

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site/public/props-model.html"
PAYLOAD = ROOT / "site/public/data/props_model_note.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shown() -> dict:
    return page_figures(PAGE.read_text(encoding="utf-8"))


def test_page_uses_figures(shown):
    """A page with no data-f elements would pass every other check here."""
    assert len(shown) > 30, f"only {len(shown)} figures marked up — did a rewrite drop them?"


def test_every_displayed_figure_matches_the_payload(shown, payload):
    figures = payload["figures"]
    wrong = {k: (v, figures.get(k)) for k, v in shown.items() if figures.get(k) != v}
    assert not wrong, (
        "page and payload disagree; run `python scripts/props_model_note.py "
        f"--render`: {wrong}")


def test_payload_rebuilds_from_committed_evidence(payload):
    """The whole claim of the page: clone the repo and get the same numbers.

    Compares the display strings rather than the raw floats, because those are
    what the reader sees and they absorb the last digit of float noise.
    """
    fresh = build()
    assert fresh["figures"] == payload["figures"], (
        "regenerating from data/capture + data/mlb no longer reproduces the "
        "published figures — run `python scripts/props_model_note.py --render` "
        "and read the diff before shipping it, the change is the finding")


def test_the_conclusion_still_holds(payload):
    """Guard the claim the page makes, not just the arithmetic behind it.

    The page says the model has no measurable edge on real board props. If a
    rerun ever contradicted that, the page's argument would need rewriting and
    a silently-updated number would hide it.
    """
    d = payload["detail"]
    assert d["board"]["won_pct"] < 0.5238, (
        "the model now clears the ATS-style breakeven on board props — that is "
        "a rewrite of this page, not a figure refresh")
    lo = d["board"]["slope"] - 1.96 * d["board"]["slope_se"]
    hi = d["board"]["slope"] + 1.96 * d["board"]["slope_se"]
    assert lo < 0 < hi, (
        "the board-population information figure is now distinguishable from "
        "zero; the page's conclusion depends on it not being")


def test_the_pinned_window_has_not_quietly_gone_stale():
    """A closed experiment is fine. A closed experiment nobody reopens is not.

    scripts.props_model_note pins the population to WINDOW_THROUGH so that the
    capture cron cannot change a published figure behind our backs. The cost is
    that evidence piles up outside the window unnoticed, which is how the CLV
    disclaimer went 22 days stale. This is the alarm on that: once the capture
    has run a month past the pinned date, extending the window (or explicitly
    re-pinning it) becomes a job rather than a preference.
    """
    captured = sorted(f.stem for f in CAPTURE.glob("*.jsonl"))
    assert captured, "no prop capture on disk at all"
    newest = date.fromisoformat(captured[-1])
    behind = (newest - date.fromisoformat(WINDOW_THROUGH)).days
    assert behind <= STALE_AFTER_DAYS, (
        f"/props-model is pinned to {WINDOW_THROUGH} but capture now reaches "
        f"{newest}, {behind} days later. Rerun "
        f"`python scripts/props_model_note.py --fetch --through {newest} "
        "--render`, read what moved, and publish the move — or re-pin "
        "WINDOW_THROUGH deliberately and say why.")


def test_no_hand_typed_numbers_left_in_the_prose():
    """Any digit in the visible copy must be generated or explicitly superseded.

    Years, percentages and sample sizes are exactly what went stale here
    before. A number is allowed in three ways and no others: inside a data-f
    element (written by the generator), inside a data-was element (a figure
    this page used to publish, quoted in the correction record and frozen for
    good), or on the short list below of constants that are not measurements.
    """
    html = PAGE.read_text(encoding="utf-8")
    body = html.split("<main", 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    # drop the rendered figures and the quoted superseded ones, then all markup
    body = re.sub(r"<(\w+)\b[^>]*\bdata-(?:f=\"[^\"]+\"|was)[^>]*>.*?</\1>",
                  " ", body, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", body)

    allowed = {
        "1.0", "0",          # the explanation of what the slope means
        "1", "2", "3",       # the numbered list of withdrawn explanations
        "5", "10",           # "last five, last ten" — a description of /props
        "2026",              # the date of the analysis and of the correction
        "28", "110",         # 28 August 2026; standard -110 pricing
        "50%",               # the definition of a coin flip
        "95%",               # the definition of the interval quoted
    }
    found = set(re.findall(r"\d+(?:[.,]\d+)*%?", text))
    leftover = sorted(found - allowed)
    assert not leftover, (
        f"bare numbers in /props-model prose: {leftover} — wire them to "
        "scripts/props_model_note.py or spell them out")


# --- worded quantities -----------------------------------------------------
# The digit test above matches \d, and its own failure message says "or spell
# them out". So it did: "four fifths of the effect disappears" sat on this page
# from 2026-08-28, unguarded, and wrong on the day it was written — 60.5% on
# the reading the table three lines above it invites, 57% today. Six days live
# on the page that argues hardest for our honesty. See
# docs/plans/2026-09-03-four-fifths.md.
#
# So: the same allowlist discipline the digit test uses, applied to quantities
# spelled in words. A phrase is allowed only if it is on the reviewed list
# below WITH a reason. Anything new fails until a human reads it.

_N = (r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen)")
_FRAC = (r"(?:halves|half|thirds?|quarters?|fifths?|sixths?|sevenths?"
         r"|eighths?|ninths?|tenths?)")
_WORDED = [
    rf"\b(?:a|one|{_N})[\s-]{_FRAC}\b",              # four fifths, a third
    r"\b(?:half|most|nearly all|almost all)\s+of\b",  # half of, most of
    rf"\b(?:a|one|{_N})\s+(?:in|out\s+of)\s+(?:every|{_N})\b",  # three in five
    r"\b(?:twice|thrice|doubles?|doubled|triples?|tripled|quadrupled"
    r"|tenfold|orders?\s+of\s+magnitude)\b",          # multipliers
    rf"\b{_N}\b\W{{0,3}}\w+",                         # eleven-point, five more
]

# phrase -> why a human decided it may stay. Keys are the matched words plus
# the word after them, lowercased, punctuation collapsed to single spaces.
REVIEWED_WORDED_QUANTITIES = {
    # counts of things on this page. A reader checks them by reading it.
    "three explanations": "the page's own THREE EXPLANATIONS WE GOT WRONG "
                          "section carries exactly three",
    "three are": "'these three are summaries' — the same three",
    "two things": "the TWO THINGS WE DID NOT FIND section carries exactly two",
    "two files": "the note rebuilds from exactly two committed inputs, our prop "
                 "capture and the cached MLB game logs",
    "two numbers": "'the gap between those two numbers' — ours and the "
                   "market's, both named in the previous clause",
    "two of": "'the worst bucket often holds two of them' — describes the "
              "retired ten-bucket statistic, not a current measurement",

    # the correction record. These describe runs that are over, so they are
    # frozen on purpose: if one of them moved, the record would be false.
    "eight days": "'what we got wrong for eight days' — a closed interval",
    "five more": "'five more days of capture' — the gap between the withdrawn "
                 "run and the one that replaced it",
    "dozen pitchers": "'about a dozen pitchers' — explicitly approximate, and "
                      "about the superseded run",
    "ten calibration": "the retired statistic used ten buckets; frozen with "
                       "the claim it corrects",

    # descriptions of another page's UI, not measurements of anything
    "five last": "'his last five, last ten and season starts' — what /props "
                 "shows",
    "ten and": "the second half of the same phrase",

    # deliberately vague. Replacing these with figures would overstate them.
    "most of": "'Most of what looked like the model's information' and 'most "
               "of that information is gone' — qualitative by intent",
    "half of": "'winning fewer than half of them' — directional, and checked "
               "against board.won_pct below",

    # tracked against the payload by the sibling test below
    "eleven point": "'an eleven-point edge' — checked against "
                    "board.mean_abs_delta_pts below",
    "five equal": "'five equal-sized buckets' — checked against salvage.folds "
                  "below",
    "three or": "'three or more books on both sides' — checked against "
                "method.board_filter below",

    # ---- DISPUTED -------------------------------------------------------
    "four fifths": "WRONG since it was written on 2026-08-28 and still live. "
                   "It reads 80%; the effect it describes is 57%. Kept here "
                   "rather than silently rewritten because correcting prose on "
                   "this page is Branden's call, not an unattended agent's. "
                   "Evidence and a gate-verified diff: "
                   "docs/plans/2026-09-03-four-fifths.md. DELETE THIS ENTRY "
                   "when the sentence is fixed.",
}


def _worded(text: str) -> dict[str, str]:
    """Every worded quantity in the prose, keyed by its normalised phrase."""
    out: dict[str, str] = {}
    for pattern in _WORDED:
        for m in re.finditer(pattern, text, re.I):
            phrase = re.sub(r"\W+", " ", m.group(0).strip().lower()).strip()
            out.setdefault(m.start(), phrase)
    return out


def test_no_worded_quantities_left_in_the_prose():
    """A quantity spelled in words is still a published number.

    Nothing here says a phrase is *right* — several of these are frozen history
    and one is recorded as wrong. It says a human has looked at each one and
    written down why it may stay. A new one has not been looked at.
    """
    html = PAGE.read_text(encoding="utf-8")
    body = html.split("<main", 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<(\w+)\b[^>]*\bdata-(?:f=\"[^\"]+\"|was)[^>]*>.*?</\1>",
                  " ", body, flags=re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))

    unreviewed = sorted(set(_worded(text).values())
                        - set(REVIEWED_WORDED_QUANTITIES))
    assert not unreviewed, (
        f"worded quantities in /props-model prose that nobody has reviewed: "
        f"{unreviewed}. Wire the number to scripts/props_model_note.py with a "
        f"data-f element, or add it to REVIEWED_WORDED_QUANTITIES with the "
        f"reason it may stay. Spelling a figure out is not a way around the "
        f"digit test.")


def test_the_worded_quantities_that_track_a_figure_still_match(payload):
    """Four of the reviewed phrases describe a number the payload computes.

    An allowlist entry saying "checked against board.won_pct" is a comment
    until something checks it. These are the checks. If a rerun moves one of
    these figures, the prose that spells it out goes stale silently — which is
    the entire failure this file exists to prevent.
    """
    d = payload["detail"]
    assert round(d["board"]["mean_abs_delta_pts"]) == 11, (
        "the page says the model claimed 'an eleven-point edge' but "
        f"board.mean_abs_delta_pts is now "
        f"{d['board']['mean_abs_delta_pts']:.1f}")
    assert d["board"]["won_pct"] < 0.5, (
        "the page says the model won 'fewer than half' of its disagreements "
        f"but board.won_pct is now {d['board']['won_pct']:.3f}")
    assert d["salvage"]["folds"] == 5, (
        "the page says calibration error is scored across 'five equal-sized "
        f"buckets' but salvage.folds is {d['salvage']['folds']}")
    assert d["method"]["board_filter"].startswith("3+"), (
        "the page says prices came from 'three or more books on both sides' "
        f"but method.board_filter is {d['method']['board_filter']!r}")
