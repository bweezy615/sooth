"""Every page that states the model's record must state the generated one.

This repo has already been bitten by exactly this, once: `figures.json` sat 19
days stale and /record and /trust quoted 1291-1317-63 (49.5%) while
/methodology and /picks quoted 1298-1310-63 (49.8%). A site whose whole claim
is that its arithmetic is reproducible cannot disagree with itself about its
own record.

`tests/test_figures_published.py` closed half of that hole: it holds the two
JSON artifacts together, and it pins the prose on /disclaimers. But /picks,
/predictor, /trust, /props-model and /engine also hand-type the same figures,
and nothing held them to anything. They are correct today. Nothing except this
file would notice if they stopped being correct after the next model change --
and "changing the model changes the copy" is the other lesson this repo has
already paid for.

Hard rule 1 says a hand-typed figure gets wired to the generator or gets a test.
These pages are hand-maintained HTML rather than build_site.py output, so a test
is the honest instrument.

Percentages are rendered from the win-loss-push record, never from the stored
`ats_pct`. Re-rounding an already-rounded number is its own quiet defect: the
edge>=4 bucket is 278-245-7, which is 53.155% and renders 53.2%, but the stored
0.5315 re-rounded to one decimal gives 53.1%.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIGURES = json.loads((ROOT / "site/content/_figures.json").read_text(encoding="utf-8"))
PUBLIC = ROOT / "site/public"


def _pct_from_record(record: str, places: int = 1) -> str:
    """Render W-L-P as a percentage of decided games, rounded once."""
    won, lost, _pushes = (int(x) for x in record.split("-"))
    return f"{won / (won + lost) * 100:.{places}f}%"


def _decided(record: str) -> int:
    won, lost, _pushes = (int(x) for x in record.split("-"))
    return won + lost


_IND = FIGURES["evaluation_a"]["results"]["independent"]
_EDGE4 = FIGURES["selectivity"]["evaluation_a"]["thresholds"][3]["all"]

ATS_PCT = _pct_from_record(_IND["ats_record"])          # 49.8%
DECIDED = f"{_decided(_IND['ats_record']):,}"           # 2,608
EDGE4_PCT = _pct_from_record(_EDGE4["record"])          # 53.2%
BREAKEVEN = f"{FIGURES['breakeven_ats'] * 100:.2f}%"    # 52.38%

# page -> the generated figures that page states in its own copy.
PINS = {
    "picks.html": [ATS_PCT, DECIDED, EDGE4_PCT, BREAKEVEN],
    "predictor.html": [ATS_PCT, DECIDED, BREAKEVEN],
    "trust.html": [ATS_PCT, DECIDED],
    "props-model.html": [ATS_PCT, DECIDED],
    "engine.html": [DECIDED],
    "record.html": [BREAKEVEN],
    "index.html": [BREAKEVEN],
    "methodology.html": [BREAKEVEN],
    "disclaimers.html": [BREAKEVEN],
}


@pytest.mark.parametrize("page,expected", sorted(PINS.items()))
def test_public_page_states_the_generated_figure(page, expected):
    text = (PUBLIC / page).read_text(encoding="utf-8", errors="replace")
    missing = [v for v in expected if v not in text]
    assert not missing, (
        f"/{page.removesuffix('.html')} no longer states {missing}. Either the "
        f"model changed and this page's copy was left behind, or the copy was "
        f"edited away from the generated figure. Regenerate with "
        f"scripts/published_figures.py and update the page to match "
        f"_figures.json — do not update this test to match the page."
    )


# Percentages that are legitimately allowed to sit next to "ATS" or "against
# the spread" in public copy: our headline record, the selective bucket, the
# breakeven bar, and the per-model rows of /methodology's backtest table.
_ALLOWED = {ATS_PCT, EDGE4_PCT, BREAKEVEN} | {
    _pct_from_record(m["ats_record"])
    for m in FIGURES["evaluation_a"]["results"].values()
} | {
    _pct_from_record(m["ats_record"])
    for m in FIGURES["evaluation_b"]["results"].values()
}

_NEAR_ATS = re.compile(
    r"(\d{2}\.\d{1,2}%)(?=(?:[^<>]|<[^>]*>){0,80}?(?:ATS|against the spread))"
)


@pytest.mark.parametrize("page", sorted(p.name for p in PUBLIC.glob("*.html")))
def test_no_public_page_quotes_a_superseded_ats_percentage(page):
    """The 49.5%-vs-49.8% split was two pages disagreeing about one number.

    Rather than enumerate values that are wrong -- which cannot be known in
    advance -- this asserts the complement: any percentage a page presents as
    an against-the-spread figure has to be one the generator currently emits.
    A stale figure left behind by a model change fails here, on the page that
    carries it.
    """
    text = (PUBLIC / page).read_text(encoding="utf-8", errors="replace")
    found = set(_NEAR_ATS.findall(text))
    unknown = sorted(found - _ALLOWED)
    assert not unknown, (
        f"/{page.removesuffix('.html')} presents {unknown} as an "
        f"against-the-spread figure, and _figures.json does not currently "
        f"produce it. Current values: {sorted(_ALLOWED)}."
    )
