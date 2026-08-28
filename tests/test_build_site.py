"""The generator and the site it generates must not drift apart.

`scripts/build_site.py` owns four files under `site/public/`. Every one of them
had been hand-edited since the generator last matched, so running the script
silently reverted live work — on 2026-08-27 a rebuild would have republished
superseded backtest figures and deleted a section of /methodology. The script
carried a "⚠ DRIFT WARNING" comment telling the reader to diff first. It had
been there for five days and prevented none of it, because a comment is not a
check.

This is the check. It builds into a temp directory and compares byte for byte,
so it fails in both directions: hand-edit a generated page without porting the
change up, or change the generator without rebuilding, and this goes red.

If it fails, do NOT just rerun the builder over the top — look at which side is
right first. The published page has been the correct one before now.
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "site/public"

# Everything build_site.py writes. Keep in step with its write_text() calls.
GENERATED = ["methodology.html", "verify.html", "disclaimers.html", "ledger.html"]


def _build_site():
    spec = importlib.util.spec_from_file_location(
        "build_site", ROOT / "scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory):
    """Rebuild into a throwaway root. site/public/ is never written."""
    out = tmp_path_factory.mktemp("site")
    bs = _build_site()
    bs.PUBLIC = out
    bs.build_markdown_pages()
    bs.build_ledger()
    return out


@pytest.mark.parametrize("name", GENERATED)
def test_generated_page_matches_whats_published(rebuilt, name):
    fresh = (rebuilt / name).read_text(encoding="utf-8")
    live = (PUBLISHED / name).read_text(encoding="utf-8")
    assert fresh == live, (
        f"{name} differs from what scripts/build_site.py produces. Either the "
        f"page was hand-edited and the change was not ported into the "
        f"generator, or the generator changed and the site was not rebuilt. "
        f"Decide which side is correct before rebuilding over the top."
    )


def test_the_frost_pass_ices_the_values_under_test_and_nothing_else(rebuilt):
    """/verify's argument is a comparison, so the things being compared are the
    things that get the ice colour — and the working material must not, or the
    distinction stops meaning anything."""
    v = (rebuilt / "verify.html").read_text(encoding="utf-8")
    # published root, recomputed root, and the leaf being proven
    assert v.count('<span class="ice">') == 4
    assert v.count('<span class="ok">VERIFIED</span>') == 1
    # the four inclusion-proof siblings are working material, not claims
    assert '"side": "right", "hash": "<span class="ice">' not in v
    # and the pointer to the previous seal is not a value under test
    for line in v.split("\n"):
        if "supersedes" in line:
            assert "ice" not in line


def test_only_the_sealed_artefacts_are_frosted(rebuilt):
    """The tools a reader uses to break the seal stay plain: nothing about them
    is committed, and they are meant to be read, edited and distrusted."""
    v = (rebuilt / "verify.html").read_text(encoding="utf-8")
    assert v.count('<pre class="frosted">') == 5
    assert 'class="language-frosted"' not in v, "attr_list leaked a fake language"

    blocks = re.findall(r"<pre( class=\"frosted\")?><code[^>]*>(.*?)</code></pre>",
                        v, re.S)
    frosted = {bool(f) for f, body in blocks
               for tool in ["curl -O https://sooth.bet",
                            "# verify.py - independently", "def check_proof("]
               if tool in body}
    assert frosted == {False}, "a reader's tool was rendered as a sealed artefact"


class TestFigureSubstitution:
    """methodology.md carries {{fig:}} tokens instead of typed numbers.

    Before this, its figures were pasted in from published_figures.py's stdout,
    and on 2026-08-27 the reliability table was found a generation stale while
    /record — which renders the same table from figures.json at runtime — showed
    the current one. Two pages, two calibration tables, same 2,671 games.
    """

    # One module instance: _build_site() re-executes the file, and a second
    # execution defines a *different* FigureError class, so pytest.raises would
    # never match the one actually raised.
    _MODULE = None

    @classmethod
    def _bs(cls):
        if cls._MODULE is None:
            cls._MODULE = _build_site()
        return cls._MODULE

    FIG = {
        "breakeven_ats": 0.5238,
        "confidence_cap": 0.85,
        "evaluation_a": {"results": {"independent": {
            "n": 2671, "brier": 0.22151, "ece": 0.03074,
            "ats_record": "1298-1310-63", "ats_pct": 0.4977}}},
        "reliability_independent": [
            {"bucket": b, "n": 100, "predicted": 0.5, "actual": 0.45,
             "gap": g}
            for b, g in [("0.3-0.4", 0.0268), ("0.4-0.5", 0.0305),
                         ("0.5-0.6", 0.0512), ("0.6-0.7", 0.0273),
                         ("0.7-0.8", 0.0168)]
        ],
    }

    def sub(self, text):
        return self._bs().substitute(text, self.FIG)

    def test_formats(self):
        cases = {
            "{{fig:breakeven_ats}}": "0.5238",
            "{{fig:breakeven_ats|4f}}": "0.5238",
            "{{fig:breakeven_ats|pct2}}": "52.38%",
            "{{fig:confidence_cap|pct0}}": "85%",
            "{{fig:evaluation_a.results.independent.n|comma}}": "2,671",
            "{{fig:evaluation_a.results.independent.n|int}}": "2671",
            "{{fig:evaluation_a.results.independent.brier|5f}}": "0.22151",
            "{{fig:evaluation_a.results.independent.ats_record}}": "1298-1310-63",
            "{{fig:evaluation_a.results.independent.ats_pct|pct2}}": "49.77%",
            "{{fig:reliability_independent.0.gap|pts2}}": "+2.68 pts",
            "{{fig:reliability_independent.0.gap|pts1_bare}}": "2.7",
        }
        for token, want in cases.items():
            assert self.sub(token) == want, token

    def test_a_list_is_indexed_by_a_numeric_segment(self):
        assert self.sub("{{fig:reliability_independent.2.bucket}}") == "0.5-0.6"

    def test_an_unknown_figure_raises_rather_than_rendering(self):
        """A page showing a literal {{fig:typo}} to a visitor would be worse
        than the hand-typed number it replaced. Fail the build instead."""
        bs = self._bs()
        with pytest.raises(bs.FigureError, match="no such figure"):
            self.sub("{{fig:evaluation_a.results.nosuchmodel.brier}}")

    def test_an_unknown_format_raises(self):
        bs = self._bs()
        with pytest.raises(bs.FigureError, match="unknown format"):
            self.sub("{{fig:breakeven_ats|furlongs}}")

    def test_an_unknown_table_raises(self):
        bs = self._bs()
        with pytest.raises(bs.FigureError, match="unknown table"):
            self.sub("{{table:nonesuch}}")

    def test_the_derived_middle_bands_are_a_sum_not_a_new_measurement(self):
        """reliability_mid exists so the prose under the reliability table can
        say "2,290 of the 2,671" without typing it. It must only add up rows
        that are already published."""
        out = self.sub("{{fig:reliability_mid.n|comma}} "
                       "{{fig:reliability_mid.min_gap|pts1_bare}} "
                       "{{fig:reliability_mid.max_gap|pts1_bare}}")
        assert out == "500 1.7 5.1"

    def test_a_missing_middle_band_raises(self):
        bs = self._bs()
        fig = dict(self.FIG,
                   reliability_independent=self.FIG["reliability_independent"][:2])
        with pytest.raises(bs.FigureError, match="missing middle bands"):
            bs.substitute("{{fig:reliability_mid.n}}", fig)

    def test_the_shipped_edge_bar_is_bolded_from_the_data(self):
        """Moving the bar must move the emphasis, not leave it on 4 points."""
        bs = self._bs()
        def row(pct, record, n):
            return {"record": record, "pct": pct, "n": n, "ci95": [0, 1],
                    "per_season": 1}
        ev = {"thresholds": [{"edge": e, "all": row(0.5, "1-1-0", 2),
                              "underdog": row(0.5, "1-1-0", 2),
                              "favourite": row(0.5, "1-1-0", 2)}
                             for e in (0.0, 2.0, 3.0)]}
        fig = {"selectivity": {"rule_threshold_pts": 3.0,
                               "evaluation_a": ev, "evaluation_b": ev}}
        out = bs.substitute("{{table:selectivity}}", fig)
        bold = [ln for ln in out.split("\n") if "**" in ln]
        assert len(bold) == 1 and "3 points" in bold[0]
