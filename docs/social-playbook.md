# @Soothbet — the daily post system

Ten post types, one graphics package, no fabricated numbers. Every card is
composed from a feed that is already published on sooth.bet, so anything on a
card can be checked against the site by anyone who cares to.

Code: `engine/xkit.py` (design kit) · `engine/xcards.py` (the ten layouts) ·
`engine/xpost.py` (guard, queue, CLI).

```bash
# render to a folder, queue nothing
~/sooth-poster/.venv/bin/python -m engine.xpost --kind board --preview /tmp/cards

# queue for Telegram approval — a button tap is still the only thing that posts
~/sooth-poster/.venv/bin/python -m engine.xpost --kind board
```

`pick-engine`'s own venv has no Pillow; the poster venv does. Both projects stay
separate on purpose: the poster rig owns the X credentials, the Telegram gate
and the publisher, and none of that belongs in this repo.

## The ten types

| `--kind`  | Post            | Reads                  | Needs |
|-----------|-----------------|------------------------|-------|
| `board`   | Today's Board   | `nflboard.json`        | 4+ games with spread + total |
| `board-ig`| Today's Board, 4:5 | `board.json`        | the Instagram canvas |
| `signal`  | Sooth Signal    | `nflboard.json` + `best_lines.json` | spread **and** our number |
| `matchup` | Matchup Intelligence | `research.json`   | nflverse team rates |
| `onestat` | One Stat        | `nflboard.json`        | one line that moved |
| `market`  | Market Watch    | `nflboard.json` + `timeline.json` | one line that moved |
| `prop`    | Player Prop Lab | `props.json`           | MLB game logs |
| `mvm`     | Model vs Market | `nflboard.json` + `best_lines.json` | spread **and** our number |
| `receipt` | Result Receipt  | `*.graded.json`        | a settled slate |
| `sees`    | What the Model Sees | `nflboard.json`    | one line that moved |
| `recap`   | Slate Recap     | `*.graded.json`        | a settled slate |

Everything NFL-shaped now runs off `engine/nflboard.py`, which is why the cards
talk in spread points rather than implied-probability points: the sport is
argued in the former and the first pass led with the latter, which is most of
why it read as market plumbing.

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
- **No invented numbers.** What the reference sheet asks for and we do not
  hold: team W-L records, L10 and home/away splits; pace; a prop projection
  outside strikeouts; final scores on the receipt. None of it is on a card.
  Spreads and totals ARE on the board now — they were always in the capture,
  and the earlier note claiming otherwise was wrong about everything but
  `board.json`. Hit rates stay labelled as history, not forecast.
- **One book is not a consensus.** ESPN publishes a single provider, so every
  spread and total on a card names DraftKings. Only the moneyline, quoted
  across several books, carries a de-vigged fair price — "best of 11" where
  eleven quoted, "1 book" where one did.
- **Sides.** `side_a` is the HOME team (`engine/capture.py`). Backwards, every
  spread inverts and still looks plausible; `engine.nflboard --selfcheck`
  asserts it, including the road-favourite case.
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
