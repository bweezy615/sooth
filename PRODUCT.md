# PRODUCT.md — Sooth

Product truth only. No visual decisions live here.

## What it is

Sooth reads every major US sportsbook and publishes two numbers for every game:

1. **Best available price** — the most generous quote on a side, and which book has it.
2. **Fair line** — the de-vigged consensus across all books. Median implied
   probability per side, normalised so the sides sum to 1, which strips out the
   bookmaker's margin.

It also runs a **pick engine**: a weekly NFL slate, sealed before kickoff,
graded in public, and free to everyone once it can be graded. Paid access buys
the slate earlier and the instrumentation around it. The model behind it loses
to the closing market and says so on its own page.

It is an odds analysis tool. It is not a sportsbook, does not accept wagers,
holds no customer funds, and is unaffiliated with any league, team or book.

## Who it is for

**Sharp and serious bettors, and people newer than that.** The core reader
still knows what vig is, already has accounts at several books, and has decided
what they want to bet before they arrive. They are not looking to be told who
wins. As of 2026-08-21 the product also has to be legible to someone who does
not yet know what a fair price is.

Design consequence, and the two halves are not in tension: **density stays,
explanation becomes available.** Information per pixel on every board. No
explainer tone in the reading path, no tutorial voice, nothing that slows down
the person who already knows. What changed is that explanation is now reachable
rather than absent — progressive disclosure, not a rewrite for a beginner.

In practice that means: a plain-English guide addressable from every page, a
collapsed gloss beside a dense board rather than a sentence injected into it,
a term defined once where it is first unavoidable rather than three times on
one screen, and shortened labels that keep their full form recoverable.

The test for anything new: does it cost the expert reader a single pixel of
density or a single second of delay? If yes, it is the wrong shape — move it
behind a click. A newcomer who has to ask one question is served. An expert
made to read an explanation they did not need is lost.

## The core claim, and why it survives scrutiny

Line shopping is positive expected value on its own arithmetic. Taking −190
instead of −235 on the same side pays more regardless of whether the pick is
correct. No forecast has to be right for the product to have value.

This is deliberate. It means the business does not rest on a prediction claim
we cannot substantiate.

Current board: ~2.3 points of implied probability between the best and worst
book on an average side, wider on NFL near kickoff.

## What we do NOT claim

We also run a prediction model. **It is worse than the closing market and we
measured it**: 49.5% against the spread across 2,608 walk-forward games, where
52.38% is break-even. Zero picks have been graded in public yet.

The same is now measured for player props, and it is worse. Across 194 real
board props — actual lines, actual de-vigged prices, outcomes known — the
strikeout model disagreed with the market by 11.5 points on average and its
side won 48.1% of the time. The finding underneath it matters more than the
number: the model carries real predictive information across all pitcher-starts
and effectively none on the subset books actually post. **Our edge existed where
no market existed.** Published in full at /props-model, including the three
explanations we got wrong first. See `docs/reports/props-model-negative-result.md`.

Consequence, and it is a constraint rather than a note: **no surface may rank or
select on model edge.** The daily best-prices post ranks on price against the
de-vigged consensus, never on `delta_pts`, because ranking by delta sorts by our
own error. Where a model probability appears at all it is labelled as context.

Both records are honest, published, and live on their own pages. They are
credibility, not the pitch. Nothing on the site depends on either model being
good.

## Business model

**We sell access and instrumentation. We never sell outcomes.** That sentence
is the whole rule, and everything below is what it permits and forbids.

Two paid things:

1. **Tools and data.** The full board, line-movement alerts, more books,
   historical closing-line lookups, exports.
2. **The sealed weekly slate.** The pick engine publishes a slate sealed at
   seal time, which unlocks free for everyone at first kickoff, plus per-pick
   instrumentation and divergence alerts. Pro buys *timing*, not accuracy.

The second one is the reason this section was rewritten on 2026-08-21. The
document previously said "explicitly not picks" while the product shipped a
paid pick surface, and the two were reconciled by an amendment appended to a
contradiction. Stated properly instead:

Selling a **prediction** carries a performance claim and therefore a
substantiation burden. Selling **early access to a prediction whose losing
record is published on the page selling it** does not — because no claim of
profitability is made anywhere, and the disqualifying figure is not in the
small print, it is the lead. /picks opens with "our model measurably loses to
the closing market — 49.5% ATS over 2,608 graded games, below the 52.4%
break-even" and tells the reader not to buy it expecting profit.

That is the line, and it is narrow. The moment any surface implies the slate
wins money, this becomes the thing the old wording was written to prevent:
dishonest, and legally exposed. Time decay is what keeps the paywall off the
trust surface — the proof is always free, because the slate is free the moment
it can be graded.

### What the pick engine depends on, and what would break it

Charging for a slate from a model whose published record is 49.5% against a
52.4% break-even is the most exposed thing this product does. The exposure is
not legal — the record leads the page that sells it, so no claim needs
substantiating. It is an **honesty** exposure, and it holds only while
"sealed, graded in public, Pro buys timing" stays literally true.

The specific failure is predictable, so it is written here rather than left to
be noticed: **the pressure will be to stop publishing the weeks that went
badly.** Not to lie — to let a bad slate go ungraded, to delay a publish, to
quietly drop a losing week from the record while the good ones stay. Every one
of those is the same act, and any of them turns this from a transparent
instrument into a tout with better typography.

So, as hard constraints:

- A sealed slate is graded and published **whether it wins or loses**. A week
  that goes badly is published on the same schedule as one that goes well.
- The slate unlocks free at first kickoff, every time. If the free unlock ever
  becomes conditional, the paywall has moved onto the trust surface and the
  product is no longer what this document describes.
- The record shown on the page selling access is the **full** record, not a
  window chosen after the fact.
- If any of these become inconvenient, that is the signal to stop selling the
  slate — not the signal to adjust what gets published.

Whoever reads this under that pressure will not have been part of the
conversation that built it. That is why it is here.

**None of the four is currently enforced by anything, and the gap is specific.**
`.github/workflows/grade.yml` commits whatever settled that week and treats an
empty result as success — `if git diff --cached --quiet; then echo "nothing
newly settled"; exit 0`. So a sealed week that is never graded is
indistinguishable from a week where nothing was due: green check, no commit, no
signal anywhere. The one failure this section names is the one failure CI
reports as fine.

Closing it means a check that knows what was sealed: for every sealed slate
past its settle time, a published grade must exist, and its absence has to be
loud — a failed run, and visible on the trust surface rather than only in a
workflow log. Until that exists these are promises, and today's other lesson
was that a rule held by convention rather than construction is one edit away
from not being held at all.

A daily post publishes the best available prop prices, refreshed with the board
and rendered from the same data the page reads. It is a **price** product and
must always read as one: selected on the gap to the de-vigged consensus, never
on a forecast, and it states plainly when nothing beats fair — which on most
boards is every line on it, because that gap is the house's cut.

Primary action on the landing surface: **subscribe.**

## Coverage

NFL, MLB, NHL, NBA, UFC. NFL is the priority — highest volume, widest gaps near
kickoff, and the season the business is built around. Other sports keep the
board populated year-round.

## Hard constraints

- Never accept, place or facilitate a wager. Never hold funds.
- Never publish a performance figure not regenerated by
  `scripts/published_figures.py`.
- **Never present a pick as profitable.** This is the constraint. The word ban
  below serves it and is not a substitute for it.
- Never use: **lock, guaranteed, risk-free, insider, sure thing, tail me** on
  any surface a reader can see, including public URLs.
- **pick / picks** is permitted in exactly one place: the pick engine, where it
  is the accurate noun for what is sold — a sealed, graded, published slate.
  It stays banned everywhere else, and specifically on the props price product,
  which selects on price and is not a forecast. Calling that one picks would
  claim a forecast we have measured and do not have.
  `data/props_picks.json` was renamed for that reason: a rule kept everywhere
  except in the routing table is not a rule. On the price product say: best
  price, best available price, fair price, consensus fair.
- **play / plays** stays banned everywhere including the pick engine. "Pick"
  names a published, gradeable prediction; "play" is an instruction to bet one,
  and we never give one.
- A disclaimer must still be able to say the word it disclaims. "Nothing here
  is guaranteed" is correct and stays. If this list is enforced by a string
  check, match on word boundaries and exempt literal negated phrases — a
  substring guard for "lock" blocks Tyler Lockett, and "play" blocks every
  "player". See AGENTS.md.
- **Never rank a price product by model edge.** The props best-prices post
  ranks on the gap to the de-vigged consensus and never on `delta_pts`,
  because that model was measured at 48.1% on 194 real board props and ranking
  by delta sorts by our own error. See "What we do NOT claim".
- The pick engine ranks by divergence (|independent − market|), which *is* a
  model-versus-market quantity, and that is legitimate there because it is the
  thing being sealed and graded rather than a claim about profit. The rule is
  not "never compute it" — it is **never let a number derived from the model
  imply that acting on it makes money.** A price product may not rank on it at
  all; the pick engine may rank on it and may not sell it as edge.
- Published confidence caps at 85% — our 90%+ band measured 94.5% predicted
  against 86.7% actual.
- **21+, where lawful.** Responsible-gambling helpline on every page.
  This document said 18+ until 2026-08-21 while every shipped surface said
  21+ — eight pages, the shell footer, `scripts/build_site.py` and the email
  alerts — and the Open Graph card said 18+, which meant the artwork on every
  shared link contradicted the page it linked to. One figure, everywhere, and
  grep for it before adding a new surface.
- Prices are what books showed when last read and move constantly; always
  timestamp the board.

## Technical truth

Static files, no framework, no build step, no backend. Data arrives as JSON
written by a Python engine and refreshed by GitHub Actions. The site is a
reader. This keeps the published numbers independently checkable and the
hosting free.
