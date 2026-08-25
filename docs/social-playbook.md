# @Soothbet — the daily post system

Ten post types, one graphics package, no fabricated numbers. Every card is
composed from a feed that is already published on sooth.bet, so anything on a
card can be checked against the site by anyone who cares to.

Code: `engine/xkit.py` (design kit) · `engine/xcards.py` (the ten layouts) ·
`engine/xpost.py` (guard, queue, CLI).

```bash
# render to a folder, queue nothing
~/worldcup-poster/.venv/bin/python -m engine.xpost --kind board --preview /tmp/cards

# queue for Telegram approval — a button tap is still the only thing that posts
~/worldcup-poster/.venv/bin/python -m engine.xpost --kind board
```

`pick-engine`'s own venv has no Pillow; the poster venv does. Both projects stay
separate on purpose: the poster rig owns the X credentials, the Telegram gate
and the publisher, and none of that belongs in this repo.

## The ten types

| `--kind`  | Post            | Reads                  | Needs |
|-----------|-----------------|------------------------|-------|
| `board`   | Today's Board   | `board.json`           | 3+ priced events |
| `signal`  | Sooth Signal    | `best_lines.json` + `teamstats-nfl.json` | an NFL slate |
| `matchup` | Matchup Intelligence | `research.json`   | nflverse team rates |
| `onestat` | One Stat        | `board.json`           | a priced board |
| `market`  | Market Watch    | `timeline.json`        | 8+ readings, 5+ books, a liquid league |
| `prop`    | Player Prop Lab | `props.json`           | MLB game logs |
| `mvm`     | Model vs Market | `best_lines.json`      | an NFL slate |
| `receipt` | Result Receipt  | `*.graded.json`        | a settled slate |
| `sees`    | What the Model Sees | `timeline.json`    | one move ≥ 1 pt |
| `recap`   | Slate Recap     | `*.graded.json`        | a settled slate |

A composer returns nothing when its feed cannot support a card. A quiet day
produces fewer posts, not softer ones.

## Rhythm

| When      | Post | Why then |
|-----------|------|----------|
| Morning   | `board` | the slate is set, nobody has looked yet |
| Midday    | `matchup` or `onestat` | shareable, no timing dependency |
| Afternoon | `signal` or `mvm` | prices have settled enough to disagree with |
| Pre-game  | `market` | the move has actually happened by now |
| Post-game | `receipt`, then `recap` | grading is the whole product |
| Any gap   | `sees` | evergreen, always available |

Do not run `signal` and `mvm` on the same day. They read the same feed —
`signal` deliberately takes the *second* widest disagreement so the two never
land on the same game, but two model-vs-price cards in one day is still one
card posted twice. Same for `board` and `onestat`, which share a headline
number on most days.

`receipt` and `recap` currently read a **replay** slate, because week one has
not been played. Both label it on the card and in the caption. When live slates
start grading, they pick up the live file automatically — the labelling
switches itself off.

## The rules the code enforces

- **No advice.** `check_caption()` runs against the *rendered* caption, not the
  template, and raises on recommendation language. `--selfcheck` builds all ten
  types and pushes every caption through it, so a card type added later cannot
  quietly introduce a pick.
- **No invented numbers.** Three things the reference sheet asks for do not
  exist in our data and are therefore not on the cards: spreads and totals on
  the board (we capture moneyline), final scores on the receipt (the ledger
  stores outcomes and prices), and a projection on the prop card (only
  strikeouts have a model). Hit rates are labelled as history, not forecast.
- **Losses look like wins.** `receipt` samples evenly across the confidence
  range instead of taking the top N, so the shakiest call is on the card by
  construction. The first version showed six calls and all six had won.
- **"Earliest read", never "open".** The price series starts where our capture
  window starts, which is not the market's opening price.
- **The independent model only.** `receipt` filters to `elo+epa-v1`, the model
  that never sees the line. The other one reads the market, so its record is
  not the honest one to publish.

## Known gaps

- Inter is the brand body face and is not installed; Helvetica Neue stands in.
  One constant in `xkit.py` (`F_BODY`) if you want to install it.
- The card teal is the site's `#2DD4A7`, not the reference sheet's `#00D1B2` —
  a card and the page it links to should not be two different greens. One
  constant (`BRAND`) if that call is wrong.
- Nothing is scheduled. Run a few by hand and approve them before automating a
  rhythm nobody has seen output from yet.
