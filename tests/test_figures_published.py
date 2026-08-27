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
