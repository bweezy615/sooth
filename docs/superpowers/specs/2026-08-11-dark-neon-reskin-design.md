# Spec: dark-neon reskin (deepbetting.io-inspired)

**Date:** 2026-08-11 · **Owner:** Branden · **Decisions:** dark-neon reskin, keep sooth's
honest voice, whole site in one pass. Reference: deepbetting.io. Built autonomously while
Branden was out; this doc records the choices for his review.

## Direction
Adopt deepbetting.io's **visual language** (near-black, neon cyan+magenta, chunky rounded
display type, glowing data cards) but NOT its AI-hype **voice**. Sooth stays honest:
"we show you the best number," % beat-the-close, compliance helpline on every page.

## Why it's cheap + low-risk
`sooth.css` (~247 lines) is token-driven: nearly every color is a `var(--token)` off a single
`:root`. Redefining the tokens flips all 19 pages at once. Only a handful of hardcoded light
values need fixing (header glass, accent-button text, mark SVG, theme-color).

## Tokens
**Color** (dark, but data-semantics preserved — green still = gain, not decoration):
- `--bg` #08090D (Void) · `--bg-2` #101219 (Carbon) · `--bg-3` #171A23 (Slate)
- `--line` rgba(255,255,255,.08) · `--line-2` rgba(255,255,255,.14)
- `--ink` #EDEFF5 · `--ink-2` #AEB4C2 · `--muted` #7A8194 · `--dim` #565E70
- `--iris` #22D3EE (Cyan — UI accent/links/active)
- `--brand` #F0338D (Magenta — CTA + gradient partner) [new token]
- `--pos`/`--pos-text` #22E5A0 (Volt — gain) · `--neg` #FF5470 · `--warn` #FFB020
- `--beam` linear-gradient(90deg, cyan → magenta) [new token — the signature]

**Type:** `Sora` 700/800 display (added) + `Archivo` UI (kept) + `JetBrains Mono` data (kept).

## Signature: the edge beam
Sooth's thesis = books price the same bet differently. Upgrade the existing `.gainbar`/`.gtrack`
into a glowing cyan→magenta gradient bar showing the worst→best price gap, edge number glowing.
The one bold element; it visualizes the actual product. Everything else stays quiet.

## Ambient
One fixed, very-subtle radial glow pair (cyan top-left, magenta bottom-right) behind content
via a `body::before`. No per-element glow spam. Reduced-motion respected; no new JS animation.

## Scope of edits
- `assets/sooth.css` — rewrite `:root`, fix hardcoded light values, add glow/gradient utilities,
  upgrade `.gainbar`, `.hd-cta`/`.btn-accent` to neon gradient, ambient `body::before`.
- `assets/shell.js` — mark-SVG stroke colors + `theme-color` meta to dark.
- `index.html` — add Sora to the font link; hero: gradient accent word + league strip +
  edge-beam demo; keep the honest headline copy verbatim.
- Other 18 pages inherit via tokens; spot-check contrast, fix any page-local light assumptions.

## Guardrails
Honest copy unchanged. Compliance footer stays quiet/legible (no neon). Data meaning intact.
Verify every page in a browser before commit. Push to `redesign/dark-neon` + open PR; do NOT
merge to main — Branden reviews. Separate from the `audit/p2-cleanup` PR.

## Out of scope
Copywriting overhaul, new pages, backend/data, the link-hygiene items (own PR).
