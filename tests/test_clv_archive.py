"""The published closing-line archive must be rebuildable from the evidence.

``site/public/data/clv-nfl.json`` was committed once, by hand, on 2026-08-06.
For twenty-two days /tools told visitors to two decimal places whether they beat
the close, against a 104 KB payload nothing in this repository could rebuild or
check. It turned out to be right - regenerating it reproduces all 855 games
exactly - but that was luck, and luck is not the standard this site argues for.

So the reproduction is a test. It also catches the thing most likely to happen
next: a newly backfilled season that never reaches the published file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.clv_archive import build

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "site/public/data/clv-nfl.json"
TOOLS = ROOT / "site/public/tools.html"
DISCLAIMERS = ROOT / "site/content/disclaimers.md"

PUBLISHED_FIELDS = ("t", "ch", "ca", "fh", "fa", "nb")


def _key(g: dict) -> tuple:
    return (g["s"], g["w"], g["h"], g["a"])


def test_the_published_archive_is_what_the_backfill_produces():
    published = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    rebuilt = build()

    have = {_key(g): g for g in published["games"]}
    want = {_key(g): g for g in rebuilt["games"]}
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    assert not missing, (
        f"{len(missing)} game(s) are in data/backfill but not in the published "
        f"archive - rerun scripts/clv_archive.py. First: {missing[:3]}")
    assert not extra, (
        f"{len(extra)} published game(s) have no backfill behind them: "
        f"{extra[:3]}")

    wrong = [(k, f, have[k][f], want[k][f]) for k in want
             for f in PUBLISHED_FIELDS if have[k].get(f) != want[k][f]]
    assert not wrong, (
        f"{len(wrong)} published value(s) disagree with the backfill, e.g. "
        f"{wrong[:3]} - rerun scripts/clv_archive.py")


def test_the_archives_own_note_matches_its_contents():
    """The committed note said "across 10-16 books". The moneyline range is
    7-16. A note is a claim like any other, so it is derived, not written."""
    p = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    books = [g["nb"] for g in p["games"]]
    assert p["books_min"] == min(books) and p["books_max"] == max(books)
    assert p["n_games"] == len(p["games"])
    assert f"{p['books_min']}-{p['books_max']} books" in p["note"], (
        f"the note says something other than the real range: {p['note']}")


def test_the_tools_page_quotes_no_book_range_of_its_own():
    html = TOOLS.read_text(encoding="utf-8")
    m = re.search(r'<h2>CLV checker.*?</p>', html, re.S)
    assert m, "the CLV checker panel changed shape - update this test"
    # Commentary about the rule is not a breach of it.
    panel = re.sub(r"<!--.*?-->", "", m.group(0), flags=re.S)
    assert not re.search(r"\d+\s*[-–]\s*\d+\s*books", panel), (
        "the CLV checker states a book range in its markup; the count differs "
        "game by game and is published per game as `nb`: " + panel[:200])


def test_the_disclaimer_does_not_deny_the_clv_the_site_publishes():
    """/disclaimers said in bold "We do not currently publish a closing-line-
    value figure" from 2026-08-02, while /tools shipped a CLV checker on
    2026-08-06 and has answered in points ever since."""
    text = DISCLAIMERS.read_text(encoding="utf-8").lower()
    assert ARCHIVE.exists(), "no CLV archive - this test needs rewriting"
    for denial in ("do not currently publish a closing-line-value",
                   "do not publish a closing-line-value"):
        assert denial not in text, (
            f"/disclaimers claims '{denial}', but the CLV checker on /tools "
            f"publishes one from site/public/data/clv-nfl.json")
