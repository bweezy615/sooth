# /research downloads half a megabyte nobody reads

*Backlog item 2. Written 2026-08-27 before any code.*

> **STATUS: CLOSED — shipped in `1224a756`, re-measured against production
> 2026-09-03.** The cut landed and the numbers below are confirmed. Nothing
> further should be trimmed here; the evidence is under "Re-measured".

## First: the premise in the backlog was partly wrong, so measure before cutting

The backlog said `research.json` is "roughly 3× the next-largest payload, and
every visitor to that page downloads it." Measured against production today:

| payload | on disk | over the wire (brotli) |
|---|---|---|
| research.json | 1,373,763 | **58,612** |
| whales.json | 316,761 | 39,507 |
| timeline.json | 303,185 | 27,956 |
| nflboard.json | 277,633 | 10,320 |
| injuries.json | 128,683 | 16,188 |

```
curl -s -o /dev/null -w "%{size_download}" https://sooth.bet/data/research.json
curl -s -H "Accept-Encoding: br" https://sooth.bet/data/research.json | wc -c
```

Vercel serves it brotli-compressed, so the actual download is **59 KB, not
1.5 MB** — 1.5× the next largest, not 3×. Anyone quoting the on-disk number as
a download figure would be repeating something untrue, which on this site
matters. Recording it here so the next person does not re-derive it.

That does not make the file fine. 1.37 MB still has to be parsed and held in
memory by every visitor to `/research` **and** `/game`, both of which fetch it
whole. On a phone that is the real cost, and it is worth removing — but the
justification is parse and memory, not bandwidth.

## The actual defect: half the file is dead, and duplicates another file

`reports[].movement` is 46% of the payload. It holds five keys:

- `spread_line`, `total_line` — where the number itself opened and sits now.
  **Read**, by `research.html:191` (the list row), `research.html:275` (the
  detail panel) and `engine/research.py::build_facts` (the "line_move" fact).
- `moneyline`, `spread`, `total` — 40 hourly consensus points each, every point
  a dict re-keyed by the full team name. **Read by nothing.** Grepped
  `site/`, `engine/`, `api/`, `scripts/`, `.github/`: the only subscripts of
  `movement` anywhere are `movement[mk + "_line"]` and `moves.get(f"{market}_line")`.

Worse, it is a duplicate. `engine/timeline.py` publishes the same thing —
consensus implied probability over time, per market — in `timeline.json`, for
89 events instead of 56, in a far tighter encoding (epoch integers in flat
arrays rather than ISO strings and repeated team names), and that is the copy
`/game` actually renders as MARKET TIMELINE. Both `/research` and `/game`
already fetch `timeline.json` alongside `research.json`, so the data is
literally already in hand on both pages that would want it.

So this is not "trim a field to save bytes". It is a second, worse copy of a
published series that no code path consumes.

## Measured effect of removing it

```
1,434,050 -> 718,735 bytes on disk   (-49.9%)
   88,846 ->  64,187 bytes gzip -9   (-27.8%)
```

Halving parse time and memory on the two pages that load it, for a payload
nothing reads.

## Does removing published data cost us a receipt?

No, and this is the question that decides it, so it gets answered explicitly:

- The same series stays published, better, in `timeline.json`.
- The raw observations it is derived from stay committed in `data/capture/*/*.jsonl`.
- No figure on any page is computed from it. `research.json`'s own note —
  "Every figure in facts is computed from the data in this file" — stays true:
  `build_facts` touches only `{market}_line`, never the point series.

Nothing becomes uncheckable. If it did, this change would not be made.

## Plan

1. **Stop emitting it.** In `engine/research.py`, drop the `mv = movement(...)`
   call from the report loop. `line_history` stays untouched.
2. **Delete `movement()` and its two unit tests.** A function computed on every
   research run whose output is published and read by nobody is not an asset to
   keep warm; it is the thing that made the payload twice its size without
   anyone noticing. `line_history`'s docstring contrasts itself with
   `movement`, so reword it to stand alone. `timeline.py` is where that series
   lives now, and the docstring says so.
3. **Regenerate `research.json`** and confirm the shape.
4. **Leave a check behind.** `tests/test_research.py` gets a test asserting the
   published report carries only `*_line` movement keys — i.e. that the series
   does not come back. Size alone is not the invariant; "we do not publish a
   payload nothing reads" is.
5. **Browser-verify `/research` and `/game`** against the trimmed file: the list
   rows still show line movement, the expanded panel still shows "Opened X, now
   Y", the facts list still carries its line_move fact, and `/game`'s MARKET
   TIMELINE (fed by `timeline.json`) is unaffected.

## Deliberately not doing

- **Not switching `indent=1` to compact JSON.** Another ~35% off disk, near
  zero off the wire (brotli erases whitespace), and it makes the committed diffs
  of a file that churns every 30 minutes unreadable. `timeline.json` is written
  compact and the rest of `site/public/data/` is written `indent=1`; that
  inconsistency is real but is a separate call, and a cosmetic one.
- **Not paginating or splitting `research.json` per game.** With `movement`
  gone it is ~44 KB over the wire, in the same band as the other payloads. A
  split would cost the instant expand-a-row behaviour the page has today, for a
  saving that no longer exists.
- **Not touching `injuries` (23%).** It is read: `research.html:266-269` renders
  the per-player list in the expanded panel.

---

## Re-measured — 2026-09-03, overnight run

Re-opened with the instruction to cut nothing without re-measuring first. The
measurement says there is nothing left to cut here, so nothing was cut. Every
figure below is a fresh fetch from sooth.bet tonight, not a re-derivation:

| payload | on disk | over the wire (brotli) |
|---|---|---|
| whales.json | 323,009 | **40,377** |
| **research.json** | **740,104** | **36,636** |
| timeline.json | 251,557 | 25,990 |
| injuries.json | 158,391 | 19,143 |
| moves.json | 218,746 | 17,740 |
| nflboard.json | 277,633 | 10,320 |
| board.json | 90,052 | 10,222 |
| props.json | 25,441 | 3,612 |
| best_lines.json | 7,788 | 1,215 |

```
curl -s -o /dev/null -w "%{size_download}" https://sooth.bet/data/<p>.json
curl -s -H "Accept-Encoding: br" -o /dev/null -w "%{size_download}" https://sooth.bet/data/<p>.json
```

Against the 2026-08-27 baseline in this file, `research.json` went
**1,373,763 → 740,104 bytes on disk (−46%)** and **58,612 → 36,636 over the
wire (−37%)**. The parse-and-memory cost this plan actually cared about is
roughly halved on `/research` and `/game`, which was the stated goal.

**It is no longer the largest payload the site serves.** `whales.json` now
downloads more (40,377 vs 36,636), and `research.json` sits in the same band as
timeline, injuries and moves. The premise that started this item — an outlier
worth special treatment — is gone. Both "deliberately not doing" items stand
unchanged and should stay not-done: compacting the JSON buys nothing over the
wire and makes a file that churns every 30 minutes produce unreadable diffs,
and splitting per game would cost the instant expand-a-row behaviour for a
saving that no longer exists.

### The guard, watched failing

`tests/test_research.py::TestPublishedPayload::test_movement_carries_only_line_history`
is the check from step 4. Injected a `movement.spread` series into the first
report in the published `site/public/data/research.json` and it **FAILED**,
naming the offending key and pointing back at this file. Reverted immediately;
`git status` clean. `movement()` itself is gone from `engine/research.py`, so
the series cannot be produced by the generator either — the test guards against
it coming back by another route.

### Noted, not acted on

`whales.json` is now the largest payload at 40 KB over the wire. That is an
observation, not a finding: nobody has checked whether any of it is unread, and
this plan's whole lesson is that the on-disk number is not the cost and that
the question is "does anything read it", not "how big is it". If it is ever
worth pursuing it needs its own read-audit, not a size argument.
