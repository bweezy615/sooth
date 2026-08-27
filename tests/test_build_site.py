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
