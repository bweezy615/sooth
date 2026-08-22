# sooth.bet — Competitive Decision Document
*Date: 2026-08-21 · Source: 25+ product scans across three segments (AI analyzers, odds/EV tools, verification infrastructure)*

---

## READ THIS FIRST — the blunt verdict

**Half of our differentiator is already gone, and it's the half we lead with.**

"We publish our losses" is not a unique position. It is a crowded one:

- **TeamRankings** publishes a filterable all-time NFL ATS ledger showing **2262-2236-131 (50.3%), −179.6 units since 2009**, against a break-even they define themselves as 52.4% — on the same domain that charges $49/mo. They also publish that their 2026 confidence rating **inverted** (2-star at 43.5%, 1-star at 55.9%).
- **nfelo** publishes losing seasons, "vs Close" benchmark columns, and CLV-vs-realized-units splits — **for free, open source**, and submits picks to **ThePredictionTracker.com for independent weekly grading**.
- **SportBot AI** publishes negative per-sport ROI *on its sales page* (NBA −2.5%, NHL −3.9%, Tennis −3.4%) and monetizes it at $18.99–$39.99/mo.

Worse: **our exact vocabulary has been counterfeited.** Sports AI already prints *"Every bet logged before kick-off, settled with the result. No cherry-picking"* as marketing copy, backed by nothing but testimonials, for $34.99 lifetime. The words are worth zero now.

**What is still genuinely ours:** not "sealed," not "honest." It is **UNFILTERED**. Every honest competitor's record is a *selected subset* — TeamRankings by star tier, nfelo by a betting-card rule that plays ~90–130 of 285 games, SportBot by an "Edge ≥2%" filter. That selection rule is where all three are attackable, and it is exactly where nfelo's 55.06% banner comes from while its own columns admit the model is 0.04% *worse* than the close.

**Sealed + unfiltered + third-party timestamped + graded against a stated break-even, on the page that sells access.** That intersection is empty. We occupy it and we are under-claiming it.

---

## 1. THE LANDSCAPE

The market splits four ways, and only one group actually competes with us.

**Actually competes with us:**
- **SportBot AI** ($18.99–$39.99/mo) — the near-clone. De-vigs to a fair price, computes a model-vs-market gap in points, wraps it in a chat, and publishes a methodology-stated ledger with losers. Everything we say about ourselves, they can say too, minus one sentence: nothing is pre-committed.
- **TeamRankings** ($49/mo) and **nfelo** (free) — the honesty competitors. They own "published losses" and have owned it for 15 years. nfelo is the closest thing to us on timestamping: open-source code plus an outside grader is a more *legible* proof to a skeptic than a Merkle root.
- **CrazyNinjaOdds** (free, donation-funded, solo operator) — the board competitor and the blueprint. Nine user-selectable devig methods, book-count per row, max-bet display, a warning glyph on low-confidence rows. One person gives away more method transparency than any $199/mo product.

**Doesn't compete — and we should stop measuring ourselves against them:**
- **OddsJam, Unabated, Betstamp PRO, PickTheOdds, OddsShopper** ($99–$499/mo) — a data arms race. Their moat is the data bill (100–200 books; $5,000+/mo per sport at the enterprise tier). On $30/mo we cannot enter this fight and should not try.
- **Juice Reel, Pikkit** — verification at *settlement* (sportsbook sync). Orthogonal to us, not rival: sync proves money was risked but not *when* the pick existed; a seal proves when the pick existed but not that money was risked.
- **Playbook (Action Network), ParlayLens, the App Store slip-scanner wave** — workflow tools that removed accuracy exposure by never picking a side. Playbook, built by the incumbent with the most reputation to lose, makes **zero predictions**. That is independent validation of our analyzer's hard ban on picking a side.
- **Rithmm ($29.99–$99.99/mo), Leans.ai (~$299/mo), RotoBot, Outlier, Sports AI** — pick-sellers monetizing unverifiable claims. Not competitors for a buyer who cares about proof; they are the foil we point at.

---

## 2. WHERE WE ALREADY WIN

| Position | Evidence | Who's closest |
|---|---|---|
| **Unfiltered full-slate commitment** | Every NFL game sealed, no star tier, no edge threshold, no betting-card rule | Nobody. TR/nfelo/SportBot all filter |
| **Third-party timestamp before the event** | Merkle root anchored to public GitHub commit; verify script published | Nobody cryptographically. nfelo's ThePredictionTracker submission is the nearest functional substitute |
| **Losing number on the page that sells access** | 49.5% ATS / 2,608 walk-forward games vs 52.38% break-even | TeamRankings (−179.6u, $49/mo), nfelo, SportBot — genuinely tied, not ahead |
| **Analyzer that structurally cannot pick a side** | /api/ask answers only from board JSON; superlatives from a precomputed leaders block | Playbook (same instinct, zero predictions). SportBot's "refusal on missing data" is an *input* gate, not an output ban — a "+4.2% on the over" IS a pick |
| **No model-written numbers, ever** | Every figure computed in Python and present verbatim in context | RotoBot's "stats current to the minute" is a *pipeline* claim, not a *citation* claim. Ours is strictly harder and actually verifiable |
| **Published negative result** | Prop model shipped, found no edge, said so | **Zero competitors have a "we built this and it didn't work" page.** Unoccupied trust primitive |
| **Price transparency + fully free** | $9.99 published, currently disarmed to $0 | Rithmm has no free tier at all; RotoBot hides pricing until after signup |
| **gain_pts is reproducible** | Plain points of implied probability, no black box | OddsShopper wraps EV in proprietary "OddsShopper Rating / xROI / xWin%" that can't be checked against another tool |

**Where we're weaker than we think, stated plainly:** the honesty posture alone is not a moat — SportBot proves it can be arrived at independently and monetized. The moat is *unfiltered + pre-committed*, and we are currently burying it under language a $34.99 scam already uses.

---

## 3. TABLE STAKES WE LACK — ranked by how badly the absence hurts

1. **Alerts / notifications — WORST.** Every paid product in both segments ships them, and they are the single most-cited reason people pay for these tools at all. We have no push, no email, no "the slate is sealed" ping. A product with no reason to return has no retention.
2. **Mobile.** The "Infinite Desk" — five monitors on a physical desk, spatially navigated — is a desktop toy. Betting happens on a phone, at the venue, minutes before kickoff. Rithmm, Outlier, Pikkit, RotoBot, Juice Reel are all mobile-first. This is the hole nobody wants to name because the UI is the thing we're proudest of.
3. **CLV tracking on our own picks.** Table stakes in 2026 (Betstamp and Unabated give it away free) — *and simultaneously our single biggest unclaimed asset*. We are the only operator who can prove a pick predated the close. We are not measuring it.
4. **Board honesty instrumentation.** No book-count per row, no max-bet/limit display, no low-confidence flag on one-way-line devigs, no devig-method selector. CrazyNinjaOdds ships all four for $0. A row devigged from 3 books currently looks identical to one from 11.
5. **Named data sources on the page.** Outlier names Sportradar and Rotowire — cheap, verifiable trust. We name nothing publicly: not the ~11 books, not the EPA source, not ESPN injuries.
6. **Line-movement history / opening line / steam.** Standard everywhere. Also a prerequisite for CLV done properly.
7. **Bet tracker.** Free at Betstamp, Pikkit, SlipSync. But see §4 — a *manual-entry* tracker is worse than none.
8. **Slip-screenshot ingestion.** The most-adopted AI interaction in consumer betting (Playbook, ParlayLens, the whole App Store wave). We have the only grounded version available and haven't built it.
9. **Distribution surface.** Playbook wins from X replies and Discord, not from model quality. Our board and sealed slate live only on sooth.bet.
10. **Multi-sport prop coverage.** Least urgent — and our prop model honestly found no edge, so breadth here would be volume without value.

---

## 4. THE BUILD LIST

### BUILD NEXT (in order)

| # | Item | Effort | Tied to |
|---|---|---|---|
| 1 | **CLV of sealed picks vs closing line.** Cron-snapshot each sealed game's best price at T−5min; publish per-pick CLV plus an aggregate CLV column in the ledger, separated from realized units. | **[2–3 days]** | Unabated (teaches CLV, never grades its own line); Betstamp (dual CLV vs price-taken *and* best close); nfelo ("vs Close" columns) |
| 2 | **Ledger headline rewrite + denominator labeling.** Lead with "no selection rule." Label the 2,608-game walk-forward backtest and the live sealed sample as two distinct populations, with counts and date ranges, on the same page. | **[0.5 day]** | SportBot AI dies on "175 qualified public picks" vs "1,297 bets tracked." We have the identical trap open |
| 3 | **Board honesty instrumentation.** Book-count column per row; devig-method selector with plain-English tradeoffs; warning glyph on rows devigged from one-way lines with estimated juice; max-bet/limit where the book exposes it. | **[2–3 days]** | CrazyNinjaOdds — a solo operator shipping all four free |
| 4 | **Name the data sources on the board.** The ~11 books by name, the EPA source, ESPN injuries, refresh cadence. | **[0.5 day]** | Outlier names Sportradar + Rotowire |
| 5 | **Submit picks to ThePredictionTracker.com.** A hash asks a stranger to run our script; an outside grader asks them to read someone else's scoreboard. Do both. | **[1 day + weekly]** | nfelo |
| 6 | **Negative-results page as a named artifact.** "Things we built that didn't work" — the prop model, permanently linked from the ledger. | **[1 day]** | Nobody. Zero competitors have this |
| 7 | **Alerts v1.** Email on slate seal, on grading publish, and on a user-set gain_pts threshold. No push infra needed. | **[2–3 days]** | Every paid product in both segments; the #1 stated reason people subscribe |
| 8 | **Mobile board view.** Not a rewrite of the Infinite Desk — a phone-first route to the board, the sealed slate, and the ledger. | **[3–5 days]** | Rithmm, Outlier, Pikkit, RotoBot — all mobile-first |
| 9 | **Taggable X bot answering from the live board JSON.** Same hard bans as /api/ask. | **[3–4 days]** | Playbook — the highest-leverage distribution build in the research |

### LATER
- **Grounded slip scanner** — scan a slip, return best price across the ~11 books, de-vigged fair line, and gain_pts per leg, **with no verdict on any side**. Nobody in the OCR wave gives this answer. **[4–6 days]**
- **Line-movement history + opening-line archive** — storage cost, and a prerequisite for richer CLV. **[3 days + data]**
- **Metered AI questions** as the Pro lever when Pro re-arms. Three-for-three across SportBot (50/mo), Rithmm ("4x Scout"), and RotoBot. Maps to real inference cost and withholds no honest number from a free user. **[1 day]**
- **Bet tracker — only with sync.** Pikkit's whole trust proposition is refusing manual entry. A manual-entry tracker is a liability, not a feature.
- **A non-slate-day reason to open the app.** RotoBot solved this with fantasy OAuth. Our honest candidates are the board and the ledger; we need an answer to "why open this on a Tuesday in March."

### DELIBERATELY NEVER — do not propose these again

| Never | Because |
|---|---|
| Parlay builder / correlated parlays | Multiplies vig by construction and requires fabricating correlation structures no consumer feed supports. Arithmetically incompatible with an honesty posture. (RotoBot) |
| Arbitrage, middles, low-hold, promo/free-bet converters | Gets users' accounts limited, carries the segment's worst honesty reputation, and puts a solo operator in bonus-abuse territory. (OddsJam calls arbitrage "guaranteed profit on every bet") |
| Testimonial ROI as evidence | "+24.82% for May", "€3,200 profit" — the exact substitution of vibes for evidence we exist to refuse. (Outlier, Sports AI) |
| Proprietary composite scores | OddsShopper Rating / xROI / xWin% make output legible and unauditable. gain_pts must stay reproducible. |
| Affiliate "we tested and ranked" review farm | SportBot, PropsBot and Picks & Parlays all rank themselves #1 against rivals they sell against. It sits on the same domain as their honesty page and destroys it. |
| Income claims, "guaranteed," any win-rate promise | "Make $500-$1000+ weekly." One sentence like this deletes the entire brand. |
| Lifetime pricing | $299/$999 lifetime against a perpetual data bill is a cash-flow signal, not confidence. (SportBot, Sports AI) |
| Per-leg verdicts on scanned slips | "Research, not picks" while the UI grades your legs is having it both ways. (ParlayLens) |
| Hidden pricing / signup-gated rates | RotoBot's lead-capture pattern. Our $9.99 is a trust asset. |
| A headline record drawn from a filtered subset | nfelo's 55.06% banner sits above columns admitting the model is worse than the close. This is the exact sin our position attacks. |
| Chasing book count | ~11 books cannot become 100. A shallow +EV feed off 11 books surfaces stale prices and produces the "lost money consistently" outcome Reddit is full of. |
| Repeating "logged before kickoff / no cherry-picking" as a tagline | Already counterfeited by Sports AI at $34.99 lifetime. Show the verify script and the anchor hash instead. |
| Staking real money to answer "sealed picks aren't real money" | No capital, and it converts an information business into a gambling one. Answer it in the FAQ with CLV, not with a bankroll. |

---

## 5. POSITIONING

**Lead sentence:**

> **Every game on the slate. Sealed before kickoff, timestamped by GitHub — not by us. Graded in public against the 52.4% break-even, including the part where we lose.**

Everything else in this market is a selected record. That is the sentence.

**Proof point 1 — No selection rule.** The full weekly NFL slate is committed, unfiltered. TeamRankings filters by star tier. nfelo plays ~90–130 of 285 games. SportBot filters at "Edge ≥2%." Every one of those records is chosen; ours is not. *This is what makes a 49.5% number credible instead of embarrassing.*

**Proof point 2 — The seal is timestamped by someone else.** Merkle root anchored to a public GitHub commit, with a verify script anyone can run. TeamRankings' strongest equivalent is a convention — "we consider our last posted pick before game time to be our final pick" — with the vendor as sole custodian of what the pick was.

**Proof point 3 — The losing number is on the sales page.** 49.5% ATS over 2,608 walk-forward games against a 52.38% break-even, plus a prop model published as a negative result. Rithmm charges up to $999.99/year and states no accuracy figure anywhere. Leans.ai charges ~$299/mo on a self-graded 53.8% ATS with no pre-commitment and no closing-line reference.

**The line to use when a skeptic shows up:** *"Ask any service showing you a record which bets are in the tracker but not in the published picks — and ask when the inclusion filter was chosen."*

**Steal the impossibility framing** (Pikkit's move — describe something that *cannot happen*, not something you promise): **"The pick cannot be changed after kickoff. The hash was published before it."**

---

## 6. THE ONE THING

**Ship closing-line value on the sealed picks, and rewrite the ledger headline around "no selection rule" as its packaging.**

Why this and nothing else:

Our stated differentiator has been commoditized on both ends — the honest competitors already publish losses, and the dishonest ones already print our vocabulary. **CLV on a third-party-timestamped, unfiltered pre-commitment is the one number in this entire market that structurally cannot be faked or matched.** Unabated teaches CLV, gives the calculator away free, and conspicuously never grades its own line. Betstamp grades users but not itself. nfelo publishes "vs Close" but only on a selected card. Every one of them could publish a CLV figure tomorrow and a skeptic would correctly ask *when did that pick exist?* — a question only we can answer.

It also solves our worst brand problem. A 49.5% ATS headline reads as "this model loses." CLV separates skill from variance — it says whether the pick beat the price the market eventually settled on, which is the metric sharps actually respect. And it partially answers the predicted top attack: *"sealed picks aren't real money."* No, but a pick that beat the close, provably before the close, is the closest thing to proof that exists without a bankroll — and we don't have a bankroll.

Two days of work. Cron-snapshot the closing price on games we already seal, compute the delta, publish it in the ledger next to the record.

**And publish it even if it's negative.** Especially if it's negative. That is the entire brand, and it is the one thing on this list that no competitor can copy without first disclosing their own selection rule.