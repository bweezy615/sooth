# research.json is not the problem it was written down as

Written 2026-08-29 by the supervisor agent. **Findings only — nothing changed.**
The shape of the fix touches pages another agent is redesigning, so this is a
handoff, not a commit.

The standing backlog says: *"`site/public/data/research.json` is 1.5 MB, roughly
3x the next-largest payload, and every visitor to that page downloads it."*

Two of those three claims no longer hold, and the third is measured wrong.

## What is actually true

**It was 1.5 MB. It is not now.** On disk it has already roughly halved without
anyone recording it:

| date | size on disk |
|---|---|
| 2026-08-21 | 1,182 KB |
| 2026-08-23 | 1,304 KB |
| 2026-08-25 | 1,338 KB |
| 2026-08-28 | 703 KB |

**On the wire it is 37 KB.** This is the number that matters and nobody had
measured it. Vercel serves it brotli-encoded:

```
$ curl -s -o /dev/null -w "%{size_download}\n" --compressed \
      https://sooth.bet/data/research.json
36958
```

For comparison, on the same measurement `whales.json` transfers **41 KB** —
*more* than research.json. So research.json is not "3x the next-largest
payload" as delivered; it is not even the largest. JSON this repetitive is
almost all redundancy, and brotli is very good at redundancy.

**It is not on a path every visitor takes.** Only `game.html` and
`research.html` fetch it.

**Conclusion: this is not a bandwidth defect, and optimising it for bandwidth
would be work spent against a number that was never measured.** Pretty-printing
accounts for about a third of the file on disk (703 KB pretty, 485 KB
minified), and minifying would save almost nothing on the wire, because
whitespace is exactly what compression removes first.

## What *is* still worth something, and why it is smaller than it looks

Two real inefficiencies survive the above. Both cost parse time, client memory
and committed repo growth — not bandwidth.

**1. Every team's injury block is embedded about three and a half times.**
`injuries` is 202 KB of the 485 KB minified, 42% of the file. But the file
holds 56 reports covering 32 distinct NFL teams, so each team appears in ~3.5
reports and its full injury roster is serialised again each time:

```
distinct teams: 32
teams appearing more than once: 32
most common: Seattle 4, New England 4, LA Rams 4, San Francisco 4
```

Hoisting injuries into a `teams: {...}` map keyed by team, with reports
referencing it, removes roughly 145 KB of the 485 KB — about 30% — with no
information lost. That change is in `engine/research.py`, but it changes the
payload shape that `game.html` and `research.html` read, so it cannot be done
from one side alone.

**2. `game.html` downloads all 56 reports to render one game.** Splitting
per-game, or serving an index plus one report, would cut what a game page
parses by ~98%. Same caveat: it is a shape change across both trees.

**3. A separate `injuries.json` (131 KB) already exists** and carries the same
upstream ESPN data. Whether the embedded copy is needed at all is worth a look
before anything is deduplicated — the cheapest fix may be to stop embedding it.

## Recommendation

Leave it alone for now, and re-title the backlog item. It is a payload-shape
and parse-cost question worth maybe 30% of a 37 KB response, not the 1.5 MB
bandwidth emergency it reads as. If the research page is being redesigned
anyway, fold item 1 into that work, where the consumer and the producer can
change together.

## The general point, which is the same one as this week's other findings

The backlog item was written from `ls`, and `ls` is not what a visitor
experiences. The number that justified the work was never the number the user
pays. This is the same defect class as the credit contradiction resolved the
same day: a figure measured once, in one context, written down as a general
fact, and then relied on by a decision. Measure the thing the claim is about.
