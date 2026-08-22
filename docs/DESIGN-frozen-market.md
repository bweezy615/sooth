# FROZEN MARKET — the sooth.bet visual concept

Derived from the two brand promos the owner produced (2026-08-22). Agents
working on this cannot see those images; everything they establish is written
down here. **This file is the authority. The images are not available to you.**

---

## What the promos actually show

**Promo 1 — the coin.** A circular black medallion, textured like wet stone,
ringed by a thick band of *cracked, dripping ice* with water beading and
running off it. Inside the ice ring, a thin **teal hairline arc** traces the
top-left of the circle — a single lit rim, not a full border. Centred: an
abstract mark in brushed cool-white (a squared-off S / double-track glyph, wet,
with water droplets on its surface) and a small **solid teal circular pip** to
its lower right. Beneath, the wordmark **`sooth.bet`** — lowercase, geometric,
tight tracking, `sooth` in cool white, **`.bet` in teal**.

**Promo 2 — the block.** The product rendered as a slab of dark glass **frozen
inside a melting block of clear ice**, standing on a wet black floor with
reflections. Above it, `sooth.bet` huge, lowercase, white with the teal `.bet`,
and under it a widely letterspaced mono line:
`MARKET INTELLIGENCE.` in grey, `HONEST EDGE.` in teal.

On the slab's face: `sooth.bet` small, a teal hairline rule, the label
`MARKET INTELLIGENCE DESK`, then a five-item capability list, each prefixed
with a small **teal ▸ triangle**, in letterspaced mono caps:

```
▸ LIVE PRICING
▸ AI ANALYSIS
▸ RESEARCH LAB
▸ PICK ENGINE
▸ PROOF LEDGER
```

To their right, a data graphic: a faint teal **wireframe mesh** (a low, rolling
surface) with vertical **stems rising from it, each capped by a small dot** —
some teal, some white. A lollipop/stem plot over a mesh floor.

---

## The idea this gives the product

**A betting market is liquid. Sooth freezes it.**

Every price on the board is in motion. What the pick engine does is take a
slice of that motion and *freeze* it: at seal time the slate stops moving, gets
hashed into a Merkle root, anchored to a public GitHub commit, and can no
longer be edited by us or anyone. At first kickoff it *thaws* and everyone sees
it.

**Liquid → frozen → thawed** is simultaneously what the product does and what
the artwork shows. The ice is not a texture we are applying; it is the seal.

## The four rules (already encoded at the top of `assets/desk.css`)

1. **Teal is the signal.** One hue. It marks a better-than-market number and it
   marks chrome that belongs to us. `--up` is now the *same* teal as `--brand`,
   deliberately: "favourable price" and "the sooth signal" are one idea. Red
   (`--dn`) is the only other hue. Amber survives *only* for staleness/caution.
2. **Frost means sealed.** Anything committed-but-not-revealed renders as ice.
3. **Glass, not cards.** Thin, dark, lit along the top edge. Never a flat grey
   box with a big radius.
4. **The ground is cold and nearly black.** `#06080A`.

## Tokens available to you (do NOT redefine these)

```
--g0 #06080A   --g1 #0B0F13   --g2 #111820   --g3 #18222B
--ink #F0F5F6  --ink2 #AEBDC2 --mut #7E8D93  --dim #546268
--brand #2DD4A7        --brand-hi #5BF0D4    --brand-dim rgba(45,212,167,.10)
--up #2DD4A7 (= brand) --dn #FF6B6B          --amber #E2A94A
--frost #BFEAF2        --frost-dim           --frost-rim
--sans 'Archivo'       --mono 'IBM Plex Mono'
--hair --hair2 --r --wrap  + the --t-* motion scale
```

## Primitives available to you (already built — reuse, don't reinvent)

| Class | What it is | Use for |
|---|---|---|
| `.frost` | Small ice chip: teal-white text, faceted gradient, diamond pip | Any SEALED / COMMITTED / NOT-YET-REVEALED state |
| `.frosted` | The same treatment on a whole surface | A locked slate, an unrevealed panel |
| `.rimlit` | A teal hairline that catches light across the top edge | The one "lit rim" moment on a hero surface |
| `.caps` | The promo's `▸ CAPABILITY` list, mono caps, teal triangle | Any list naming what a surface does |
| `.itab` / `.feed` / `.mkt` | Existing glass slabs — already restyled | Data surfaces |
| `.tl` | Letterspaced mono caption | Labels, as everywhere |

## Wordmark

`sooth<i>.bet</i>` — lowercase, `.bet` in teal (`.brand b i` handles it).
Already changed in `desk.js`'s `header()`. Do not reintroduce uppercase
"SOOTH" anywhere.

## Hard constraints — violating any of these is a failed task

- **Do NOT edit `site/public/assets/desk.css` or `site/public/assets/desk.js`.**
  They are shared and owned by the lead. If you need a new shared primitive,
  say so in your report instead of adding it.
- **Do not change any number, claim, record, or piece of factual copy.** The
  49.5% figure, the break-even, sample sizes, the compliance footer, and the
  disclaimers are load-bearing and legally checked. Visual work only.
- **Do not add a second hue.** No purple, no blue, no gradient backdrop.
- **Do not add rounded cards, big border-radii, or drop-shadow "elevation".**
- **Do not break the mobile work just shipped**: tables stack below 720px via
  `Desk.stack()`; nothing may reintroduce a horizontal scroller.
- **No new dependencies, no external assets, no images.** Pure CSS.
- Keep every page's existing structure, ids and script behaviour working. This
  is a re-skin, not a rebuild.
- Preserve accessibility: contrast on `--g0`, visible focus, real labels.

## What good looks like

The page should feel like the slab in promo 2: cold, dark, precise, one teal
signal, with the sealed things visibly under ice. Restrained — the promos are
mostly black. Teal is a *highlight*, covering a few percent of the surface, not
a theme colour splashed on panels.
