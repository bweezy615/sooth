---
title: "Keyword and content plan"
description: "Internal SEO and AI-search distribution plan: where an honesty-first prediction site can actually rank, which queries to target, and what to publish before NFL Week 1."
last_updated: 2026-08-02
status: internal working document
---

# Keyword and content plan

Internal document. Not published to the site.

Deadline: NFL Week 1 kicks off **2026-09-09**. Today is 2026-08-02. That is five
weeks, and indexing lag means the deadline for the core content corpus is
earlier than the football deadline - see the timing section.

---

## The competitive situation, stated honestly

We are entering a category owned by large, well-funded affiliate publishers:
CBS SportsLine, Action Network, Covers, OddsShark, Dimers, Pickswise,
VegasInsider, BettingPros, OddsJam, Unabated, TheLines, plus every sportsbook's
own content arm. They have a decade of domain authority, full-time editorial
staff, and revenue-share deals that fund link acquisition.

**We will not outrank them for high-volume commercial queries.** "NFL
predictions week 1", "NFL picks against the spread", "best sports betting picks"
are lost before we start. Any plan that assumes otherwise is a fantasy and
should be discarded.

What those sites cannot do is answer a skeptical question credibly. Their
business model requires performance claims, so they cannot write "our model
lost to the closing line" and they cannot publish a verifiable record, because
the record would not survive publication. That is a structural weakness, not a
temporary one, and it is the only opening we have.

Two further facts shape the plan:

1. **AI answer engines reward exactly what we have.** The consistent finding
   across current guidance on LLM citation is that answer engines preferentially
   cite original statistics, self-contained factual sections, and content that
   answers a specific question directly. We have original, reproducible
   statistics that nobody else in the category publishes. That is the highest
   value asset we own for distribution purposes.
2. **Indexing lag differs by engine.** Perplexity picks up new pages within days
   of crawling. ChatGPT Search typically takes one to three weeks. Google AI
   Overviews follow standard indexing, four to eight weeks. This dictates the
   publishing calendar.

---

## The angle

**We are the site that publishes the numbers that argue against us.**

Everything downstream follows from that one sentence. Three defensible content
positions come out of it:

**Position 1 - Original benchmark data.** We publish measured NFL model
performance against de-vigged closing lines on 2,750 out-of-sample games, with
the full calibration table. Nobody else publishes this because nobody else has
an incentive to. When someone asks an answer engine "how accurate are NFL
prediction models", there is currently no good source. There should be, and it
should be us.

**Position 2 - The due-diligence authority.** We own the mechanism for verifying
a prediction record, so we can credibly own the topic of how to evaluate one.
This is the cluster where skeptical, high-intent searchers already are, and it
is currently served by Reddit threads, Whop-affiliate spam, and CapperTek
listings.

**Position 3 - Correct free tools that show their working.** No-vig calculators,
CLV calculators, and breakeven calculators exist in abundance and most are thin
pages wrapped around a form. Ours will publish the formula, the worked example,
and the edge cases. Tool pages earn links, get bookmarked, and get cited as
references by answer engines that need a definition alongside a calculation.

---

## Keyword clusters

Difficulty ratings below are relative judgements, not tool exports. Verify
against real data before committing budget.

### Cluster A - Concept explainers and definitions

The highest-leverage cluster for AI-search citation. Stable, evergreen,
non-seasonal, and every one of these queries has a single correct answer that we
can state in one sentence and then justify.

| query | intent | difficulty | our play |
|---|---|---|---|
| what is closing line value | informational | medium | the definitive explainer, plus why most published CLV is unverifiable |
| what does no-vig mean / no vig odds explained | informational | medium | formula, worked example, the two de-vigging methods and when they differ |
| what win rate to break even at -110 | informational | low | the 52.38% page; short, exact, quotable |
| brier score sports betting | informational | low | almost uncontested; we already compute it |
| what is a calibrated probability | informational | low | uncontested; ties directly to our only claim |
| implied probability from american odds | informational | medium | table plus converter |
| expected value sports betting formula | informational | medium | worked examples, no promises |
| data leakage machine learning backtest | informational | low-medium | crosses over to a technical audience that links |

**Why this cluster first:** these pages are the ones an answer engine quotes.
They are also the ones that make our tool pages and methodology page credible
through internal linking.

### Cluster B - Free tools and calculators

Highest commercial intent that is compatible with making no performance claims.
Existing tools from OddsJam, Unabated, BettingPros, DRatings and a dozen others
prove the demand.

| query | our play |
|---|---|
| no vig calculator / no-vig fair odds calculator | build it; publish the maths on the page, not just the form |
| closing line value calculator | build it; be explicit about which line you should enter and why |
| odds converter (american / decimal / fractional / implied) | build it; trivially cheap, permanently useful |
| hold calculator / sportsbook margin calculator | build it |
| parlay odds calculator | build it, with a plain statement of how correlation and hold compound |
| breakeven win rate calculator | build it; links to the 52.38% explainer |
| kelly criterion calculator | build it, with an explicit warning that Kelly assumes an edge you probably do not have |

These are also the free surface for the paid tier, which is tools and data. The
funnel is honest: the free calculator does one computation, the paid tier does
it continuously across books and history.

### Cluster C - Skeptic and due-diligence queries

See the dedicated section below. This is the acquisition channel most likely to
be underestimated.

| query pattern | examples |
|---|---|
| is [service] legit | is SportsLine legit, is Dimers accurate, is BetQL worth it, is Pickswise legit, is Rithmm legit |
| [service] review / [service] scam | Whop capper reviews, Telegram picks group reviews |
| are sports picks services worth it | generic category query, high volume, weak incumbents |
| how to spot a fake handicapper | evergreen, links well |
| do AI sports betting predictions work | rising query, poorly served |

### Cluster D - Prediction and model queries

The obvious cluster and the wrong one to lead with. High volume, seasonal,
dominated by incumbents, and directly adjacent to performance-claim language we
have banned. Enter selectively.

| query | our play |
|---|---|
| how accurate are NFL prediction models | **win this one.** We have the data; the current results are marketing pages |
| NFL computer picks / model picks | publish, but as calibrated probabilities with the losing backtest attached |
| NFL predictions week N | publish for completeness and internal linking; do not expect to rank |
| elo ratings NFL / how elo works in football | technical audience, links well, low competition |

### Cluster E - Verification and transparency

Nearly uncontested, low volume today, and strategically important because it is
the language we want the category to eventually be judged in.

- verified sports betting track record
- how to prove a betting record is real
- provably fair sports predictions
- merkle tree prediction commitment
- tamper-proof pick record

Volume here is small. Take it anyway: these queries convert at a very high rate
because the searcher has already decided that self-reported records are
worthless, which is our entire pitch.

### Cluster F - Programmatic pages off the ledger

Once the ledger is live and grading weekly, generate pages from it rather than
writing them:

- `/nfl/week-N` - the committed slate, the root hash, the graded outcome
- `/nfl/teams/[team]` - our rating history and every prediction involving them
- `/ledger/[slate-id]` - the commitment, the reveal, the verification status

Each page is unique, data-backed, updates on a schedule, and carries a
verification link. This is the only way we generate content at incumbent volume
without writing incumbent-quality prose. Gate it behind real data: an empty or
templated programmatic page is worse than no page.

---

## Ten article titles targeting AI-search citation

Written to be quoted. Each leads with a direct factual answer in the first
sentence, uses question-form subheadings, and contains at least one table of
original numbers.

1. **"Our NFL Model Lost to the Closing Line: A 2,750-Game Walk-Forward Backtest,
   2016-2025"**
   Target: *how accurate are NFL prediction models*. The flagship. Original
   data, an unusual conclusion, and a headline that no competitor can write.
   This is the single most citable thing we will publish.

2. **"What Win Rate Do You Need to Break Even at -110? The 52.38% Number,
   Derived"**
   Target: *breakeven win rate sports betting*. Short, exact, arithmetic anyone
   can check. Answer engines cite pages that state a number and show the
   derivation.

3. **"No-Vig Odds Explained: How to Remove the Sportsbook Margin, With Worked
   Examples"**
   Target: *no vig calculator*, *what is no-vig*. Pairs the explainer with the
   tool. Covers both multiplicative and power de-vigging and states when they
   disagree.

4. **"How to Check Whether a Sports Picks Service Is Legitimate: A Seven-Step
   Audit"**
   Target: *are sports picks services legit*. The template we then apply
   publicly, which turns one article into a repeatable series.

5. **"Closing Line Value: What It Measures, How to Compute It, and Why Most
   Published CLV Numbers Cannot Be Verified"**
   Target: *closing line value calculator*, *what is CLV*. Contains the strongest
   argument we have: we explain why we are not publishing our own CLV yet.
   Refusing to publish a number is more persuasive than publishing one.

6. **"Why the 'Highest-Confidence Pick of the Day' Is the Least Reliable Pick:
   Calibration Evidence From 2,750 Games"**
   Target: *are high confidence picks better*. Directly inverts the dominant
   product format in the category, with a measured 7.84-point overconfidence gap
   in the top band as evidence. Highly quotable and genuinely counterintuitive.

7. **"Data Leakage in Sports Betting Models: The Columns That Make a Backtest
   Lie"**
   Target: *sports betting model backtest overfitting*, *data leakage*. Names the
   specific banned columns. Crosses into the data-science audience, which is
   where inbound links actually come from in this space.

8. **"Brier Score, Accuracy, or ROI: How to Actually Evaluate a Sports
   Prediction Model"**
   Target: *brier score sports betting*, *how to evaluate a betting model*.
   Comparison tables are among the most-cited formats in AI answers.

9. **"How a Merkle Root Makes a Prediction Record Tamper-Evident"**
   Target: *provably fair sports predictions*, *verified track record*. Bridges
   the crypto-literate audience, who are already primed for commit-reveal
   arguments, into a sports context.

10. **"What the NFL Closing Line Knows That Your Model Does Not"**
    Target: *is the NFL betting market efficient*, *can you beat the closing
    line*. The essay version of our positioning. Most linkable of the ten, least
    directly commercial.

**Format rules for all ten:** first sentence answers the title question. One
idea per paragraph. Question-form H2s. At least one table of original figures.
A dated "last updated" line. Every statistic linked to the ledger or the
methodology page so a citation is checkable. No conclusion paragraph that
restates the article - answer engines extract from the top.

---

## The "is [competitor] legit" channel

This is a real acquisition channel and it is undervalued.

**Why it works.** Someone typing "is [picks service] a scam" has commercial
intent, has already been marketed to, and has already decided that testimonials
and screenshots are not evidence. That is a perfectly pre-qualified visitor for
a site whose product is a verifiable record. The queries are long-tail, so
individual volume is low, but the pattern replicates across dozens of service
names and the aggregate is meaningful. The incumbents in these results today are
Reddit threads, affiliate-funded "review" pages with a sign-up link at the
bottom, and Whop marketplace listings - all of which are visibly compromised or
visibly thin.

**Why it works for AI search specifically.** When an answer engine is asked "is
X legit", it needs a source that states checkable facts. Right now it mostly has
promotional pages and forum opinion. A page that says "we checked on this date
and found the following specific things" is materially better input, and gets
cited.

**The format.** One audit template, applied identically to every service, with
the same checks in the same order:

1. Does a public results ledger exist at the URL they advertise? Load it and
   record the HTTP status.
2. Is the record verifiable by anyone other than them, or is it self-reported?
3. Is there a methodology page that names the model and the data?
4. What performance claims do they make, and is there any published basis?
5. What vendors do their own terms and privacy policy disclose, and is that
   stack consistent with the technology they advertise?
6. Are subscription terms, renewal, and cancellation disclosed before payment?
7. Are affiliate relationships disclosed at the point of the link?

Then run the same seven checks on ourselves, on the same page, and publish the
result. If we ever fail one, that goes up too. An audit that always exonerates
its author is not an audit.

**Rules, non-negotiable.**

- Publish observations, not conclusions about intent. "The `/ledger` URL
  returned 404 on 2026-08-02" is a fact. "They are lying about their record" is
  an accusation, and one we do not need to make - the reader will draw it.
- Date and archive every observation. Screenshot and note the check time. Sites
  change; a stale claim becomes a false claim.
- Never use "scam" as an assertion in our own voice. It can appear in a heading
  as the query being answered, and the body answers it with evidence.
- Offer a right of reply and publish corrections prominently. Recheck and
  re-date at least quarterly.
- No affiliate link to any service we audit, ever, including favourable audits.
  A compensated audit is not an audit and disclosing it does not fix that.

The risk here is defamation exposure, and it is managed by the rules above, not
by avoiding the channel. Verifiable statements of fact, dated and sourced, with
a right of reply, are the standard defence.

---

## Technical AI-search layer

Already done:

- `robots.txt` explicitly allows GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot,
  Claude-Web, PerplexityBot, Perplexity-User, Google-Extended,
  Applebot-Extended, CCBot and others. Blocking OAI-SearchBot in particular
  removes a site from ChatGPT's live citations entirely, and a surprising number
  of publishers have done so by accident.
- `sitemap.xml` covering the core routes and the eight pending sports.

Still to do:

- **`/llms.txt`** at the root: a short machine-readable summary of what this site
  is, what it publishes, what it explicitly does not claim, and where the primary
  data lives. Ours should state the no-performance-claims position in the first
  three lines, because that is the distinguishing fact an answer engine needs.
- **Schema.org markup.** `Organization` on every page. `Dataset` on the ledger,
  which is genuinely a dataset and is treated as one by search engines.
  `TechArticle` on the methodology page. `FAQPage` on the explainers.
  `SoftwareApplication` on the calculators. `WebSite` with `SearchAction`.
- **Server-rendered content.** Anything an answer engine must read has to be in
  the initial HTML. Several AI crawlers do not execute JavaScript. The ledger,
  the methodology page, and the calculators' explanatory text must render
  without JS. The calculator interaction can be JS; the explanation cannot be.
- **Stable, readable URLs.** `/methodology`, `/verify`, `/ledger/2026-W01-nfl`.
  Never change one; if a route must move, 301 it permanently.
- **Visible dates.** A "last updated" line rendered in the HTML on every page.
  Freshness is a documented input to AI-search selection and it costs nothing.
- **Entity consistency.** Same brand name, same one-sentence description,
  everywhere on and off site. Answer engines resolve brands as entities, and
  inconsistent self-description dilutes that.
- **Server-log monitoring for AI crawlers.** Track hits by user-agent for
  GPTBot, OAI-SearchBot, PerplexityBot, ClaudeBot. Crawl arrival is the leading
  indicator; citations follow weeks later.

---

## Publishing timing

Working backwards from 2026-09-09, and from the indexing lags above:

**By 2026-08-10 (must-ship set).** Methodology, verify, disclaimers, the
flagship backtest article (#1), the calibration/confidence article (#6), and the
first three calculators with their paired explainers (#2, #3, #5). This is the
corpus that has to be crawled and indexed before Week 1 traffic exists. Anything
in this set that slips past mid-August will not be in ChatGPT Search or AI
Overviews by kickoff.

**By 2026-08-24.** The remaining explainers (#7, #8, #9), the due-diligence
audit template (#4), the first two service audits, `/llms.txt`, and all schema
markup.

**By 2026-09-05.** The NFL page, the Week 1 committed slate published with its
root hash, the essay (#10), and the eight sport stubs with honest status badges.

**From 2026-09-09, weekly.** Commit the slate before first kickoff. Publish the
reveal and the graded result after settlement. Update the running record. This
cadence is itself the content strategy for the season: a weekly, dated,
verifiable data drop is exactly the freshness signal both classical and AI
search reward, and it costs no editorial time because the pipeline generates it.

---

## Measurement

Vanity metrics to ignore: impressions, average position, domain authority.

Metrics that matter:

1. **AI crawler hits per week by user-agent**, from server logs. Leading
   indicator, visible within days.
2. **Citation appearances.** Run a fixed set of about thirty target prompts
   monthly against ChatGPT, Perplexity, Claude, and Google AI Overviews, and
   record whether we are cited and for what claim. This is manual and it is the
   only direct measurement available.
3. **Referral sessions from AI surfaces**, identified by referrer and by the
   `ChatGPT-User` and `Perplexity-User` agent strings.
4. **Calculator page to signup rate.** The tools are the commercial path.
5. **Verification page depth.** How many visitors actually reach `/verify` and
   how far they scroll. If nobody ever verifies, the commitment scheme is still
   worth having for its own sake, but the marketing framing needs rethinking.

---

## Copy constraints, applying to every page and every title

- Banned words: *guaranteed*, *lock*, *risk-free*, *insider*, *sure thing*.
- No win-rate, ROI, units-won, or profitability claim anywhere, in any format,
  including page titles, meta descriptions, image alt text, and social copy.
- No claim we cannot reproduce from the public ledger on demand.
- Do not describe the model as AI, machine learning, or a neural network. It is
  an Elo rating system with isotonic calibration. Accurate description is also
  the differentiator, and "AI" branding puts us inside the FTC's stated
  enforcement focus for no upside.
- Every page that mentions results links to `/methodology`. Every page that
  mentions the record links to `/verify`.
- If a headline would work equally well on a competitor's site, it is the wrong
  headline. Our headlines should be ones they structurally cannot copy.
