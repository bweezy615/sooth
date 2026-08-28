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


def _sport_label_maps() -> dict[str, list[tuple[str, str]]]:
    """Every hand-written `var SPORT_LABEL={...}` in the shipped pages."""
    out: dict[str, list[tuple[str, str]]] = {}
    for page in ("index.html", "game.html", "market.html"):
        text = (ROOT / "site/public" / page).read_text(encoding="utf-8")
        for body in re.findall(r"var SPORT_LABEL=\{(.*?)\};", text, re.S):
            out.setdefault(page, []).append(
                tuple(re.findall(r'(\w+):"([^"]+)"', body)))  # type: ignore[arg-type]
    return out


def test_every_page_calls_each_sport_by_the_same_name():
    """A trust site must not call one league two names.

    The rail in desk.js is the list of what we cover; three pages repeat it as
    a hand-written SPORT_LABEL map. Hand-kept copies of a list go stale - this
    repo has already paid for that once with figures.json - so the copies are
    checked against the original rather than trusted.
    """
    rail = re.search(r"var SPORTS=\[(.*?)\];",
                     DESK_JS.read_text(encoding="utf-8"), re.S)
    assert rail
    want = dict(re.findall(r'k:"([a-z]+)",l:"([A-Z]+)"',
                           re.sub(r"\s+", "", rail.group(1))))
    assert want, "desk.js SPORTS no longer parses - update this test"

    maps = _sport_label_maps()
    assert maps, "no SPORT_LABEL maps found - update this test"
    for page, occurrences in maps.items():
        for pairs in occurrences:
            got = dict(pairs)
            assert got == want, (
                f"{page}'s SPORT_LABEL disagrees with the sport rail in "
                f"desk.js. rail={want} {page}={got}")


def test_no_page_renders_a_raw_sport_slug():
    """One league, one name, on every surface that shows a league.

    The slugs are internal keys, not display names. Uppercasing one puts
    "NCAAF" on a card sitting directly under a rail tab that says "CFB" - which
    is what /edges, the phone board card, the desktop movement rows and the
    /alerts team picker were all doing on 2026-08-28. Every one of them was a
    separate line of code that had never needed a display name before college
    football arrived with a slug that is not its name.
    """
    offenders = []
    for page in sorted((ROOT / "site/public").glob("*.html")):
        for i, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"[.]toUpperCase[(][)]", line):
                # Judge the RECEIVER, not the line. Plenty of lines mention
                # a sport while upper-casing something else entirely: a book
                # abbreviation, or board.json's own `label` field, which is
                # already the display name we want.
                recv = line[max(0, m.start() - 40):m.start()].lower()
                if "sport" not in recv:
                    continue
                if "label" in recv or "abbr" in recv:
                    continue
                offenders.append(f"{page.name}:{i}: {line.strip()[:90]}")
    assert not offenders, (
        "a page is rendering the raw sport slug instead of its display "
        "name; use Desk.sportLabel() or the page SPORT_LABEL map: "
        + "; ".join(offenders))


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


def test_no_page_promises_live_prices_in_static_copy():
    """Freshness is a measurement; a static label must not claim it.

    /market was headed "MARKET INTELLIGENCE DESK · LIVE PRICING" while the
    board is rebuilt by capture.yml - which through late August 2026 was
    landing about three runs a day, mean gap 4.2h and max 10.5h. desk.js calls
    a feed stale past three hours, so for roughly half the wall clock the
    page's own status strip read DELAYED directly beneath a label promising
    LIVE. The strip is the honest surface because it is computed from
    generated_at; the label is a promise nothing checks.

    Extended on the same day to "LIVE BOARD", which /edges and /ask were both
    stamping across their chrome and /ask across its meta description, while
    /ask showed no timestamp of any kind. Its answers quote a price to the
    point; they now carry the age of the board they read.
    """
    offenders = []
    for page in sorted((ROOT / "site/public").glob("*.html")):
        for i, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("<!--", "*", "/*")):
                continue                      # commentary about the rule itself
            # Uppercase is the site's own chrome - the .tl labels and the meta
            # descriptions - making a claim. Lowercase "the live board" in
            # prose, a loading state or an error string is the artifact's name
            # rather than a promise about its age, and is left alone.
            if re.search(r"LIVE (PRICING|PRICES|ODDS|BOARD)", line):
                offenders.append(f"{page.name}:{i}: {line.strip()[:90]}")
            if re.search(r"content=\"[^\"]*live board", line, re.I):
                offenders.append(f"{page.name}:{i}: {line.strip()[:90]}")
    assert not offenders, (
        "a page states in static copy that its prices are live. The board "
        "refreshes when capture.yml runs, which is not continuous; let the "
        "generated_at stamp say how old the numbers are: " + "; ".join(offenders))


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
