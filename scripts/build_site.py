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

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import markdown

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.commit import (canonical, commitment_history, merkle_proof,
                           merkle_root, verify_proof)

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "site/content"
PUBLIC = ROOT / "site/public"
LEDGER = ROOT / "data/ledger"
# What sooth.bet actually serves. Deliberately NOT derived from PUBLIC:
# tests/test_build_site.py redirects PUBLIC to a temp directory to rebuild
# without touching the site, and this is a build INPUT - the payload the
# seal pipeline published and that /verify tells a reader to download.
SERVED = ROOT / "site/public/data"

BRAND = "Sooth"
DOMAIN = "https://sooth.bet"

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

# The stylesheets below are the ones actually serving on sooth.bet.
# tests/test_build_site.py rebuilds the site into a temp root and fails if this
# file and site/public/ disagree, so a hand edit to either side that is not
# mirrored in the other cannot land. That test is the guard the old "diff
# before running" comment here was trying, and failing, to be. A comment is not
# a check. See docs/plans/build-site-drift.md.
#
# CSS_PROSE serves /methodology and /disclaimers. /verify is CSS_PROSE with the
# frost rules spliced in ahead of the long-form block, where they sit on disk.
# /ledger has its own sheet: that page is the frozen artifact itself.
CSS_PROSE = """/* FROZEN MARKET — the long-form pages carry their own stylesheet. The legacy
   token names these rules were written against now resolve onto the desk
   system instead of a second, warmer palette, so the article and the shell it
   is mounted inside are one cold surface rather than two that meet awkwardly
   at the header. Nothing below redefines a shared token. */
:root{--bg:var(--g0);--panel:var(--g1);--panel-2:var(--g3);
--line:var(--hair);--line-2:var(--hair2);--muted:var(--mut);
--accent:var(--brand);--warn:var(--amber);--bad:var(--dn);--link:var(--brand)}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font:15px/1.7 var(--sans);
-webkit-font-smoothing:antialiased}
/* The shell is the shell. .wrap used to be redefined to 860px here, which
   quietly shrank the injected header and footer on these three pages alone —
   and the bare `nav{}` rule below it was landing on the shell's own nav. Both
   are gone; only the measure of the prose is narrow now. */
.prose{max-width:812px;margin:0 auto;padding:44px 0 60px}
.prose a{color:var(--link);text-decoration:none}
.prose a:hover{text-decoration:underline;text-underline-offset:2px}
.prose h1{font:700 clamp(24px,3.6vw,32px)/1.15 var(--sans);letter-spacing:-.025em;
margin:0 0 24px;color:var(--ink)}
/* Section heads take the promo's teal triangle — the same mark .caps uses for
   a capability list. One hue, one bullet, on every surface that names a part. */
.prose h2{display:flex;align-items:flex-start;gap:9px;
font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--muted);margin:42px 0 14px;padding-top:22px;
border-top:1px solid var(--line)}
.prose h2::before{content:"";flex:0 0 auto;margin-top:2px;
border:4px solid transparent;border-left-color:var(--brand)}
.prose h3{font-size:15px;margin:26px 0 8px;font-weight:650;color:var(--ink)}
.prose p{margin:0 0 15px;color:var(--ink2)}
.prose li{margin:0 0 7px;color:var(--ink2)}
.prose strong{font-weight:650;color:var(--ink)}
.prose code{font-family:var(--mono);font-size:12.5px;background:var(--panel-2);
border:1px solid var(--line-2);border-radius:var(--r);padding:1px 5px;color:var(--ink)}
/* A code block is a slab of dark glass lit along its top edge — rule 3. */
.prose pre{background:linear-gradient(180deg,#0E141A 0%,#0A0F14 100%);
border:1px solid var(--line);border-radius:var(--r);padding:15px 17px;
overflow-x:auto;font-size:12px;line-height:1.55;
box-shadow:inset 0 1px 0 rgba(190,240,245,.09),inset 0 -1px 0 rgba(0,0,0,.5)}
.prose pre code{background:none;border:0;padding:0;font-size:12px}
.prose table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0;
display:block;overflow-x:auto;font-family:var(--mono);
font-variant-numeric:tabular-nums}
.prose th{text-align:left;font-weight:600;color:var(--dim);font-size:9.5px;
text-transform:uppercase;letter-spacing:.12em;padding:0 12px 9px;
border-bottom:1px solid var(--line-2);white-space:nowrap;font-family:var(--mono)}
.prose td{padding:9px 12px;border-bottom:1px solid var(--line);color:var(--ink2)}
/* Below 720px a table stops being a table, exactly as .itab already does on
   the board: each row becomes a labelled card, using the data-l attributes
   Desk.stack() already writes onto every table on the site. A six-column
   backtest table was otherwise a sideways scroller that hid every number to
   the right of the model name — which on this page is the whole argument. */
@media (max-width:720px){
  .prose table{display:block;overflow-x:visible}
  .prose tbody,.prose tr,.prose td{display:block;width:auto}
  .prose thead{display:none}
  .prose tr{border:1px solid var(--line);background:var(--panel);
    padding:11px 13px 3px;margin:0 0 8px}
  .prose td{padding:6px 0;text-align:right;white-space:normal;
    display:flex;align-items:baseline;justify-content:space-between;gap:14px}
  .prose td::before{content:attr(data-l);flex:0 0 auto;text-align:left;
    font:600 9.5px var(--mono);letter-spacing:.11em;text-transform:uppercase;
    color:var(--dim)}
  .prose td:not([data-l]){display:block;text-align:left;padding-bottom:9px;
    color:var(--ink)}
  .prose td:not([data-l])::before{content:none}
  .prose tr td:last-child{border-bottom:0}
}
.prose blockquote{margin:18px 0;padding:14px 18px;background:var(--panel);
border-left:2px solid var(--warn);border-radius:0 var(--r) var(--r) 0}
.prose blockquote p{margin:0}
.prose hr{border:0;border-top:1px solid var(--line);margin:34px 0}
footer p{max-width:86ch;margin:0 0 9px}
.mono{font-family:var(--mono)}
.hash{font-family:var(--mono);font-size:11.5px;color:var(--frost);
word-break:break-all}
.badge{display:inline-block;font:700 9.5px/1 var(--mono);
letter-spacing:.08em;padding:3px 7px;border-radius:var(--r);
border:1px solid var(--line-2);color:var(--muted);vertical-align:2px}
/* Rule 2: frost means sealed. A SEALED badge is ice, not a caution colour. */
.badge.sealed{color:var(--frost);border-color:var(--frost-rim)}
.badge.revealed{color:var(--brand);border-color:var(--brand)}
.card{background:linear-gradient(180deg,#141B22 0%,#0E141A 55%,#0A0F14 100%);
border:1px solid var(--line);border-radius:var(--r);padding:17px 19px;margin:0 0 13px;
box-shadow:inset 0 1px 0 rgba(190,240,245,.10),inset 0 -1px 0 rgba(0,0,0,.55),
0 18px 40px -22px rgba(0,0,0,.9)}
.card .row{display:flex;gap:13px;padding:4px 0;flex-wrap:wrap;font-size:12.5px}
.card .k{color:var(--dim);min-width:118px;font-family:var(--mono);font-size:10.5px;
letter-spacing:.06em;text-transform:uppercase;padding-top:2px}

/* ---- long-form rhythm ----------------------------------------------------
   Three typographic repairs, no colour and no new primitive.

   1. MEASURE. The column ran the full 812px — roughly 100 characters at
      15px Archivo, past the point where the eye reliably finds the start of
      the next line. Running text is capped at 72ch; headings, tables and code
      keep the whole column, so a six-column table still has room to breathe.

   2. LIST MARKERS. desk.css's reset zeroes padding on every element, so every
      <ul> and <ol> here inherited padding-left:0 and hung its bullets and its
      numbers outside the measure. At 375px they were clipped off the left of
      the screen: the numbered specification read "Canonical JSON… Leaf hash…"
      with no numbers at all. 22px puts the markers back on the text's grid.

   3. THE DOUBLED RULE. The markdown these pages are generated from writes
      `---` before most `##`, and .prose h2 draws its own border-top — so every
      section opened with two hairlines 42px apart and nothing between them.
      A heading that already has an <hr> above it drops its own rule. */
.prose p,.prose li{max-width:72ch}
.prose ul,.prose ol{margin:0 0 15px;padding-left:22px}
.prose li>ul,.prose li>ol{margin:7px 0 0}
.prose li::marker{color:var(--mut)}
.prose hr+h2{border-top:0;padding-top:0;margin-top:26px}
.prose h2+h3{margin-top:16px}
.prose h3+p,.prose h3+ul,.prose h3+ol{margin-top:0}
@media (max-width:720px){
  .prose{padding:28px 0 44px}
  .prose h1{margin-bottom:18px}
  .prose h2{margin:34px 0 12px;padding-top:18px}
  .prose hr{margin:26px 0}
  .prose ul,.prose ol{padding-left:20px}
  .prose pre{padding:13px 14px}
}"""

# Frost means sealed. On every other page that is a metaphor; /verify is where
# someone recomputes the root and finds out whether the ice is real, so there
# it is load-bearing markup and needs rules the prose pages never use.
CSS_VERIFY_FROST = """/* ============ THIS PAGE IS THE ICE BEING CHECKED ============
   Rule 2 says frost means sealed. On every other page that is a metaphor.
   Here it is literal: this is the page where someone recomputes the root and
   finds out whether the ice is real, so the frost does the arguing.

   The division is the argument. The artefacts WE sealed — the commitment
   file, the canonical prediction, its leaf fingerprint, the inclusion proof,
   and the run that recomputes the root — are under ice, using the shared
   .frosted surface. The blocks that are YOUR tools for breaking that seal —
   curl, verify.py, check_proof — stay plain dark glass, because nothing about
   them is committed and you are meant to read, edit and distrust them.
   Sealed vs. yours, drawn rather than said. */
.prose pre.frosted{overflow-x:auto}
.prose pre.frosted code{color:var(--ink)}
/* the two roots and the leaf: the values the whole page exists to compare */
.prose .ice{color:var(--frost)}
/* the verdict line, in the one hue */
.prose .ok{color:var(--brand);font-weight:600}
/* The article itself carries the shared .rimlit hairline (see the markup):
   one lit teal edge across the top of the block, the single edge-light moment
   in the promo, spent on the page that carries the proof. */

"""

_ANCHOR = "/* ---- long-form rhythm"
assert _ANCHOR in CSS_PROSE, "long-form anchor lost; the frost rules would move"
CSS_VERIFY = CSS_PROSE.replace(_ANCHOR, CSS_VERIFY_FROST + _ANCHOR, 1)

CSS_LEDGER = """/* FROZEN MARKET — this page is the frozen artifact itself.
   A sealed slate is a commitment nobody can edit afterwards, so the seal chip
   and the published root are the two things rendered as ice (rule 2), and
   nothing else on the page carries a hue.

   The page used to carry its own warm palette and redefine --ink, --dim and
   --mono on :root. Those tokens belong to the shell: the header and footer
   desk.js injects were reading them, so the wordmark and the compliance floor
   rendered in a different colour here than on every other page. The local
   palette is gone and everything below is expressed in desk.css tokens.

   The header/nav/.brand/footer rules went with it. They were not merely dead:
   .brand was declared here, after desk.css and at equal specificity, with
   text-transform:uppercase — it was rendering the lowercase sooth.bet
   wordmark in caps on this page alone — and bare nav{} was giving the
   injected .hd-links its own height, max-width and 28px padding. */
*{box-sizing:border-box}
/* The generator (scripts/build_site.py) writes one inline `color:var(--muted)`
   into the "superseded" row, and defines --muted in its own CSS constant. This
   page dropped that constant when it was re-skinned, so the token resolved to
   nothing and the longest, least important sentence on the page rendered at
   full body brightness — louder than the roots above it. Aliasing the legacy
   name onto the desk token fixes it here and survives the next rebuild. */
:root{--muted:var(--mut)}
/* only the prose column is 860px; the shell's own .wrap stays site-width */
body>.wrap{max-width:860px;margin:0 auto;padding:0 24px}
@media (max-width:720px){body>.wrap{padding:0 14px}}
.prose{padding:40px 0 60px;font:15px/1.7 var(--sans);color:var(--ink2)}
.prose a{color:var(--brand)}
.prose a:hover{text-decoration:underline;text-underline-offset:2px}
.prose h1{font:760 clamp(24px,3.6vw,32px)/1.15 var(--sans);letter-spacing:-.02em;
margin:0 0 24px;color:var(--ink)}
.prose h2{font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--mut);margin:42px 0 14px;padding-top:22px;border-top:1px solid var(--hair)}
.prose h3{font:650 15px/1.4 var(--sans);margin:26px 0 8px;color:var(--ink)}
.prose p{margin:0 0 15px;color:var(--ink2)}
.prose li{margin:0 0 7px;color:var(--ink2)}
.prose strong{font-weight:650;color:var(--ink)}
.prose code{font-family:var(--mono);font-size:12.5px;background:var(--g2);
border:1px solid var(--hair2);border-radius:var(--r);padding:1px 5px;color:var(--ink)}
.prose pre{background:var(--g1);border:1px solid var(--hair);
border-radius:var(--r);padding:15px 17px;overflow-x:auto;font-size:12px;
line-height:1.55;box-shadow:inset 0 1px 0 rgba(190,240,245,.08)}
.prose pre code{background:none;border:0;padding:0;font-size:12px}
/* a table here wraps rather than scrolling sideways: the column is already
   narrow enough to read on a phone, and a scroller hides the numbers */
.prose table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0;
font-family:var(--mono);font-variant-numeric:tabular-nums}
.prose th{text-align:left;font:600 9.5px var(--mono);color:var(--dim);
text-transform:uppercase;letter-spacing:.12em;padding:0 12px 9px;
border-bottom:1px solid var(--hair2)}
.prose td{padding:9px 12px;border-bottom:1px solid var(--hair);color:var(--ink2)}
.prose blockquote{margin:18px 0;padding:14px 18px;background:var(--g1);
border-left:2px solid var(--amber);border-radius:0 var(--r) var(--r) 0}
.prose blockquote p{margin:0}
.prose hr{border:0;border-top:1px solid var(--hair);margin:34px 0}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
/* the published root — the one artifact on this site that is genuinely
   frozen, so it is the one thing set in ice */
.hash{font:500 11.5px/1.55 var(--mono);color:var(--frost);letter-spacing:.02em;
word-break:break-all}
/* SEALED is the shared .frost chip (see the markup below). .badge survives for
   any other state the builder emits: REVEALED has thawed and is verifiable, so
   it takes the one hue. */
.prose .frost{vertical-align:1px}
.badge{display:inline-block;font:600 9.5px/1 var(--mono);letter-spacing:.14em;
text-transform:uppercase;padding:4px 8px;
border:1px solid var(--hair2);color:var(--mut);vertical-align:2px}
.badge.sealed{color:var(--frost);border-color:var(--frost-rim);
background:var(--frost-dim)}
.badge.revealed{color:var(--brand);border-color:rgba(45,212,167,.35)}
/* one slate, one slab of dark glass, lit along its top edge — the shared
   instrument recipe, so the light source matches the rest of the site */
.card{background:linear-gradient(180deg,#141B22 0%,#0E141A 55%,#0A0F14 100%);
border:1px solid var(--hair);border-radius:var(--r);padding:17px 19px;margin:0 0 13px;
box-shadow:inset 0 1px 0 rgba(190,240,245,.10),inset 0 -1px 0 rgba(0,0,0,.55),
0 18px 40px -22px rgba(0,0,0,.9)}
.card .row{display:grid;grid-template-columns:118px minmax(0,1fr);gap:13px;
padding:5px 0;font-size:12.5px;color:var(--ink2);align-items:baseline}
.card .k{color:var(--dim);font:600 10px/1.5 var(--mono);
letter-spacing:.14em;text-transform:uppercase}
/* A flex row with a 118px minimum on the key wrapped unpredictably: some
   values sat beside their label, a 64-character hash dropped to its own line,
   and the rows came out 29px, 57px, 72px and 121px tall in the same card. A
   two-column grid puts every label on one rail and every value on another, so
   the card reads down a single edge. Below 560px there is not room for two
   rails, so the label stacks above its value instead of squeezing it. */
@media (max-width:560px){
  .card .row{grid-template-columns:minmax(0,1fr);gap:3px;padding:7px 0}
  .card{padding:15px 14px}
}
/* the prose column is generated markdown; give its lists their markers back
   (desk.css's reset zeroes padding on everything) */
.prose ul,.prose ol{margin:0 0 15px;padding-left:22px}
.prose li::marker{color:var(--mut)}
.prose p,.prose li{max-width:72ch}"""

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {brand}</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#06080A">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Sooth">
<meta name="description" content="{description}">
<link rel="canonical" href="{domain}/{slug}">
<meta property="og:title" content="{title} — {brand}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:image" content="https://sooth.bet/og.jpg">
<meta property="og:url" content="{domain}/{slug}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<!-- desk.css first so this page's own rules below still win on any clash;
     it is here for the shared header and footer that desk.js injects. -->
<link rel="stylesheet" href="/assets/desk.css">
<style>
{css}
</style>
<link rel="stylesheet" href="/assets/market-system.css?v=market-interface">
</head>
<body>
<div class="wrap"><div class="prose{prose_class}">
{body}
</div></div>
<script src="/assets/desk.js"></script>
<script>window.Desk.mount("{mount}");</script>
<script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js");</script>
</body>
</html>
"""


# Keyed on slug rather than threaded through PAGES so the ledger page, which is
# not built from markdown and never appears in PAGES, resolves the same way.
SHEETS = {"verify": CSS_VERIFY, "ledger": CSS_LEDGER}

# One lit teal edge across the top of the article. It is the single edge-light
# moment on the long-form pages, and it is spent on the one carrying the proof.
PROSE_CLASS = {"verify": " rimlit"}

# Which header-nav entry a generated page lights. /ledger is the sealed-slate
# artifact the PROOF entry exists to lead to, so standing on it must not leave
# the nav dark — that was half of why two pages both called themselves "Ledger"
# went unnoticed. The prose pages hang off the footer, belong to no section,
# and correctly light nothing. See docs/plans/ledger-nav-collision.md.
MOUNT = {"ledger": "proof"}


def render(slug: str, title: str, description: str, body: str) -> str:
    return SHELL.format(
        title=title, brand=BRAND, description=description, domain=DOMAIN,
        slug=slug, css=SHEETS.get(slug, CSS_PROSE), body=body,
        prose_class=PROSE_CLASS.get(slug, ""), mount=MOUNT.get(slug, ""),
    )


_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
_FROSTED_BLOCK = re.compile(
    r'(<pre class="frosted"><code[^>]*>)(.*?)(</code></pre>)', re.S)


def frost(html: str) -> str:
    """Ice the values a sealed artefact exists to be checked against.

    /verify divides its code blocks: the artefacts WE sealed are under frost,
    the tools YOU use to break the seal stay plain dark glass. Which is which
    is declared in the markdown — ``` {.frosted}``` — because that is an
    editorial call and belongs next to the prose making it.

    Inside a frosted block two values take the ice colour: a fingerprint on a
    line that names a root, and a fingerprint standing alone as the whole line.
    That is exactly the published root, the recomputed root, and the leaf being
    proven — the numbers the page asks you to compare. Deliberately NOT iced:
    the `supersedes` hash (a pointer to an older seal, not a value under test)
    and the inclusion proof's four siblings (working material, not the claim).
    Markdown escapes raw HTML inside a fence, so this cannot live in the source.
    """
    html = html.replace('<pre><code class="language-frosted">',
                        '<pre class="frosted"><code>')

    def ice(line: str) -> str:
        if line.strip() == "VERIFIED":
            return '<span class="ok">VERIFIED</span>'
        if _HEX64.fullmatch(line.strip()) or "root" in line.lower():
            return _HEX64.sub(lambda m: f'<span class="ice">{m.group(0)}</span>',
                              line)
        return line

    return _FROSTED_BLOCK.sub(
        lambda m: m.group(1) + "\n".join(ice(ln) for ln in m.group(2).split("\n"))
        + m.group(3), html)


# ---------------------------------------------------------------------------
# Figure substitution.
#
# Hard rule 1: no published number is hand-typed. methodology.md used to type
# all of its in, pasted from published_figures.py's stdout, and on 2026-08-27
# the reliability table had drifted a generation behind: /record renders that
# table from figures.json at runtime, so the two pages showed different
# calibration numbers for the same 2,671 games, and the prose reading the table
# was stale with it.
#
# So the markdown carries tokens and this resolves them at build time:
#
#   {{fig:evaluation_a.results.independent.ats_pct|pct2}}   ->  49.77%
#   {{table:reliability}}                                   ->  the whole table
#
# An unresolved or misspelled token raises. Rendering a literal "{{fig:...}}"
# to a visitor would be worse than the hand-typed number it replaced.
# See docs/plans/methodology-figures.md.
# ---------------------------------------------------------------------------

FIGURES = CONTENT / "_figures.json"

_TOKEN = re.compile(r"\{\{(fig|table):([a-zA-Z0-9_.]+)(?:\|([a-zA-Z0-9_]+))?\}\}")


class FigureError(RuntimeError):
    """A token the published figures cannot answer. Never rendered, always raised."""


def _fmt(value, spec, token):
    try:
        if spec is None:
            return str(value)
        if spec == "int":
            return str(int(value))
        if spec == "comma":
            return f"{int(value):,}"
        if spec == "round0":                                 # 260.8 -> "261"
            return f"{round(float(value))}"
        if spec == "date":                                   # ISO stamp -> 2026-08-27
            return str(value)[:10]
        if spec.endswith("f") and spec[:-1].isdigit():        # 2f, 4f, 5f
            return f"{float(value):.{int(spec[:-1])}f}"
        if spec.startswith("pct") and spec[3:].isdigit():     # pct1, pct2
            return f"{float(value) * 100:.{int(spec[3:])}f}%"
        if spec.startswith("pts") and spec[3:].isdigit():     # pts2 -> "+2.68 pts"
            return f"{float(value) * 100:+.{int(spec[3:])}f} pts"
        # ..._bare: the same scaling with no sign and no unit, for prose that
        # supplies its own ("between 1.7 and 5.1 percentage points").
        if spec.startswith("pts") and spec.endswith("_bare") and spec[3:-5].isdigit():
            return f"{abs(float(value)) * 100:.{int(spec[3:-5])}f}"
    except (TypeError, ValueError) as e:
        raise FigureError(f"{token}: cannot format {value!r} as {spec}") from e
    raise FigureError(f"{token}: unknown format '{spec}'")


def _lookup(figures, path, token):
    node = figures
    for part in path.split("."):
        try:
            # a numeric segment indexes a list: reliability_independent.0.n,
            # selectivity.evaluation_a.live.ci95.1
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, TypeError, IndexError, ValueError) as e:
            raise FigureError(
                f"{token}: no such figure - _figures.json has nothing at "
                f"'{part}' in '{path}'. Rerun scripts/published_figures.py if "
                f"the shape changed.") from e
    return node


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


_BACKTEST_LABELS = {"elo": "Elo baseline", "independent": "Independent (ours)",
                    "consensus": "Consensus (+market)", "market": "Closing market"}


def _model_table(ev):
    rows = ["| model | n | Brier | ECE | ATS record | ATS% |",
            "|---|---|---|---|---|---|"]
    for key, label in _BACKTEST_LABELS.items():
        r = ev["results"][key]
        rows.append(_row([label, r["n"], f"{r['brier']:.5f}", f"{r['ece']:.5f}",
                          r["ats_record"], f"{r['ats_pct']:.4f}"]))
    return "\n".join(rows)


def _tbl_backtest_a(f):
    return _model_table(f["evaluation_a"])


def _tbl_backtest_b(f):
    return _model_table(f["evaluation_b"])


def _tbl_ece(f):
    res = f["evaluation_a"]["results"]
    return "\n".join([
        "| model | ECE | Brier |", "|---|---|---|",
        _row(["Elo baseline", f"{res['elo']['ece']:.5f}",
              f"{res['elo']['brier']:.5f}"]),
        _row(["Elo + EPA + rest, isotonic (published)",
              f"**{res['independent']['ece']:.5f}**",
              f"{res['independent']['brier']:.5f}"]),
        _row(["de-vigged market", f"{res['market']['ece']:.5f}",
              f"{res['market']['brier']:.5f}"]),
    ])


def _tbl_reliability(f):
    rows = ["| predicted band | n | mean predicted | actual frequency | gap |",
            "|---|---|---|---|---|"]
    for r in f["reliability_independent"]:
        rows.append(_row([r["bucket"], r["n"], f"{r['predicted'] * 100:.2f}%",
                          f"{r['actual'] * 100:.2f}%",
                          f"{r['gap'] * 100:+.2f} pts"]))
    return "\n".join(rows)


def _tbl_selectivity(f):
    """Every edge bar we measured, on both line sources, shipped bar in bold.

    The bold row follows selectivity.rule_threshold_pts rather than being
    hardcoded, so moving the bar moves the emphasis with it.
    """
    a = f["selectivity"]["evaluation_a"]
    b = f["selectivity"]["evaluation_b"]
    ship = float(f["selectivity"]["rule_threshold_pts"])
    rows = ["| edge bar | A: nflverse 2016-2025 | B: real closes 2023-2025 |",
            "|---|---|---|"]
    for ta, tb in zip(a["thresholds"], b["thresholds"]):
        if ta["edge"] != tb["edge"]:
            raise FigureError("the two samples measured different edge bars")
        edge = ta["edge"]
        label = "every game" if edge == 0 else f"\u2265 {edge:g} points"
        cells = [label] + [f"{t['all']['record']} ({t['all']['pct'] * 100:.2f}%)"
                           for t in (ta, tb)]
        if edge == ship:
            cells = [f"**{c}**" for c in cells]
        rows.append(_row(cells))
    return "\n".join(rows)


def _record(entry):
    """A season with no pushes prints W-L, not W-L-0."""
    rec = entry["record"]
    return rec[:-2] if rec.endswith("-0") else rec


def _tbl_by_season(f):
    """Two columns of five seasons, losers included - the point of the table."""
    seasons = sorted(f["selectivity"]["evaluation_a"]["by_season"].items())
    half = (len(seasons) + 1) // 2
    rows = ["| season | record | | season | record |", "|---|---|---|---|---|"]
    for (ly, lv), (ry, rv) in zip(seasons[:half], seasons[half:]):
        rows.append(_row([ly, _record(lv), "", ry, _record(rv)]))
    return "\n".join(rows)


TABLES = {"backtest_a": _tbl_backtest_a, "backtest_b": _tbl_backtest_b,
          "ece": _tbl_ece, "reliability": _tbl_reliability,
          "selectivity": _tbl_selectivity, "by_season": _tbl_by_season}


# The middle bands, which the prose about the reliability table reads. Derived
# here rather than typed into the prose, and derived FROM the published figures
# rather than measured again — nothing new is computed, the rows are just
# summed. Named as its own block so a reader of the markdown can see that
# "2,290 of the 2,671" is a sum of the table directly above it.
_MID_BANDS = ("0.3-0.4", "0.4-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8")


def _derive(figures):
    # Absent entirely: leave it out, and any {{fig:reliability_mid...}} token
    # then fails as an unknown figure, which is the right failure. Present but
    # incomplete is the dangerous case and is caught below.
    if "reliability_independent" not in figures:
        return figures
    mid = [r for r in figures["reliability_independent"]
           if r["bucket"] in _MID_BANDS]
    if len(mid) != len(_MID_BANDS):
        raise FigureError(
            f"reliability_independent is missing middle bands: expected "
            f"{list(_MID_BANDS)}, found {[r['bucket'] for r in mid]}")
    gaps = [r["gap"] for r in mid]
    return dict(figures, reliability_mid={
        "n": sum(r["n"] for r in mid),
        "min_gap": min(gaps), "max_gap": max(gaps),
    })


# ---------------------------------------------------------------------------
# The live commitment, for /verify.
#
# /verify is the page that teaches a reader to download two files, re-hash them
# themselves, and treat a mismatch as having caught us. Every figure on it was
# hand-typed, and after the 2026-09-01 re-seal every one of them disagreed with
# the files the page hands the reader: it printed the v3 root while
# /data/2026-W01-nfl.commitment.json served v4, its sample output contradicted
# its own JSON block, and its worked inclusion proof was still the v1
# sixteen-prediction tree. A walkthrough that does not reproduce is worse on
# that page than on any other.
#
# So the walkthrough is COMPUTED here, on every build, from data/ledger: the
# canonical string, the leaf, the inclusion proof and the tampered root are all
# re-derived from the published predictions rather than pasted from a terminal.
# Hard rule 5 applied to the page that argues hardest for it.
#
# Resolved from the VERSIONED commitment history, never from the unversioned
# data/ledger/<slate>.commitment.json, which is a legacy pointer and is
# currently two versions behind the seal the site actually serves.
# ---------------------------------------------------------------------------

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _human_date(iso: str) -> str:
    """'2026-09-01T23:28:44+00:00' -> '1 September 2026'.

    Assembled by hand rather than with strftime("%-d %B %Y"): %-d is a glibc
    extension that raises ValueError on Windows, where this generator also has
    to run. engine/alert_lifecycle.py already carries that bug.
    """
    d = datetime.fromisoformat(iso)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def _leaf(prediction: dict) -> str:
    return hashlib.sha256(b"\x00" + canonical(prediction)).hexdigest()


def _level_sizes(n: int) -> list[int]:
    """Node counts at each level, odd levels duplicating their tail."""
    sizes = [n]
    while sizes[-1] > 1:
        sizes.append((sizes[-1] + sizes[-1] % 2) // 2)
    return sizes


def slate_figures() -> dict:
    """Everything /verify prints, recomputed from the newest sealed slate.

    Raises rather than returning a stale or unverifiable figure. A page that
    tells a reader "a mismatch means you caught us" may not itself ship a
    mismatch.
    """
    ids = sorted({p.name.split(".commitment")[0]
                  for p in LEDGER.glob("*.commitment.v*.json")})
    if not ids:
        raise FigureError(
            "data/ledger holds no versioned commitment, so /verify has no "
            "slate to walk through. Seal one before building the site.")
    slate_id = ids[-1]
    history = commitment_history(slate_id, LEDGER)
    c = history[-1]
    version = int(c["version"])

    reveal_path = LEDGER / f"{slate_id}.reveal.v{version}.json"
    if not reveal_path.exists():
        raise FigureError(f"{slate_id} is committed at v{version} but "
                          f"{reveal_path.name} is missing")
    reveal = json.loads(reveal_path.read_text(encoding="utf-8"))
    preds = reveal["predictions"]
    leaves = [_leaf(p) for p in preds]

    # The page's own claim, checked before the page is allowed to make it.
    if leaves != reveal["leaves"]:
        raise FigureError(f"{slate_id} v{version}: the leaf hashes we recompute "
                          f"are not the ones published in the reveal file")
    root = merkle_root(leaves)
    if root != c["merkle_root"] or root != reveal.get("merkle_root", root):
        raise FigureError(f"{slate_id} v{version}: recomputed root {root} is "
                          f"not the committed root {c['merkle_root']}")
    if len(preds) != c["n_predictions"]:
        raise FigureError(f"{slate_id} v{version}: {len(preds)} predictions "
                          f"revealed, {c['n_predictions']} committed")

    # ...and the copy a reader downloads must BE that commitment. This is the
    # check that /ledger did not have on 2026-09-01, when the site served v4
    # while every page rendered from it still said v3.
    served = json.loads((SERVED / f"{slate_id}.commitment.json")
                        .read_text(encoding="utf-8"))
    if served.get("merkle_root") != root or int(served.get("version", 0)) != version:
        raise FigureError(
            f"/data/{slate_id}.commitment.json serves root "
            f"{served.get('merkle_root')} (v{served.get('version')}), but the "
            f"ledger's latest commitment is {root} (v{version}). /verify would "
            f"tell a reader to download a file that disagrees with the page.")

    proof = merkle_proof(leaves, 0)
    if not verify_proof(leaves[0], proof, root):
        raise FigureError("the worked inclusion proof does not chain to the root")

    tampered = merkle_root([_leaf(dict(p, probability=0.99)) if i == 0 else lh
                            for i, (p, lh) in enumerate(zip(preds, leaves))])
    first = canonical(preds[0]).decode()
    sizes = _level_sizes(len(leaves))

    return {
        "id": slate_id,
        "version": version,
        "n_predictions": len(preds),
        "merkle_root": root,
        "root_abbrev": root[:7] + "...",
        "committed_at": c["committed_at"],
        "earliest_kickoff": c["earliest_kickoff"],
        "sealed_human": _human_date(c["committed_at"]),
        "days_before_kickoff": (datetime.fromisoformat(c["earliest_kickoff"])
                                - datetime.fromisoformat(c["committed_at"])).days,
        "commitment_json": json.dumps(c, indent=2, sort_keys=True),
        "sample_output": "\n".join([
            f"predictions revealed : {len(preds)}",
            f"predictions committed: {c['n_predictions']}",
            f"committed at         : {c['committed_at']}",
            f"earliest kickoff     : {c['earliest_kickoff']}",
            "",
            f"published root       : {c['merkle_root']}",
            f"recomputed root      : {root}",
            "",
            "VERIFIED",
        ]),
        "first_canonical": first,
        "first_canonical_len": len(first),
        "first_leaf": leaves[0],
        "first_probability": preds[0]["probability"],
        "tampered_root_abbrev": tampered[:10] + "...",
        "proof_json": "[\n" + ",\n".join(
            "  " + json.dumps(s, separators=(", ", ": ")) for s in proof) + "\n]",
        "proof_len": len(proof),
        "proof_shrink": ", ".join(f"{a} becomes {b}"
                                  for a, b in zip(sizes, sizes[1:])),
    }


def substitute(text, figures):
    """Resolve every {{fig:}} and {{table:}} token, or raise FigureError."""
    figures = _derive(figures)
    def one(m):
        kind, name, spec, token = m.group(1), m.group(2), m.group(3), m.group(0)
        if kind == "table":
            if spec is not None:
                raise FigureError(f"{token}: a table takes no format")
            if name not in TABLES:
                raise FigureError(f"{token}: unknown table. Known: {sorted(TABLES)}")
            return TABLES[name](figures)
        return _fmt(_lookup(figures, name, token), spec, token)

    return _TOKEN.sub(one, text)


def build_markdown_pages() -> list[str]:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"]
    )
    figures = json.loads(FIGURES.read_text(encoding="utf-8"))
    if "slate" in figures:
        raise FigureError(
            "_figures.json now has a 'slate' key, which would shadow the live "
            "commitment /verify is built from. Rename one of them.")
    figures = dict(figures, slate=slate_figures())
    built = []
    for slug, src, title, desc in PAGES:
        path = CONTENT / src
        if not path.exists():
            print(f"  SKIP {slug}: {src} missing")
            continue
        md.reset()
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end != -1:
                text = text[end + 5:]
        text = substitute(text, figures)
        html = frost(md.convert(text))
        (PUBLIC / f"{slug}.html").write_text(render(slug, title, desc, html), encoding="utf-8")
        built.append(slug)
        print(f"  built /{slug}")
    return built


def build_ledger() -> None:
    """Render every committed slate straight from data/ledger/."""
    # Versioned files only. The unversioned legacy pair was deleted on
    # 2026-09-02; falling back to it rendered a two-seal-stale root onto the
    # one page whose job is proving roots do not quietly change.
    slate_ids = sorted({p.name.split(".commitment")[0]
                        for p in LEDGER.glob("*.commitment.v*.json")})

    slates = []
    now = datetime.now(timezone.utc)
    for slate_id in slate_ids:
        history = commitment_history(slate_id, LEDGER)
        if not history:
            raise FileNotFoundError(
                f"{slate_id} has versioned commitment files that do not parse")
        c = history[-1]
        kickoff = datetime.fromisoformat(c["earliest_kickoff"])
        public_state = "revealed" if kickoff < now else "sealed"
        slates.append({**c, "state": public_state, "history": history})

    rows = []
    for s in sorted(slates, key=lambda x: x["slate_id"], reverse=True):
        # Frost means sealed, so a SEALED slate takes the shared .frost chip
        # rather than a generic badge. REVEALED has thawed — it is graded and
        # checkable — and keeps .badge, which is the only state left using it.
        if s["state"] == "revealed":
            chip = '<span class="badge revealed">REVEALED</span>'
        else:
            chip = '<span class="frost">SEALED</span>'
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
<div class="card rimlit">
  <div class="row"><span class="k">slate</span>
    <span><strong>{s['slate_id']}</strong>
    {chip}</span></div>
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
<p>Every slate we have ever committed, newest first. A <span class="frost">SEALED</span>
slate has had its Merkle root published before kickoff; its predictions are
published alongside it, and the root proves they cannot be altered afterwards.
A <span class="badge revealed">REVEALED</span> slate has been graded after the
games settled and can be recomputed by anyone.</p>
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


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    print("building site...")
    build_markdown_pages()
    try:
        build_ledger()
    except Exception as e:                       # noqa: BLE001
        # A ledger-render bug must not halt every deploy: keep the previous
        # ledger.html on disk and say so loudly in the log.
        print(f"  LEDGER BUILD FAILED — keeping previous ledger.html: {e!r}")
    print("done")


if __name__ == "__main__":
    main()
