"""Two pages must not answer to the same name.

Until 2026-08-27 `/trust` was titled "Sooth — Ledger" and `/ledger` was titled
"Ledger — Sooth". The header nav's LEDGER link went to the first — an index of
receipts — while the actual ledger of sealed slates, the artifact a skeptic
opens the nav looking for, was reachable only from the footer and lit no nav
entry at all. The homepage sidebar labelled that same page a third way, "Proof
Ledger". One word, three destinations.

On a site whose whole argument is "check our arithmetic", a reader who follows a
label to the wrong page has been handed a reason to doubt the rest. So this is a
check, not a comment: `/trust` is now "Proof", `/ledger` is "Ledger", and the
next page that borrows a name already in use fails here.

See docs/plans/ledger-nav-collision.md.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "site/public"

_TITLE = re.compile(r"<title>([^<]*)</title>")
# The brand affix is decoration; "Sooth — Ledger" and "Ledger — Sooth" are the
# same name for a reader, which is precisely how the collision survived review.
_BRAND = re.compile(r"^(?:sooth(?:\.bet)?)\s+—\s+|\s+—\s+(?:sooth(?:\.bet)?)$",
                    re.I)


def _name(html: str) -> str | None:
    m = _TITLE.search(html)
    return _BRAND.sub("", m.group(1)).strip().lower() if m else None


def test_every_page_is_titled():
    missing = [p.name for p in sorted(PUBLIC.glob("*.html"))
               if _name(p.read_text(encoding="utf-8")) is None]
    assert not missing, f"pages with no <title>: {missing}"


def test_no_two_pages_share_a_name():
    seen: dict[str, str] = {}
    clashes = []
    for p in sorted(PUBLIC.glob("*.html")):
        name = _name(p.read_text(encoding="utf-8"))
        if name in seen:
            clashes.append(f"{seen[name]} and {p.name} are both '{name}'")
        seen[name] = p.name
    assert not clashes, (
        "two pages answer to the same name, so a link labelled with it is "
        "ambiguous: " + "; ".join(clashes))


def test_the_ledger_is_the_page_that_is_called_the_ledger():
    """The specific regression. `/ledger` renders data/ledger/; it owns the
    word. `/trust` indexes the receipts and is called Proof."""
    assert _name((PUBLIC / "ledger.html").read_text(encoding="utf-8")) == "ledger"
    assert _name((PUBLIC / "trust.html").read_text(encoding="utf-8")) == "proof"


def test_the_ledger_lights_the_nav_entry_that_leads_to_it():
    """Standing on the sealed ledger used to leave every nav entry dark, which
    is half of why nobody noticed the nav pointed somewhere else."""
    ledger = (PUBLIC / "ledger.html").read_text(encoding="utf-8")
    assert 'Desk.mount("proof")' in ledger, (
        "ledger.html must mount the PROOF section. It is generated — fix "
        "MOUNT in scripts/build_site.py and rebuild, not the HTML."
    )
