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
