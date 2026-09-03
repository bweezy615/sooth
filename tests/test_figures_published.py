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

    # The same sentence quotes three more generated figures, and until
    # 2026-09-03 only the three above were pinned. A model change that moved
    # the sample size or the market's Brier would have left /disclaimers -- the
    # page that states our record for legal purposes -- quietly wrong, with the
    # three checked figures around it still passing. Found by the Task 3 sweep
    # in docs/plans/2026-09-03-overnight.md.
    mkt = fig["evaluation_a"]["results"]["market"]
    for value, what in ((f"{ind['n']:,}", "sample size"),
                        (f"{mkt['brier']}", "market's Brier score"),
                        (f"{fig['breakeven_ats'] * 100:.2f}%", "break-even")):
        assert value in prose, (
            f"disclaimers.md does not quote the current {what} {value}")


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
        # /predictor quotes the same four numbers /trust does, in prose, and
        # was the one page doing it unpinned. It had not drifted when this was
        # added on 2026-08-28 - but neither had methodology.md the day before
        # it did.
        "predictor.html": [
            (_pct(ind["ats_pct"], 1), "our ATS%"),
            (decided, "decided games"),
            (n, "graded walk-forward games"),
            (pushes, "pushes"),
            (be2, "break-even"),
        ],
        # The stat tile's own subtitle. The number beside it is filled from
        # figures.json at runtime; this half was typed.
        "index.html": [(be2, "break-even")],
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


# --- /verify's walkthrough has to reproduce --------------------------------
# /verify hand-typed every figure in its worked example until 2026-09-01, when
# the v4 re-seal left all of them disagreeing with the files the page itself
# tells the reader to download: it printed the v3 root, its sample output
# contradicted its own JSON block two screens higher, and its inclusion proof
# was still the v1 sixteen-prediction tree. On the page whose argument is "a
# mismatch means you caught us", that is the worst place on the site to carry a
# number nobody regenerates.
#
# scripts/build_site.slate_figures() now computes them from data/ledger and
# raises rather than publish one it cannot verify. These hold that in place.

VERIFY_MD = ROOT / "site/content/verify.md"
VERIFY_HTML = ROOT / "site/public/verify.html"


def _verify_page() -> str:
    """The rendered page as a READER sees it. Inside a code block the JSON
    quotes are stored as &quot;, so comparing against the raw markup would
    miss the canonical string that is plainly on the page."""
    import html

    return html.unescape(VERIFY_HTML.read_text(encoding="utf-8"))


def test_verify_types_no_hash_of_its_own():
    """A 64-character hex literal in the markdown is a figure nothing updates."""
    typed = re.findall(r"\b[0-9a-f]{64}\b", VERIFY_MD.read_text(encoding="utf-8"))
    assert not typed, (
        f"verify.md types {len(typed)} hash(es) by hand: {typed}. Use a "
        f"{{{{fig:slate....}}}} token so build_site.py recomputes it from "
        f"data/ledger on every build."
    )


def test_the_verify_page_walks_through_the_committed_slate():
    """slate_figures() raises if data/ledger, the reveal and the served
    commitment disagree, so calling it is half the check. The rest is that the
    published page actually carries what it returned."""
    from scripts.build_site import slate_figures

    s = slate_figures()
    html = _verify_page()
    for what, value in (("merkle root", s["merkle_root"]),
                        ("first leaf hash", s["first_leaf"]),
                        ("canonical string", s["first_canonical"]),
                        ("slate id", s["id"])):
        assert str(value) in html, (
            f"/verify does not show the current {what} ({value}). Rebuild with "
            f"scripts/build_site.py."
        )


def test_verify_never_shows_an_orphaned_superseded_root():
    """A root from an older seal, left on the page, reads as the current one.

    The latest root is expected, and so is the one it names in `supersedes` -
    the commitment block prints it. Any earlier root is a leftover.
    """
    from engine.commit import commitment_history
    from scripts.build_site import LEDGER, slate_figures

    history = commitment_history(slate_figures()["id"], LEDGER)
    latest = history[-1]
    allowed = {latest["merkle_root"], latest.get("supersedes")}
    html = _verify_page()
    stale = [(h.get("version"), h["merkle_root"]) for h in history[:-1]
             if h["merkle_root"] not in allowed]
    for version, root in stale:
        assert root not in html, (
            f"/verify still shows the v{version} root {root}, but the slate is "
            f"committed at v{latest.get('version')}. A reader comparing the page "
            f"against the file it links would see a mismatch."
        )


# --- the bar, spelled out --------------------------------------------------
# test_the_edge_bar_is_the_same_number_in_all_three_places holds the digit 4
# together across picks.html's `var EDGE_BAR`, ensemble.EDGE_THRESHOLD and
# _figures.json. Two pages also state the bar in WORDS, and nothing held those:
# move the bar to five and that test goes red naming `var EDGE_BAR`, someone
# fixes the three digits, the gate goes green, and /picks still tells a reader
# "the bar is four points of disagreement" while the engine applies five.
#
# Same lesson as "four fifths" on /props-model, found by the same sweep: a
# digit test does not see a number that is spelled out.
# See docs/plans/2026-09-03-overnight.md, Task 3.

_BAR_IN_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                 7: "seven", 8: "eight", 9: "nine", 10: "ten"}

# (file, the phrase it must contain, with {w} standing in for the bar)
_BAR_PHRASES = [
    (ROOT / "site/content/methodology.md", "{w}-point bar"),
    (ROOT / "site/public/picks.html", "bar is {w} points of disagreement"),
]


def test_the_edge_bar_is_spelled_the_same_way_in_the_copy():
    fig = json.loads(CONTENT.read_text(encoding="utf-8"))
    published = float(fig["selectivity"]["rule_threshold_pts"])
    assert published == int(published) and int(published) in _BAR_IN_WORDS, (
        f"the bar is now {published}, which this test has no word for. Add it "
        f"to _BAR_IN_WORDS and reword the two sentences below.")
    word = _BAR_IN_WORDS[int(published)]

    wrong = []
    for path, template in _BAR_PHRASES:
        want = template.format(w=word)
        if want not in path.read_text(encoding="utf-8"):
            wrong.append(f"{path.name} does not say {want!r}")
    assert not wrong, (
        f"the published bar is {published:g} points but the copy does not spell "
        f"it that way:\n  " + "\n  ".join(wrong) +
        f"\nEdit the sentence (methodology.md is the SOURCE — rebuild after), "
        f"or update the expected phrase here if it was deliberately reworded.")
