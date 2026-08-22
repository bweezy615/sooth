# The sooth.bet mobile app — layout spec

Reference: **lineterminal.com** on a 375px viewport, captured 2026-08-22, chosen
by the owner as the target layout. This file records what to take from it, what
to deliberately reject, and how each pattern maps onto surfaces sooth actually
has.

---

## What LineTerminal does on a phone

1. **Add-to-home-screen banner** pinned at the very top: icon, "Use the app /
   Add to home screen — no download needed", and an **Install** button.
2. **Header**: wordmark left; social + search icons right.
3. **Sport filter tiles** — a horizontally scrollable row of large tappable
   tiles carrying league logos, with `ALL` selected and ringed.
4. **A persistent AI prompt bar** — full width, rounded, with a circular submit
   arrow: "Create a free account to chat with Atom".
5. **Section rails.** Each section is a header bar (title, a mode chip like
   `Swipe Mode`, a date stepper, `See All ›`) followed by a **horizontal
   carousel of cards**, each card ~85% of the viewport with the next peeking.
6. **Rich, self-contained cards.** One prop card carries: league chip, market
   type, headshot, player name, the line, a price chip, `LAST 5 4-1`, a **bar
   chart with a dashed threshold line** and opponent logos beneath each bar,
   a `LAST 10` row of green ✓ / red ✗ squares, the matchup, the time, and an
   `Analyze` button.
7. **Fixed bottom tab bar** — floating pill: `HOME · SCORES · PROPS · ATOM ·
   MORE`, active item highlighted. This is the single most app-like element on
   the page.
8. **A floating action button** above the tab bar.

## What we take

| Pattern | Our version |
|---|---|
| Fixed bottom tab bar | `BOARD · PICKS · LEDGER · ANALYST · MORE` — our five real surfaces |
| A2HS install banner | We already ship a manifest and a service worker; the prompt was never surfaced |
| Sport filter tiles | NFL / MLB / NBA / NHL / UFC, driven by `sports_live` in board.json — a sport with no games shows as dark, never as a dead tab |
| Persistent prompt bar | `/ask`, our analyst. **No account, no gate** |
| Section rails + `See All ›` | `NEXT UP` (soonest games), `BIGGEST GAPS` (best `gain_pts`), `THE SEALED SLATE` |
| Rich self-contained card | Our game card: both sides, best price + book, de-vigged fair, `gain_pts`, and a mini price-spread track |
| Mini data-viz in card | Not a "last 5" bar chart — we have something better and truer: **every book's implied probability on one track**, with fair marked and best highlighted. `Desk.spectrum()` already draws it |

**On horizontal scrolling.** The owner's earlier complaint — "they shouldn't
have to scroll right and left to see our stats" — still stands and is not
contradicted by this. The distinction:

- A **table** that hides columns off-screen is a defect. The stats are the
  product and they were invisible. Tables stay stacked below 720px.
- A **card carousel** is a deliberate one-item-at-a-time control where each
  card is complete in itself and the next one peeks so the affordance is
  obvious. That is fine, and it is what LineTerminal is doing.

Never put a *field of one record* off-screen. Putting the *next record*
off-screen is normal.

## What we deliberately reject

LineTerminal's shell is excellent. Its content model is the thing sooth exists
to argue against, and adopting it would delete our position:

| Theirs | Why we don't |
|---|---|
| `Sign up to unlock` on most cards | Everything here is free and ungated. Our lock is time-based and applies to everyone equally |
| `PICK ?????` / `Premium reasoning hidden` | Withholding reasoning to sell it is the opposite of publishing a method |
| Systems sold on `+21.1% ROI`, `+41.4u`, `63.5% W` | Selected subsets with chosen filters — the exact attack surface our positioning names. Also on our "deliberately never" list as testimonial/income claims |
| A card that names a side to bet | Our analyzer structurally cannot pick a side. That ban does not move for a layout |

We take the chrome. We keep the substance.

## Structure to build

```
┌─────────────────────────────┐
│ [icon] Add to home screen  ⨯│  dismissible, once
├─────────────────────────────┤
│ sooth.bet          ⌕        │  wordmark, teal .bet
├─────────────────────────────┤
│ [ALL][NFL][MLB][NBA][NHL]   │  sport tiles, h-scroll, live dot
├─────────────────────────────┤
│ ⌨  Ask about tonight's board│  prompt bar → /ask
├─────────────────────────────┤
│ NEXT UP            See all ›│  section rail header
│ ┌────────────┐┌──────────   │  card carousel, next peeks
│ │ game card  ││ game card   │
│ └────────────┘└──────────   │
│ BIGGEST GAPS       See all ›│
│ ┌────────────┐┌──────────   │
│ THE SEALED SLATE            │
│ ┌─ frost card, countdown ─┐ │
├─────────────────────────────┤
│  BOARD  PICKS  LEDGER  ASK  │  fixed bottom tabs
└─────────────────────────────┘
```

Everything obeys `docs/DESIGN-frozen-market.md`: cold near-black ground, one
teal, frost for anything sealed.
