"""Build the static site.

Content lives in markdown under site/content/. This renders it into the shared
shell so the prose pages and the data pages look like one product, and so the
methodology page is regenerated from source rather than hand-maintained in two
places.

The ledger page is generated from data/ledger/, not written by hand. That is
deliberate: the page a skeptic reads must be a rendering of the same files
they can download and verify themselves, or it is just another claim.

    python scripts/build_site.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import markdown

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.commit import commitment_history

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "site/content"
PUBLIC = ROOT / "site/public"
LEDGER = ROOT / "data/ledger"

BRAND = "Sooth"
DOMAIN = "https://sooth.bet"

# nav-key for the shared shell.js highlight, per slug
DATA_PAGE = {"methodology": "method", "verify": "verify",
             "ledger": "ledger", "disclaimers": ""}
# internal links in prose/ledger use bare /slug; the site serves explicit .html
LINK_SLUGS = ("methodology", "verify", "ledger", "disclaimers", "board", "record")

# Pages built from markdown: (slug, source, title, description)
PAGES = [
    ("methodology", "methodology.md", "Methodology",
     "The exact model, the walk-forward backtest, the calibration table, and "
     "the result we lose to the market. Reproducible from published data."),
    ("verify", "verify.md", "Verify our record",
     "How to independently recompute our Merkle root and prove no prediction "
     "was altered after the fact. Standard library only."),
    ("disclaimers", "disclaimers.md", "Disclaimers",
     "Entertainment and analysis only. We accept no wagers, hold no funds, "
     "and make no performance claims."),
]

# The prose pages share the terminal design system: sooth.css for style,
# shell.js injects the header + compliant footer so nav/legal never drift from
# the hand-built pages (board, record, home). No inline CSS or chrome here.
SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {brand}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{domain}/{slug}.html">
<meta property="og:title" content="{title} — {brand}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/sooth.css">
</head>
<body data-page="{data_page}">
<a class="skip" href="#main">Skip to content</a>
<main class="wrap-narrow" id="main"><div class="prose">
{body}
</div></main>
<script src="/assets/shell.js" defer></script>
</body>
</html>
"""


def _html_links(html: str) -> str:
    """Rewrite bare internal /slug links to explicit /slug.html to match the
    rest of the site, so prose cross-links resolve on a plain static host."""
    return re.sub(
        r'href="/(' + "|".join(LINK_SLUGS) + r')"',
        r'href="/\1.html"', html,
    )


def render(slug: str, title: str, description: str, body: str) -> str:
    return SHELL.format(
        title=title, brand=BRAND, description=description, domain=DOMAIN,
        slug=slug, data_page=DATA_PAGE.get(slug, ""), body=_html_links(body),
    )


def build_markdown_pages() -> list[str]:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"]
    )
    built = []
    for slug, src, title, desc in PAGES:
        path = CONTENT / src
        if not path.exists():
            print(f"  SKIP {slug}: {src} missing")
            continue
        md.reset()
        html = md.convert(path.read_text(encoding="utf-8"))
        (PUBLIC / f"{slug}.html").write_text(
            render(slug, title, desc, html), encoding="utf-8")
        built.append(slug)
        print(f"  built /{slug}")
    return built


def build_ledger() -> None:
    """Render every committed slate straight from data/ledger/."""
    slate_ids = sorted({p.name.split(".commitment")[0]
                        for p in LEDGER.glob("*.commitment.v*.json")})
    if not slate_ids:  # legacy unversioned layout
        slate_ids = sorted({p.name.split(".commitment")[0]
                            for p in LEDGER.glob("*.commitment.json")})

    slates = []
    now = datetime.now(timezone.utc)
    for slate_id in slate_ids:
        history = commitment_history(slate_id, LEDGER)
        if not history:
            history = [json.loads((LEDGER / f"{slate_id}.commitment.json").read_text(encoding="utf-8"))]
        c = history[-1]
        kickoff = datetime.fromisoformat(c["earliest_kickoff"])
        public_state = "revealed" if kickoff < now else "sealed"
        slates.append({**c, "state": public_state, "history": history})

    rows = []
    for s in sorted(slates, key=lambda x: x["slate_id"], reverse=True):
        badge = "revealed" if s["state"] == "revealed" else "sealed"
        label = "REVEALED" if s["state"] == "revealed" else "SEALED"
        hist = s.get("history", [])
        superseded = ""
        if len(hist) > 1:
            items = "".join(
                f'<div class="row"><span class="k">v{h["version"]} '
                f'({h["n_predictions"]})</span>'
                f'<span class="hash" style="color:var(--dim)">{h["merkle_root"]}</span></div>'
                for h in hist[:-1]
            )
            superseded = (
                f'<div class="row"><span class="k">superseded</span>'
                f'<span style="font-size:12.5px;color:var(--muted)">'
                f'{len(hist)-1} earlier commitment(s), retained and still '
                f'verifiable. Predictions may be revised until kickoff; what '
                f'is never permitted is a root quietly disappearing.'
                f'</span></div>{items}'
            )
        rows.append(f"""
<div class="card">
  <div class="row"><span class="k">slate</span>
    <span><strong>{s['slate_id']}</strong>
    <span class="badge {badge}">{label}</span></span></div>
  <div class="row"><span class="k">predictions</span><span>{s['n_predictions']}</span></div>
  <div class="row"><span class="k">merkle root</span><span class="hash">{s['merkle_root']}</span></div>
  <div class="row"><span class="k">sealed at</span><span class="mono">{s['committed_at']}</span></div>
  <div class="row"><span class="k">first kickoff</span><span class="mono">{s['earliest_kickoff']}</span></div>
  <div class="row"><span class="k">algorithm</span><span class="mono">{s['algorithm']}</span></div>
  {superseded}
  <div class="row"><span class="k">files</span><span>
    <a href="/data/{s['slate_id']}.json">slate</a></span></div>
</div>""")

    body = f"""
<h1>Ledger</h1>
<p>Every slate we have ever committed, newest first. A <span class="badge sealed">SEALED</span>
slate has had its Merkle root published but its predictions withheld until the
games begin. A <span class="badge revealed">REVEALED</span> slate has been
opened in full and can be recomputed by anyone.</p>
<p>Nothing is ever edited or removed from this page. If a prediction were
altered after sealing, the recomputed root would not match the published one —
that is the entire point, and <a href="/verify">you can check it yourself</a>.</p>
<p><strong>{len(slates)}</strong> slate(s) committed.</p>
{''.join(rows) if rows else '<p class="mono">No slates committed yet.</p>'}
<h2>What this page does not prove</h2>
<p>The commitment proves our predictions were fixed before kickoff and have not
been altered. It proves nothing about whether they are any good. For that, read
the <a href="/methodology">methodology</a> — including the part where our
backtest loses to the closing market.</p>
"""
    (PUBLIC / "ledger.html").write_text(
        render("ledger", "Ledger",
               "Every slate we have committed, sealed before kickoff and "
               "verifiable afterward. Nothing edited, nothing removed.", body),
        encoding="utf-8",
    )
    print(f"  built /ledger ({len(slates)} slate(s))")


def publish_figures() -> None:
    """Copy the regenerated performance figures into /data so the static
    Record page can fetch them. The figures themselves are produced by
    scripts/published_figures.py; this only publishes them."""
    src = CONTENT / "_figures.json"
    if not src.exists():
        print("  SKIP figures: _figures.json missing (run published_figures.py)")
        return
    (PUBLIC / "data").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "data" / "figures.json").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8")
    print("  published /data/figures.json")


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    print("building site...")
    build_markdown_pages()
    build_ledger()
    publish_figures()
    print("done")


if __name__ == "__main__":
    main()
