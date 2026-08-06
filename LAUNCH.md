# Sooth launch posts — Friday 2026-08-08

Drafts, not gospel. Edit freely. Nothing here makes a performance claim,
promises a win rate, or uses the banned words (guaranteed / lock / risk-free /
insider / sure thing). The pitch is arithmetic, not prophecy.

---

## X / Twitter (short)

Every sportsbook charges a different price for the same bet.

Sooth reads 11+ books, strips the vig, and shows you the best number next to
the fair one — games and player props, timestamped, free to look at.

We even publish our own model losing to the market. That's the point.

[link]

---

## X / Twitter (thread version)

1/ We built a prediction model for NFL games. Backtested it properly —
walk-forward, no future data, 2,608 games.

It lost to the market. 49.5% against the spread when breakeven is 52.4%.

So we published the losing record and built something better instead.

2/ Here's the thing nobody's model beats: the price gap BETWEEN books.

Same bet, same line. One book pays +230, another +200. Taking the better
number is worth ~2 points of implied probability on an average side — before
any prediction is made.

3/ On player props it's wider. Our first capture found gaps up to 6 points
on the same line, same player, same market.

Books can't repost every prop every time news breaks. That lag is the edge.

4/ So that's what Sooth is: every book's price, the de-vigged consensus,
best number highlighted. Games and props. Timestamped snapshots, committed
to a public ledger before kickoff so nothing can be quietly edited later.

No picks. No "locks." The arithmetic is the product. [link]

---

## Reddit r/sportsbook (or r/sportsbetting) — text post

**Title:** I backtested my "AI picks" model properly. It lost. So I built a
line-shopping board instead — free, no picks.

**Body:**

Like half this sub, I built an NFL prediction model. Unlike the pick-sellers,
I backtested it walk-forward with leakage controls: 2,608 out-of-sample games,
2016–2025. Result: 49.5% ATS against a 52.38% breakeven. The closing market
beat it, which is the expected result — the closing line is brutally
efficient. The full methodology and the losing record are published on the
site, because if I'm asking you to trust the numbers, that has to include the
embarrassing ones.

What DOES survive scrutiny is boring arithmetic: books disagree on price.
Right now the average side has about 2 points of implied probability between
the best and worst book, and player props run wider (we've measured same-line
gaps over 6 points). Taking the better number pays regardless of whether your
pick is any good.

So the site is just that: every book's price on games and props, the
de-vigged median consensus, best number flagged, snapshot timestamped. Board
states are hash-committed before games start so the record can't be
retroactively edited.

Free to look at. No picks sold, ever — our own data says they'd lose you
money. Link in comments / profile per sub rules.

---

## Checklist for Friday (from the plan)

- [ ] Buy domain, `vercel domains add <domain>`, update canonical/OG tags in index.html
- [ ] Run week's ledger commitment so launch day has a receipt
- [ ] Final smoke-test every page on the real domain
- [ ] Post (X first, Reddit after — Reddit needs the account to not look like an ad)
- [ ] 18+ / responsible-gambling line present on every page (constraint from PRODUCT.md)
