"""Prose claims that must stay true to the code and the data behind them.

The site's whole position is that its statements are checkable, so a sentence
that has quietly stopped being true is a worse defect than a broken feature.
Two were found on /methodology on 2026-08-27:

- "No play-level information. The model does not use expected points added" —
  while the same page's summary says the model is "augmented with
  opponent-aware expected-points-added form", `_figures.json` describes it as
  "Elo + opponent-aware EPA + rest", and `ensemble.BASE_FEATURES` contains
  `epa_edge`. The page contradicted itself; the limitation bullet was the half
  left over from the pure-Elo model.
- "The other eight sports on this site" — the site covers five sports in total.

Neither is the kind of thing a build breaks on, so it is checked here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from engine.models.ensemble import BASE_FEATURES

ROOT = Path(__file__).resolve().parents[1]
METHODOLOGY = ROOT / "site/content/methodology.md"
DESK_JS = ROOT / "site/public/assets/desk.js"
BOARD = ROOT / "site/public/data/board.json"

_NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def _sports() -> set[str]:
    """Every sport the site actually presents, from the shell's own rail."""
    rail = re.search(r"var SPORTS=\[(.*?)\];", DESK_JS.read_text(encoding="utf-8"),
                     re.S)
    assert rail, "desk.js no longer declares SPORTS - update this test"
    return set(re.findall(r'k:"([a-z]+)"', rail.group(1)))


def test_the_sport_rail_and_the_board_agree_on_what_we_cover():
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    assert {b["sport"] for b in board["boards"]} <= _sports(), (
        "board.json publishes a sport the shell's rail does not show"
    )


def test_methodology_counts_the_other_sports_correctly():
    """It said "the other eight sports" while the site covered five in total."""
    others = len(_sports()) - 1          # every sport but the graded one, NFL
    text = METHODOLOGY.read_text(encoding="utf-8")
    assert f"other {_NUMBER_WORDS[others]} sports" in text, (
        f"methodology.md should say 'other {_NUMBER_WORDS[others]} sports' - the "
        f"site covers {len(_sports())} ({', '.join(sorted(_sports()))}), of "
        f"which only NFL is graded."
    )
    wrong = [w for n, w in _NUMBER_WORDS.items()
             if n != others and f"other {w} sports" in text]
    assert not wrong, f"methodology.md also claims 'other {wrong[0]} sports'"


def test_methodology_does_not_deny_the_features_the_model_uses():
    """The published model reads team-week EPA. The page may say it does not
    read plays; it may not say it does not use EPA at all."""
    text = METHODOLOGY.read_text(encoding="utf-8").lower()
    assert "epa_edge" in BASE_FEATURES, (
        "the model no longer uses EPA - this test, and the methodology copy it "
        "guards, both need rewriting"
    )
    for denial in ("does not use expected points added",
                   "no play-level information"):
        assert denial not in text, (
            f"methodology.md claims '{denial}', but ensemble.BASE_FEATURES is "
            f"{BASE_FEATURES}. The model reads team-week EPA per play; only "
            f"play-by-play data is absent."
        )


# --- "last updated" must not lie ------------------------------------------
# /methodology said "Last updated 2026-08-06" and /disclaimers "2026-08-02";
# both had in fact been edited on 2026-08-27. A freshness date is a claim like
# any other, and a stale one on the pages a skeptic opens first is the cheapest
# possible way to look untrustworthy. /methodology's date is now generated from
# _figures.json's own generated_at, so it cannot drift; /disclaimers has no
# figure to bind to, so it is checked here instead.

def _last_touched(path: Path) -> str:
    """When this file last changed: today if it is dirty, else its last commit.

    Using the commit date alone would only fail the run *after* the offending
    push. Counting an uncommitted edit as today catches it before.
    """
    import datetime
    import subprocess
    rel = path.relative_to(ROOT).as_posix()
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", "--", rel],
                               cwd=ROOT, capture_output=True, text=True,
                               timeout=30)
        if dirty.returncode != 0:
            return ""                                  # not a checkout; skip
        if dirty.stdout.strip():
            return datetime.date.today().isoformat()
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", rel],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def test_the_stated_last_updated_dates_are_not_behind_the_files():
    stale = []
    for name in ("methodology.md", "disclaimers.md"):
        path = ROOT / "site/content" / name
        touched = _last_touched(path)
        if not touched:
            continue                                   # no git here; nothing to check
        for label, date in re.findall(
                r"\*(Last updated|Figures on this page regenerated) ([0-9]{4}-[0-9]{2}-[0-9]{2})",
                path.read_text(encoding="utf-8")):
            if date < touched:
                stale.append(f"{name} says {label.lower()} {date}, "
                             f"but it was edited {touched}")
    assert not stale, "; ".join(stale)
