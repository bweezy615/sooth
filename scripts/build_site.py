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

# ⚠ DRIFT WARNING — read before running this script.
#
# build_ledger() and friends REGENERATE site/public/{ledger,methodology,verify,
# disclaimers}.html from this constant plus an f-string body. Those four files
# were hand-re-skinned to the FROZEN MARKET concept on 2026-08-22
# (docs/DESIGN-frozen-market.md), and verify.html in particular gained frost
# treatment on its commitment blocks that this generator knows nothing about.
#
# The palette below has been ported so a rebuild no longer reverts the colours
# and type. It will still discard any hand-edit to the four pages' STRUCTURE.
# Before running: diff the generated output against what is on disk, or port
# the structural change up into here first.
CSS = """
:root{--bg:#06080A;--panel:#0B0F13;--panel-2:#18222B;--line:rgba(190,222,228,.085);
--line-2:rgba(190,222,228,.17);
--ink:#F0F5F6;--muted:#7E8D93;--dim:#546268;--accent:#2DD4A7;--warn:#E2A94A;
--bad:#FF6B6B;--link:#2DD4A7;--frost:#BFEAF2;--frost-rim:rgba(191,234,242,.34);
--mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);
font:15px/1.7 Archivo,system-ui,-apple-system,sans-serif;
-webkit-font-smoothing:antialiased;
background:radial-gradient(1100px 480px at 50% -180px,rgba(45,212,167,.055),transparent 72%),var(--bg)}
.wrap{max-width:860px;margin:0 auto;padding:0 24px}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:2px}
header{border-bottom:1px solid var(--line);position:sticky;top:0;
background:rgba(6,8,10,.86);backdrop-filter:blur(10px);z-index:10}
nav{display:flex;align-items:center;gap:18px;height:52px;
max-width:1360px;margin:0 auto;padding:0 28px}
.brand{font:600 17px/1 Archivo,sans-serif;letter-spacing:-.02em;text-transform:none;
text-decoration:none;color:var(--ink);display:flex;align-items:center;gap:9px}
.brand:hover{text-decoration:none}
.brand .dot{width:8px;height:8px;border-radius:50%;background:var(--accent);
box-shadow:0 0 10px rgba(45,212,167,.55)}
.brand i{font-style:normal;color:var(--accent)}
nav .spacer{flex:1}
nav a.l{color:var(--muted);text-decoration:none;font:600 11.5px/1 Archivo,sans-serif;
letter-spacing:.06em;text-transform:uppercase;padding:7px 10px;border-radius:3px}
nav a.l:hover{color:var(--ink);background:var(--panel);text-decoration:none}
.prose{padding:40px 0 60px}
.prose h1{font-size:clamp(24px,3.6vw,32px);line-height:1.15;
letter-spacing:-.02em;margin:0 0 24px;font-weight:760}
.prose h2{font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;
color:var(--muted);margin:42px 0 14px;padding-top:22px;border-top:1px solid var(--line)}
.prose h3{font-size:15px;margin:26px 0 8px;font-weight:650;color:var(--ink)}
.prose p{margin:0 0 15px;color:#B4BAC4}
.prose li{margin:0 0 7px;color:#B4BAC4}
.prose strong{font-weight:650;color:var(--ink)}
.prose code{font-family:var(--mono);font-size:12.5px;background:var(--panel-2);
border:1px solid var(--line-2);border-radius:4px;padding:1px 5px;color:var(--ink)}
.prose pre{background:var(--panel);border:1px solid var(--line);
border-radius:3px;padding:15px 17px;overflow-x:auto;font-size:12px;
line-height:1.55;box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}
.prose pre code{background:none;border:0;padding:0;font-size:12px}
.prose table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0;
display:block;overflow-x:auto;font-family:var(--mono);
font-variant-numeric:tabular-nums}
.prose th{text-align:left;font-weight:600;color:var(--dim);font-size:9.5px;
text-transform:uppercase;letter-spacing:.12em;padding:0 12px 9px;
border-bottom:1px solid var(--line-2);white-space:nowrap;font-family:var(--mono)}
.prose td{padding:9px 12px;border-bottom:1px solid var(--line);color:#B4BAC4}
.prose blockquote{margin:18px 0;padding:14px 18px;background:var(--panel);
border-left:2px solid var(--warn);border-radius:0 3px 3px 0}
.prose blockquote p{margin:0}
.prose hr{border:0;border-top:1px solid var(--line);margin:34px 0}
footer{border-top:1px solid var(--line);padding:26px 0 44px;
color:var(--dim);font-size:11.5px;line-height:1.7}
footer p{max-width:86ch;margin:0 0 9px}
footer b,footer strong{color:var(--muted)}
footer a{color:var(--muted)}
.mono{font-family:var(--mono)}
.hash{font-family:var(--mono);font-size:11.5px;color:var(--accent);
word-break:break-all}
.badge{display:inline-block;font:700 9.5px/1 var(--mono);
letter-spacing:.08em;padding:3px 7px;border-radius:4px;
border:1px solid var(--line-2);color:var(--muted);vertical-align:2px}
.badge.sealed{color:var(--warn);border-color:var(--warn)}
.badge.revealed{color:var(--accent);border-color:var(--accent)}
.card{background:linear-gradient(180deg,#15181D 0%,#101216 55%,#0D0F12 100%);
border:1px solid var(--line);border-radius:3px;padding:17px 19px;margin:0 0 13px;
box-shadow:inset 0 1px 0 rgba(255,255,255,.08),inset 0 -1px 0 rgba(0,0,0,.5),
0 12px 30px -20px rgba(0,0,0,.85)}
.card .row{display:flex;gap:13px;padding:4px 0;flex-wrap:wrap;font-size:12.5px}
.card .k{color:var(--dim);min-width:118px;font-family:var(--mono);font-size:10.5px;
letter-spacing:.06em;text-transform:uppercase;padding-top:2px}
"""

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
<meta property="og:image" content="https://sooth.bet/og.png">
<meta property="og:url" content="{domain}/{slug}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<!-- desk.css first so this page's own rules below still win on any clash;
     it is here for the shared header and footer that desk.js injects. -->
<link rel="stylesheet" href="/assets/desk.css">
<style>{css}</style>
</head>
<body>
<div class="wrap"><div class="prose">
{body}
</div></div>
<script src="/assets/desk.js"></script>
<script>window.Desk.mount("");</script>
<script>if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js");</script>
</body>
</html>
"""


def render(slug: str, title: str, description: str, body: str) -> str:
    return SHELL.format(
        title=title, brand=BRAND, description=description, domain=DOMAIN,
        slug=slug, css=CSS, body=body,
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
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end != -1:
                text = text[end + 5:]
        html = md.convert(text)
        (PUBLIC / f"{slug}.html").write_text(render(slug, title, desc, html), encoding="utf-8")
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
