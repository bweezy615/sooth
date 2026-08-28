"""The figures the site serves must be the figures we generated.

`site/content/_figures.json` is the build input. `site/public/data/figures.json`
is what desk.js fetches at runtime for the populations block on /record and
/trust. They used to be kept in step by remembering to copy one over the other,
which worked until it didn't: the public copy sat 19 days stale, so /record and
/trust quoted 1291-1317-63 (49.5%) while /methodology and /picks quoted
1298-1310-63 (49.8%). A site whose entire claim is that its numbers are
reproducible cannot disagree with itself about its own record.

published_figures.py now writes both. This holds them together.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "site/content/_figures.json"
PUBLIC = ROOT / "site/public/data/figures.json"


def test_the_served_figures_are_the_generated_figures():
    assert PUBLIC.read_text(encoding="utf-8") == CONTENT.read_text(encoding="utf-8"), (
        "site/public/data/figures.json is out of step with site/content/"
        "_figures.json. Rerun scripts/published_figures.py rather than copying "
        "one over the other — a hand copy is what went stale last time."
    )


def test_the_record_quoted_in_prose_matches_the_generated_figures():
    """/disclaimers states the backtest record in prose. It is hand-typed, so
    it is the thing most likely to be left behind when the model changes — and
    it was, by this morning's decision-rule change."""
    fig = json.loads(CONTENT.read_text(encoding="utf-8"))
    ind = fig["evaluation_a"]["results"]["independent"]
    prose = (ROOT / "site/content/disclaimers.md").read_text(encoding="utf-8")

    assert ind["ats_record"] in prose, (
        f"disclaimers.md does not quote the current ATS record "
        f"{ind['ats_record']}"
    )
    assert f"{ind['brier']}" in prose, (
        f"disclaimers.md does not quote the current Brier score {ind['brier']}"
    )
    assert f"{ind['ats_pct'] * 100:.2f}%" in prose, (
        f"disclaimers.md does not quote the current ATS percentage "
        f"{ind['ats_pct'] * 100:.2f}%"
    )


def _owned_figures(fig: dict) -> set[str]:
    """Every string form of a number that _figures.json is the source of.

    Deliberately the *rendered* forms — "49.77%", "0.22151", "1298-1310-63" —
    because those are what a hand-typed copy would look like in the markdown.
    """
    out: set[str] = set()
    for ev in ("evaluation_a", "evaluation_b"):
        for r in fig[ev]["results"].values():
            out |= {r["ats_record"], f"{r['brier']:.5f}", f"{r['ece']:.5f}",
                    f"{r['ats_pct']:.4f}", f"{r['ats_pct'] * 100:.2f}%",
                    f"{r['accuracy'] * 100:.2f}%"}
    for r in fig["reliability_independent"]:
        out |= {f"{r['predicted'] * 100:.2f}%", f"{r['actual'] * 100:.2f}%",
                f"{r['gap'] * 100:+.2f} pts"}
    for ev in ("evaluation_a", "evaluation_b"):
        s = fig["selectivity"][ev]
        for t in s["thresholds"]:
            for side in ("all", "underdog", "favourite"):
                out |= {t[side]["record"], f"{t[side]['pct'] * 100:.2f}%"}
        out |= {f"{b:.2%}" for b in s["live"]["ci95"]}
    return {v for v in out if v}


def test_methodology_does_not_type_its_figures():
    """Hard rule 1, enforced on the page most likely to break it.

    methodology.md used to paste in the tables published_figures.py prints, and
    the reliability block went a full generation stale that way while /record —
    which fetches figures.json at runtime — showed the current one. The page now
    carries {{fig:}} and {{table:}} tokens that scripts/build_site.py resolves
    at build time. A number typed back in beside them would drift again, so
    this fails if one appears.
    """
    fig = json.loads(CONTENT.read_text(encoding="utf-8"))
    prose = re.sub(r"\{\{[^}]+\}\}", "",
                   (ROOT / "site/content/methodology.md").read_text(encoding="utf-8"))
    typed = sorted(v for v in _owned_figures(fig) if v in prose)
    assert not typed, (
        f"methodology.md types figures that _figures.json owns: {typed}. "
        f"Use a {{{{fig:...}}}} token instead - see "
        f"docs/plans/methodology-figures.md."
    )


# --- hand-typed figures on the pages the generator does not build ----------
# /methodology and /disclaimers come from site/content/*.md and are wired to
# _figures.json at build time. The five pages below are hand-written HTML that
# build_site.py never touches, and each of them types the backtest record into
# its copy. Hard rule 1 allows exactly two answers to that: wire it, or pin it
# with a test. Wiring means fetching figures.json and rewriting hero copy at
# runtime, which trades a drift risk for a flash-of-wrong-content risk on the
# page that carries the argument. So: pinned.
#
# Every value below was verified correct on 2026-08-27. When the model changes,
# these go red and name the file and the number to change. That is the point.

def _pct(value: float, dp: int) -> str:
    """Half-up, which is what the pages show: 53.15 reads as 53.2, not 53.1."""
    from decimal import ROUND_HALF_UP, Decimal
    q = Decimal(1).scaleb(-dp)
    return f"{Decimal(str(value * 100)).quantize(q, rounding=ROUND_HALF_UP)}%"


def _expected(fig: dict) -> dict[str, list[tuple[str, str]]]:
    ind = fig["evaluation_a"]["results"]["independent"]
    mkt = fig["evaluation_a"]["results"]["market"]
    live = fig["selectivity"]["evaluation_a"]["live"]
    wins, losses, pushes = ind["ats_record"].split("-")
    n = f"{ind['n']:,}"
    decided = f"{int(wins) + int(losses):,}"
    be1, be2 = _pct(fig["breakeven_ats"], 1), _pct(fig["breakeven_ats"], 2)

    return {
        "trust.html": [
            (n, "graded walk-forward games"),
            (decided, "decided games"),
            (pushes, "pushes"),
            (_pct(ind["ats_pct"], 1), "our ATS%"),
            (_pct(mkt["ats_pct"], 1), "the market's ATS%"),
            (be1, "break-even"),
        ],
        "picks.html": [
            (_pct(ind["ats_pct"], 1), "our ATS% on the whole board"),
            (decided, "decided games"),
            (be2, "break-even"),
            (_pct(live["pct"], 1), "ATS% of the games clearing the bar"),
        ],
        "engine.html": [
            (n, "graded ATS calls"),
            (decided, "decided games"),
            (be1, "break-even"),
        ],
        "record.html": [
            (be2, "break-even"),
            (f"{fig['confidence_cap'] * 100:.0f}%", "confidence cap"),
        ],
        "learn.html": [(be1, "break-even at -110")],
    }


def test_the_hand_written_pages_quote_the_generated_figures():
    fig = json.loads(CONTENT.read_text(encoding="utf-8"))
    missing = []
    for page, wanted in _expected(fig).items():
        html = (ROOT / "site/public" / page).read_text(encoding="utf-8")
        for value, what in wanted:
            if value not in html:
                missing.append(f"{page} does not quote {what} as {value}")
    assert not missing, (
        "the site is quoting a figure _figures.json no longer supports. Update "
        "the page(s), do not regenerate around it:\n  " + "\n  ".join(missing)
    )


def test_the_edge_bar_is_the_same_number_in_all_three_places():
    """picks.html hard-codes `var EDGE_BAR=4`, the engine decides with
    ensemble.EDGE_THRESHOLD, and the measurement is published as
    selectivity.rule_threshold_pts. Let them drift and /picks contradicts
    itself: with the bar at 4 in the copy and 5 in the engine, a no-play slate
    renders "nothing sits 4 points off the number - the furthest we get is 4.3".
    """
    import re

    from engine.models.ensemble import EDGE_THRESHOLD

    fig = json.loads(CONTENT.read_text(encoding="utf-8"))
    published = float(fig["selectivity"]["rule_threshold_pts"])
    assert float(EDGE_THRESHOLD) == published, (
        f"ensemble.EDGE_THRESHOLD is {EDGE_THRESHOLD} but _figures.json "
        f"publishes the rule at {published}"
    )

    html = (ROOT / "site/public/picks.html").read_text(encoding="utf-8")
    m = re.search(r"var EDGE_BAR\s*=\s*([0-9.]+)\s*;", html)
    assert m, "picks.html no longer declares EDGE_BAR - update this test"
    assert float(m.group(1)) == published, (
        f"picks.html says the bar is {m.group(1)} points; the engine and the "
        f"published measurement say {published:g}. The page would describe a "
        f"bar it is not applying."
    )
