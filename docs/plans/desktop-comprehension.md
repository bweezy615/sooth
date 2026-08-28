# Making the desktop site legible to a bettor

Written 2026-08-28. Branden: "redesign our frontend to make it more simple to
understand for our customers."

## The finding that shapes everything

**The mobile site and the desktop site are different products, and mobile is
the right one.** One `index.html`, one breakpoint at 859px, both layouts in the
DOM.

Mobile opens on: sport rail (ALL 47 / NFL 8 / CFB 8 / MLB 15) → ask box →
NEXT UP with best price per side → BIGGEST GAPS, subtitled "SHOPPING PAYS
MOST". Five items in a thumb-reachable bottom nav. That is a bettor's tool and
it answers "what should I look at today?".

Desktop opens on a dashboard about the model. Reading order of `#main` today:

    hero → stats → [ Model calibration | Top market movers | Where books
    disagree ] → pulse

The largest numbers above the fold are `Calibration error 3.07%` and
`Brier score 0.222`. Both describe how well the model is calibrated. Neither
is a thing a visitor can act on, and one of them ("0.25 is a coin flip") is
only meaningful to someone who already knows what a Brier score is.

So this is not a redesign from scratch. It is porting an information
architecture that already exists and already works onto the wider screen.

## What the customer is here to do

Branden's answer, and the thing the landing surface must serve:

> Find picks/props for everyday slates. Best edge / line movement.

"What is worth looking at today", not "should I trust this model". Trust is
the reason to stay; it is not the reason to arrive, and it currently occupies
the whole first screen.

## What must not be lost

This site's position is that it only makes checkable claims. Simplifying the
words must not simplify away the claim they carry.

- **The empty state on `/picks` stays honest.** When nothing clears the
  4-point bar the page says the sealed slate contains no play at all. That
  sentence is the product working, not a gap to fill. A landing page that
  promises daily picks and then has none is worse than one that says plainly
  that today has none.
- **Zero win-rate claims.** "Best edge" describes distance from the consensus
  price. It is not a claim that the pick wins, and no new copy may imply it.
- **No published number moves out of `published_figures.py`.** Anything the
  landing page quotes is read from a payload, not typed.
- **Demoting the model figures is not hiding them.** They move to a section a
  visitor reaches deliberately, and the honest summary — our model does not
  beat the closing line — stays visible on the landing page in words a
  non-quant can read.
- **The generated pages are off limits to hand edits.** `build_site.py` owns
  methodology, verify, disclaimers and ledger; `tests/test_build_site.py`
  fails if the tree and the generator disagree.

## Phase 1 — the desktop landing becomes today's slate

Reorder `#main` in `site/public/index.html` to mirror the mobile order:

1. **Sport rail.** `desk.js` already has `sportRail()`; desktop never calls it.
2. **Tonight's board** — next games, best price per side, which book has it.
3. **Best edges** — the biggest gaps, with the mobile subtitle's honesty:
   shopping is where the money is, and it does not require the model to be right.
4. **Line movement** — today's `Top market movers` panel, with the bug below fixed.
5. **Picks and props for the slate**, including the honest empty state.
6. **Proof** — calibration, Brier, ATS record. Below the fold, plainly labelled.

**Bug to fix in the same phase.** `#movers` on the homepage prints raw
`side_a` / `side_b` to visitors. `edges.html:333`, `game.html:177` and
`market.html:288` each carry the same `name()` helper that swaps those for the
home and away team; the homepage panel is the one place that never got it.
This is a database field name on the landing page of a site selling clarity.

## Phase 2 — the navigation says what things are

Desktop sidebar today is ten items in internal vocabulary: Dashboard, Live
Markets, Analyst, Research, Pick Engine, Record, Ledger, Movement, Props,
Alerts. "Analyst", "Pick Engine", "Ledger" and "Movement" do not tell a
visitor what they get. Ten also exceeds the 7±2 that a person can hold.

Mobile already ships a five-item nav (BOARD, PICKS, PROOF, ANALYST, ALERTS).
Desktop should not disagree with mobile about what the site contains. Group
and rename to match, keeping every existing URL working — renaming a link is
a copy change, not a routing change.

## Phase 3 — the numbers explain themselves

- `FAIR +181` and `+2.4 PTS` appear on the card that carries the entire
  line-shopping benefit, and nothing on the page says what either means. This
  is the single highest-value explanation on the site.
- Jargon spread, measured across the 23 pages: **ATS on 14, ECE on 12,
  de-vig on 11, walk-forward on 7, Merkle on 7, CLV on 6, Brier on 5.** Rule:
  defined in plain words at first use on each page, or replaced by the plain
  words entirely where the term is not load-bearing.
- Prefer replacing over glossing. "Against the spread" costs three words;
  "ATS" costs a visitor who does not already know.

## Acceptance

- Every phase browser-verified at 375px and desktop, and against production
  after deploy.
- `bash scripts/check.sh` green before every push, including
  `tests/frontend/desk.selfcheck.js` and `tests/test_build_site.py`.
- **The service worker cache name is renamed in the same commit as any CSS or
  shell change.** `tests/test_service_worker.py` enforces it, and it has
  already caught one change that would have left returning visitors on the old
  version while the fix looked shipped.
- No new hand-typed figure anywhere.

## Out of scope

Rebuilding the IA from scratch. Touching the generated pages. The `/market`
headline and the `/disclaimers` §7 wording (both reserved to Branden and still
unanswered). The Sept 1 paywall flip — noted only because it lands four days
after this work and `/picks` currently says the site is free.
