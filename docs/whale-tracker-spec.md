# Whale Tracker — build spec

**Status:** ready to build. Nothing in this file is assumed; every API fact was
verified live on 2026-08-25 with the exact commands shown.
**Owner:** unassigned — written as a self-contained handoff.
**Read first:** `AGENTS.md` (deploy rules), `PRODUCT.md` (what the product is).

---

## 1. What this is, in one line

Surface **real money already committed on a public ledger** — Polymarket
positions and trades — as another checkable number beside our own.

## 2. Why it fits this product, and the trap it must avoid

sooth.bet is a **research analyzer**, not a tipster. Everything on the site is
computed from published data the reader can go and verify, including our own
losing backtest. Polymarket data fits that test better than almost anything
else we publish: the trades are real money, settled on-chain, publicly
readable, and attributable to a wallet that has a track record you can also
read.

**The trap.** This feature came out of a competitor scan (Oddify, $29.99/mo,
"AI predictions"). Their version is a tip sheet with extra steps: *follow the
smart money*. If ours ships as "whales are on the Yankees, so back the
Yankees", we have quietly become the thing we deleted the paid tier to avoid,
and we have done it while our own published record is 49.5% ATS against a
52.38% break-even.

So the rule for every string of copy in this feature:

> Report what was traded, by whom, at what price, and when.
> Never say what it means for a bet.

`engine/watch_email.py::_selfcheck` already enforces this pattern for the
watchlist emails by failing the build on recommendation language. Do the same
here.

---

## 3. THE BLOCKING CONSTRAINT — read this before designing anything

**Polymarket has no per-game sports markets.** Their sports coverage is
futures and novelty. Verified:

```bash
curl -s "https://gamma-api.polymarket.com/events?limit=6&closed=false&tag_slug=mlb&order=startDate&ascending=true"
# -> World Series Champion 2026, AL MVP, NL MVP, AL Cy Young, NL Cy Young, AL Champion

curl -s "https://gamma-api.polymarket.com/events?limit=3&closed=false&tag_slug=nfl"
# -> "Tush Push banned for 2026 NFL Season?", "Will Aaron Rodgers retire before
#    next season?", "Who will attend Taylor Swift and Travis Kelce's wedding?"
```

There is no "Tigers vs Rays tonight, moneyline" market to join to our board.

**Consequence:** this **cannot** be a per-game widget on `/market` or `/game`.
Anyone who plans it that way will get a long way in before discovering there is
nothing to join on. It is a **season-futures** surface: who the market's real
money likes to win the division, the pennant, the MVP — over months, not hours.

That is still worth building, and it is genuinely differentiated: nobody in our
competitive set shows on-chain conviction next to sportsbook pricing. But it is
a **new page**, not a column on an existing one.

If per-game markets ever appear, the join key is the market `title` /`slug`,
which contains full team names (see §4.2) and can be mapped through
`site/public/data/team-logos.json` exactly as `engine/watchlist.py::team_index`
already does.

---

## 4. The APIs — verified

### 4.1 Use these. No API key, no wallet, no signature.

Base: `https://data-api.polymarket.com`

| Path | Returns | Verified |
|---|---|---|
| `/trades?market={conditionId}&limit=N` | recent trades, self-describing | ✅ |
| `/holders?market={conditionId}&limit=N` | top holders per outcome token | ✅ |
| `/oi?market={conditionId}` | open interest | ✅ |
| `/v1/leaderboard?period=1d&limit=N` | trader rankings by pnl/vol | ✅ |

Base: `https://gamma-api.polymarket.com`

| Path | Returns | Verified |
|---|---|---|
| `/events?closed=false&tag_slug={nfl\|nba\|mlb\|nhl\|sports}` | events + nested markets | ✅ |
| `/markets?limit=N&closed=false` | markets incl. `conditionId` | ✅ |

### 4.2 Shapes actually returned

`/trades` — note it carries the market title, so a trade is self-describing and
needs no second lookup to render:

```json
{"proxyWallet":"0x51fd8f03…","side":"BUY","size":200,"price":0.1,
 "timestamp":1787623092,"outcome":"Yes","outcomeIndex":0,
 "title":"Will the New York Yankees win the 2026 World Series?",
 "slug":"will-the-new-york-yankees-win-the-2026-world-series",
 "eventSlug":"mlb-world-series-champion-2026",
 "name":"TimeTraveler","pseudonym":"Enchanted-Plaintiff","conditionId":"0x3df7be…"}
```

`/holders` — `{"token": "...", "holders":[{"proxyWallet","amount","name","pseudonym","outcomeIndex","verified"}]}`

`/oi` — `[{"market":"0x3df7be…","value":29727.074486}]`

`/v1/leaderboard` — `[{"rank","proxyWallet","userName","vol","pnl","verifiedBadge"}]`

### 4.3 DO NOT use `clob.polymarket.com/data/trades`

It looks like the obvious endpoint and it is the wrong one. It **requires**
L2/readonly auth headers (`POLY_API_KEY`, `POLY_ADDRESS`, `POLY_SIGNATURE`,
`POLY_PASSPHRASE`, `POLY_TIMESTAMP`) **and** a `maker_address`, so it is a
per-user history, not a market feed. `data-api` is the public one.

### 4.4 Rate limits (documented)

Data API: 1,000 req/10s general, **200 req/10s on `/trades`**.
Gamma: 4,000 req/10s general, 500 req/10s `/events`, 300 req/10s `/markets`.
Over-limit requests are **throttled, not rejected**. A cron polling a few dozen
markets every 30 min is nowhere near this — do not build a rate limiter.

---

## 5. What to build

Follow the existing shape exactly: a **capture** step that writes JSON, a
**publish** step, and a **static page** that reads it. No new runtime service.

### 5.1 `engine/whales.py` — fetch + normalise

* Discover open sports events via Gamma across `nfl,nba,mlb,nhl,sports` tags.
* For each market, pull `/holders`, `/oi`, and recent `/trades`.
* Normalise to a stable record. Suggested output `site/public/data/whales.json`:

```json
{"generated_at":"…","markets":[{
  "condition_id":"0x…","title":"…","event_slug":"…","sport":"mlb",
  "open_interest":29727.07,
  "outcomes":[{"outcome":"Yes","index":0,"top_holders":[
     {"wallet":"0xde7c…","display":"thebug44","amount":32137.76}]}],
  "recent":[{"wallet":"0x51fd…","display":"TimeTraveler","side":"BUY",
             "size":200,"price":0.1,"outcome":"Yes","ts":1787623092}]}]}
```

* **A "whale" must be defined by a published threshold, not by vibes.** Put the
  number in the file (e.g. `"whale_min_usd": 10000`) so the page can state it
  and a reader can check it. An unstated threshold is an editorial choice
  dressed as data.
* Fail soft, like every other capture module here: a dead endpoint yields an
  older file, never a half-written one.

### 5.2 `.github/workflows/whales.yml`

Model on `.github/workflows/capture.yml`. Every 30 min is plenty. No secrets
needed — that is the nicest property of this whole feature.

### 5.3 `site/public/whales.html`

* Loads `/assets/desk.css`, calls `Desk.mount("…")`, uses `.ph` for the
  masthead (canonical in `desk.css`), and **must have exactly one `<h1>`** —
  see commit `05407b4`, every page carries one now.
* Team crests via `assets/crest.js`: `Crest.team(name,{size:14,sport:'mlb'})`.
  **Always pass `sport`** — bare abbreviations collide across leagues and an
  unscoped lookup resolves to nothing by design.
* Add to `site/public/sitemap.xml` and bump `CACHE` in `site/public/sw.js`.
* Compliance footer is injected by `Desk.mount()`. Do not hand-write it and do
  not paraphrase it — the wagers clause and the hotline are legally checked.

### 5.4 Copy rules

* Wallet identities are **pseudonyms chosen by the trader**, shown on their own
  public profile. Render `name`/`pseudonym` as given; do not enrich, do not
  cross-reference to anything off-platform, do not attempt to identify a person
  behind a wallet.
* Say "held" and "traded", never "backing", "fading", "smart money says".
* State the threshold and the timestamp on the page itself.

---

## 6. Guardrails (non-negotiable)

1. **No PII in the repo.** `data/` is public git history forever. Wallet
   addresses are already public on-chain and are fine; **no email, ever** — see
   `engine/subscribers.py`, which exists entirely because of this rule.
2. **Never change a published number, record, denominator or disclaimer** while
   doing this work.
3. **Positioning:** the ratified line is "the best sports betting research
   analyzer on the market." This has been corrected twice. Before shipping any
   `<title>`, `<h1>` or meta description, read it back and ask what it says the
   product *is*. If the answer is "a tip service", rewrite it.
4. **Do not add a paid tier.** There is nothing to buy on this site, by
   decision, as of 2026-08-22.

---

## 7. Acceptance

- [ ] `python -m engine.whales --selfcheck` passes with no network (pure
      normalisation over a fixture, same pattern as `engine/watchlist.py`).
- [ ] A live run writes `whales.json` and a second run with the endpoint
      unreachable leaves the previous file intact.
- [ ] `/whales` renders with one `<h1>`, crests resolve, no console errors, no
      horizontal overflow at 375px.
- [ ] The page states the whale threshold and the capture timestamp.
- [ ] No string in the page or module recommends a bet. Add a selfcheck
      assertion for the banned-language list, as `engine/watch_email.py` does.
- [ ] `pytest -q` green, all `api/*.selfcheck.js` green.

---

## 8. Prior art in this repo — copy these, don't reinvent

| Need | Read |
|---|---|
| Capture → JSON → page pipeline | `engine/capture.py`, `.github/workflows/capture.yml` |
| Pure-selection module + selfcheck | `engine/watchlist.py` |
| Recommendation-language guard | `engine/watch_email.py::_selfcheck` |
| Team name → sport-scoped key | `engine/watchlist.py::team_index` |
| Crest rendering + why sport is required | `site/public/assets/crest.js` |
| Page masthead / `.ph` / `.vh` | `site/public/assets/desk.css` |

---

## 9. Open question for the owner

Polymarket's sports markets are season futures. That makes this a **slow**
surface — conviction shifts over weeks. Worth confirming that is the product
you want before building the page, because the fast version everyone pictures
("whales just moved on tonight's game") does not exist to build.
