# PRODUCT.md — Sooth

Product truth only. No visual decisions live here.

## What it is

Sooth is a **sports betting research analyzer**. Ask about a game and get an
answer assembled only from numbers that are published and checkable — never a
recommendation, and never a figure the model wrote.

Corrected 2026-08-22, twice, by the owner: the product is the analysis. "Every
book's price on one board" is **not** the mission. Price comparison is the
richest INPUT the analyzer has, and it belongs in the second sentence rather
than the first. Anything that states what the product IS — title, h1, meta
description, store blurb — has to lead with the analysis.

What it computes, and what the analyzer reasons over:

1. **Best available price** — the most generous quote on a side, and which book has it.
2. **Fair line** — the de-vigged consensus across all books. Median implied
   probability per side, normalised so the sides sum to 1, which strips out the
   bookmaker's margin.

It also runs a **pick engine**: a weekly NFL slate, sealed before kickoff and
published with its commitment, then graded in public. Everything is free. The
model behind it loses to the closing market and says so on its own page.

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

**There isn't one yet, and the site now says so in one sentence: everything is
free.** The paid tier was removed on 2026-08-22 — checkout endpoints deleted,
`/subscribe` gone, the PRO button out of the nav. No account, no signup, no
tier, nothing to buy anywhere on sooth.bet.

This is a correction, not a pivot. The paywall had been disarmed for weeks
while every surface still sold it: the nav had a PRO button, `/picks` said
"Pro buys you the slate at seal time", `/subscribe` listed a $9.99 price and a
feature comparison, the analyzer's capped state offered an upgrade, and
`/api/picks` returned an `upgrade` funnel — all pointing at a purchase the
product had already decided not to make. A reader could not get a straight
answer to "what is this and what does it cost", which is a worse problem than
being free.

**What replaced it, exactly:**

- The sealed slate is **published as soon as it is sealed** (changed
  2026-08-22). It used to hold until first kickoff, and this document argued
  that the wait was the proof mechanism. That was wrong. Commit-reveal
  integrity rests on the hash being published and externally timestamped
  BEFORE the event; the reveal time does not enter into it. W1's root was
  anchored to a public GitHub commit five weeks before its first kickoff, so
  revealing early proves exactly as much. The withholding was never even doing
  what it claimed — `{slate}.reveal.json` has carried every prediction in the
  clear the whole time as the Merkle leaf set. The lock existed to sell timing
  to the paid tier, and that tier is gone.
- Alerts are free and opt-in at `/alerts`.
- The analyzer's daily cap exists to keep the inference bill survivable, not
  to sell a way around it. It is currently switched off.

**When money comes back, these are the constraints it inherits.** *We sell
access and instrumentation. We never sell outcomes.* Selling a **prediction**
carries a performance claim and a substantiation burden. Selling **early
access to a prediction whose losing record is published on the page selling
it** does not — no claim of profitability is made anywhere, and the
disqualifying figure is the lead, not the small print. Time decay is what
keeps a paywall off the trust surface: the proof is always free, because the
slate is free the moment it can be graded. Anything that cannot satisfy all of
that does not ship.

### What the pick engine depends on, and what would break it

Publishing a slate from a model whose record is 49.5% against a 52.4%
break-even is the most exposed thing this product does — and it was more
exposed still while we were charging for it. Nothing is charged for now, which
removes the legal edge of the problem entirely and leaves the one that
actually matters: it is an **honesty** exposure, and it holds only while
"sealed, graded in public, losses published like wins" stays literally true.

The specific failure is predictable, so it is written here rather than left to
be noticed: **the pressure will be to stop publishing the weeks that went
badly.** Not to lie — to let a bad slate go ungraded, to delay a publish, to
quietly drop a losing week from the record while the good ones stay. Every one
of those is the same act, and any of them turns this from a transparent
instrument into a tout with better typography.

So, as hard constraints:

- A sealed slate is graded and published **whether it wins or loses**. A week
  that goes badly is published on the same schedule as one that goes well.
- The slate is free and unconditional. If access to it ever becomes
  conditional, a paywall has moved onto the trust surface and the product is no
  longer what this document describes.
- The record shown anywhere the slate is presented is the **full** record, not
  a window chosen after the fact.
- If any of these become inconvenient, that is the signal to stop publishing a
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

Primary action on the landing surface: **ask the analyzer about a game.**
There is nothing to subscribe to — the paid tier was deleted on 2026-08-22.
The only other conversion on the site is the free, opt-in alert list at
`/alerts`.

## Coverage

NFL, CFB, MLB, NHL, NBA. NFL is the priority — highest volume, widest gaps near
kickoff, and the season the business is built around. Other sports keep the
board populated year-round.

College football replaced UFC on 2026-08-27 (Branden's call, recorded in
`engine/lines.py`) rather than being added alongside it, which held the board
at five Odds API credits per run. Captured UFC history stays on disk under
`data/capture/ufc/`; we stopped publishing it, we did not delete it. This
section still said UFC on 2026-08-29, two days after every shipped surface had
stopped saying it — the drift this document is repeatedly warned about, found
by grepping the site for what the section claimed.

**CFB is line shopping only.** It is on the board and on /market and /edges; it
has no prediction model and no sealed slate, and `data/ledger/` holds NFL
slates alone. Per `docs/plans/college-football.md` the CFB model is Phase 3 and
deliberately deferred, so any CFB prediction that ever ships carries the "in
calibration" label /disclaimers §7 already promises, gets its own slate id
(`2026-W01-ncaaf`) and its own root, and never enters the NFL record.

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
