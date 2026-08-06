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

CSS = """
:root{--bg:#080B16;--panel:#111629;--panel-2:#0B1022;--line:#1E2540;
--ink:#EEF1F8;--muted:#8C96B2;--dim:#5D6786;--accent:#4ade80;--warn:#fbbf24;
--bad:#f87171;--link:#38BDF8;
--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 Inter,system-ui,-apple-system,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:0 20px}
a{color:var(--link)}
header{border-bottom:1px solid var(--line);position:sticky;top:0;
background:color-mix(in srgb,var(--bg) 88%,transparent);
backdrop-filter:blur(12px);z-index:10}
nav{display:flex;align-items:center;gap:22px;height:60px;
max-width:820px;margin:0 auto;padding:0 20px}
.brand{font-weight:700;letter-spacing:-.02em;font-size:17px;
text-decoration:none;color:var(--ink);display:flex;align-items:center;gap:8px}
.brand .dot{width:9px;height:9px;border-radius:50%;background:var(--accent)}
nav .spacer{flex:1}
nav a.l{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500}
nav a.l:hover{color:var(--ink)}
.prose{padding:44px 0 60px}
.prose h1{font-size:clamp(28px,4.5vw,38px);line-height:1.15;
letter-spacing:-.03em;margin:0 0 26px;font-weight:700}
.prose h2{font-size:21px;letter-spacing:-.01em;margin:40px 0 12px;
padding-top:20px;border-top:1px solid var(--line);font-weight:650}
.prose h3{font-size:17px;margin:26px 0 8px;font-weight:650}
.prose p{margin:0 0 15px;color:var(--ink)}
.prose li{margin:0 0 7px}
.prose strong{font-weight:650}
.prose code{font-family:var(--mono);font-size:13px;background:var(--panel-2);
border:1px solid var(--line);border-radius:4px;padding:1px 5px}
.prose pre{background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:15px 17px;overflow-x:auto;font-size:12.5px;
line-height:1.55}
.prose pre code{background:none;border:0;padding:0;font-size:12.5px}
.prose table{width:100%;border-collapse:collapse;font-size:14px;margin:18px 0;
display:block;overflow-x:auto}
.prose th{text-align:left;font-weight:600;color:var(--dim);font-size:11px;
text-transform:uppercase;letter-spacing:.07em;padding:0 12px 9px;
border-bottom:1px solid var(--line);white-space:nowrap}
.prose td{padding:10px 12px;border-bottom:1px solid var(--line)}
.prose blockquote{margin:18px 0;padding:14px 18px;background:var(--panel-2);
border-left:3px solid var(--warn);border-radius:0 8px 8px 0}
.prose blockquote p{margin:0}
.prose hr{border:0;border-top:1px solid var(--line);margin:34px 0}
footer{border-top:1px solid var(--line);padding:30px 0 54px;
color:var(--dim);font-size:12.5px}
footer p{max-width:80ch;margin:0 0 9px}
.mono{font-family:var(--mono)}
.hash{font-family:var(--mono);font-size:12px;color:var(--accent);
word-break:break-all}
.badge{display:inline-block;font-size:10.5px;font-weight:700;
letter-spacing:.05em;padding:2px 7px;border-radius:4px;
border:1px solid var(--line);color:var(--muted)}
.badge.sealed{color:var(--warn);border-color:var(--warn)}
.badge.revealed{color:var(--accent);border-color:var(--accent)}
.card{background:var(--panel);border:1px solid var(--line);
border-radius:12px;padding:17px 19px;margin:0 0 13px}
.card .row{display:flex;gap:13px;padding:4px 0;flex-wrap:wrap;font-size:13px}
.card .k{color:var(--dim);min-width:118px;font-family:var(--mono);font-size:12px}
"""

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {brand}</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#080B16">
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<header><nav>
  <a class="brand" href="/"><span class="dot"></span>{brand}</a>
  <span class="spacer"></span>
  <a class="l" href="/">Board</a>
  <a class="l" href="/props">Props</a>
  <a class="l" href="/edges">Edges</a>
  <a class="l" href="/tools">Tools</a>
  <a class="l" href="/trust">Trust</a>
</nav></header>
<div class="wrap"><div class="prose">
{body}
</div></div>
<footer><div class="wrap">
<p><strong>Entertainment and analysis only. We do not accept, place, or
facilitate wagers</strong>, and we hold no customer funds. Not affiliated with
the NFL or any sportsbook.</p>
<p>Past performance does not indicate future results. Our published backtest
shows a loss against the closing market. Nothing here is a recommendation to
bet. 21+, where lawful.</p>
<p>If gambling is causing harm, the NCPG helpline is
<strong>1-800-522-4700</strong>, available 24/7.</p>
<p style="margin-top:16px"><a href="/methodology">Methodology</a> ·
<a href="/verify">Verify</a> · <a href="/ledger">Ledger</a> ·
<a href="/disclaimers">Disclaimers</a></p>
</div></footer>
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
        text = path.read_text()
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end != -1:
                text = text[end + 5:]
        html = md.convert(text)
        (PUBLIC / f"{slug}.html").write_text(render(slug, title, desc, html))
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
            history = [json.loads((LEDGER / f"{slate_id}.commitment.json").read_text())]
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
               "verifiable afterward. Nothing edited, nothing removed.", body)
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
