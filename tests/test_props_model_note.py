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
