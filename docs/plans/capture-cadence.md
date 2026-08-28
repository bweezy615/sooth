# Capture cadence and the Odds API budget

Written 2026-08-28 by the supervisor agent. **This memo asked for a decision
and made none.** Cadence and spend were both reserved to Branden.

## DECIDED 2026-08-28 by Branden: option A

Split the free half onto its own workflow. Shipped the same day, the night
before college football week 1, as `.github/workflows/capture-evidence.yml`:
`engine.capture` for `nfl` and `ncaaf` on `13,43 * * * *`, committing only
`data/capture`, sharing capture.yml's `capture-odds` concurrency group so the
two can never race each other's rebase.

Two things about the shipped form differ from the sketch below, both
deliberate:

- **`capture.yml` keeps its own ESPN capture step.** Removing it would have
  been the tidier diff and the wrong one. GitHub drops `schedule` events, which
  is half of what this memo is about, so two independent schedules writing the
  same append-only series is redundancy, not waste: a run dropped on one is
  covered by the other. Duplicate observations are harmless here - the file is
  a time series keyed by `observed_at`, and more observations is the goal.
- **The paid board build was not touched at all.** Option A's whole point is
  that the free half stops being rationed by the paid half's budget. Changing
  both at once would have made a bad Saturday impossible to diagnose.

**Still open, and still Branden's:** the board build spends 5 credits a run.
(This sentence used to open "the Odds API plan is 500 credits/month". That was
wrong — it was a reading of a *different key* than the one CI uses. See
"Correction, 2026-08-28: there are two keys" at the foot of this memo. The
question stays open; the number it was framed with does not.) This split does nothing about that, by design -
it stops the *evidence* depending on it. Options B, C and D below remain live
questions about the board. C's copy half is already done: `/market` no longer
says "LIVE PRICING".

## The short version

Two problems are hiding each other, and each one is the reason the other has
not caused an outage yet.

1. `.github/workflows/capture.yml` asks for a run every 30 minutes. It is
   getting about three a day.
2. ~~The Odds API plan is 500 credits a month. The board build spends 5 per run.
   Three runs a day is 450 a month — almost exactly the plan.~~
   **Wrong, corrected 2026-08-28.** That 500 belongs to a key CI does not
   use. The account the site actually runs on had 3,008 credits left the
   same morning. See the correction at the foot of this memo. Problem 1
   (the scheduler) is real and unaffected; problem 2 as stated is not.

So the schedule is broken, and the budget can only afford a broken schedule.
Fix either one alone and the other breaks loudly.

## What was measured, 2026-08-28

Scheduled runs of `capture.yml`, against a `*/30` cron that asks for 48 a day:

| date | runs |
|---|---|
| 2026-08-23 | 32 |
| 2026-08-24 | 23 |
| 2026-08-25 | 24 |
| 2026-08-26 | 16 |
| 2026-08-27 | 3 |
| 2026-08-28 | 3 (pace, at 07:40Z) |

Every other scheduled workflow in the repo shows the same collapse, so it is
not something in this workflow. The repo is public, so Actions minutes are free
and this is not a billing stop. Jobs that do start succeed in 1–3 minutes.
The remaining explanation is GitHub dropping `schedule` events, which it
documents as best-effort and which it does hardest on the `:00`/`:30` minutes
that a `*/30` cron lands on.

Odds API, same morning: `x-requests-used: 387`, `x-requests-remaining: 113`.
A 500-credit allowance with 22 board builds left — **on the key that shell
had loaded, which is not the key CI runs on.** Reading corrected 2026-08-28;
see the foot of this memo. The scheduler collapse measured above stands on its
own evidence and does not depend on this.

## Why this matters more than it looks

College football week 1 kicks off 2026-08-29. ESPN deletes a game's odds block
when the game ends and there is no backfill anywhere, so the run that does not
happen before kickoff is evidence that cannot be bought back afterwards. At
three runs a day, Saturday's seven games get one or two observations each and
probably none close to kickoff — which is the observation the whole archive
exists to hold.

The board build is the expensive half. The evidence half is free: `engine.capture`
reads ESPN and spends nothing. They currently share one workflow and therefore
one schedule, so the free half is rationed by the paid half's budget for no
reason other than that they were written together.

## What a fix costs

Free capture (`nfl` + `ncaaf`, `--weeks 2`) writes about 339 KB per cycle,
measured from today's files:

| runs/day | repo growth |
|---|---|
| 3 (today) | 1.0 MB/day, 30 MB/month |
| 12 | 4.0 MB/day, 119 MB/month |
| 24 | 8.0 MB/day, 239 MB/month |
| 48 (what the cron asks) | 15.9 MB/day, 477 MB/month |

`data/capture` is already 179 MB. This is committed, permanent, and the point:
the git timestamps are the third-party attestation. But it is not free of cost
and the rate is a real choice.

## The options, with what each one actually buys

**A. Split the free half onto its own workflow.** `engine.capture` for nfl and
ncaaf, its own cron on an off-peak minute (`13,43 * * * *` rather than `*/30`,
because the contended minutes are the ones GitHub drops), committing only
`data/capture`. The paid board build stays exactly where it is. Costs no money;
costs repo growth per the table. This is the only option that protects
Saturday. Needs a shared `concurrency` group with `capture.yml` so two
workflows never push at once.

**B. Raise the Odds API plan.** Money. Makes the board genuinely refresh at
whatever cadence GitHub will give us, which is the separate problem.

**C. Accept ~3 board refreshes a day and say so.** The board already stamps
itself honestly (`generated_at`, and `desk.js` marks a feed stale past 3 hours),
so this is not dishonest — but the page currently reads "LIVE PRICING", and a
board refreshed three times a day is not that. If this is the answer, the copy
should change with it.

**D. Spend fewer credits per run.** `engine/nflboard.py` already shows the
pattern: build spreads and totals from our own free ESPN capture instead of
buying them. Generalising it would cut what the paid call has to cover. Real
work, no money, and it does nothing before Saturday.

A and C are compatible and probably belong together. A is the one with a
deadline attached.

## What was deliberately not done

The agent did not change any cron, did not add a workflow, and did not spend a
credit beyond one board rebuild needed to verify the UFC→CFB swap. Widening
capture was named as Branden's call and this memo exists instead of a commit.

---

# Addendum, 2026-08-28: the balance is measurable, and it runs out during NFL week 1

Option A shipped. The board half is still open, and this is the number it was
missing. Nobody had to buy anything to get it: `engine/props.py` already reads
the Odds API's `x-requests-remaining` header and writes it into
`site/public/data/props.json`, which is committed on every run. Fourteen days
of git history is therefore fourteen days of balance readings.

```
2026-08-14 05:43   6,071 remaining
2026-08-28 06:04   3,008 remaining
                   ------
  14.0 days, 80 samples, 3,063 used  =  219 credits a day
```

At 219 a day, **3,008 credits is about 14 more days and empties around
2026-09-11.** No reset appears anywhere in the fourteen days, so this reads as
a fixed pool rather than a monthly allowance — worth confirming against the
account, because it changes the answer completely.

**NFL week 1 kicks off 2026-09-09.** On the current burn the credits run out
inside the first weekend of the season the site is built for. That is the
deadline this decision actually has, and it is two weeks away, not abstract.

Two things follow that were not obvious before:

- **The GitHub throttling is currently the only thing keeping the account
  alive.** `capture.yml` is written for `*/30` and reasons about ~192 credits a
  day; measured burn across all paid workflows is 219. If the scheduler ever
  started honouring the crons, the burn would go up, not down. Fixing the
  throttling (see `scheduled-runs-and-silent-green.md`) without first fixing
  the credit budget would empty the account in days.
- **Option D is worth more than it looked.** Cutting credits per run is the
  only option that buys time without spending money, and there are now two
  weeks in which it could.

Recorded, not decided. Nothing here changes a cron, a plan or a spend.

One reporting gap, small: `engine/lines.py` reads `x-requests-last` and records
`credits_spent` in board.json, but ignores `x-requests-remaining` even though
the header is in the same response. `engine/props.py` records both. Adding it
to `lines.py` is three lines and would put the balance on the board build too,
but it cannot be verified without spending a credit, so it was left.

---

# Correction, 2026-08-28: there are two keys, and this memo was reading both

This memo contradicted itself. It opened by stating the Odds API plan is **500
credits a month**, and closed, a hundred lines later, with a measured balance of
**3,008 credits remaining**. Those cannot both describe one account. The
contradiction sat in one document for a day without either half being doubted,
because each half arrived from a different place and neither was ever put next
to the other.

Both readings were true. They are different API keys.

## The evidence

**One.** Every balance in `props.json` is written by CI, which runs
`engine/props.py` with `secrets.ODDS_API_KEY`. That series is continuous and
monotonic across 22 days of git history — 7,363 on 2026-08-06 down to 3,008 on
2026-08-28 — with no reset and no discontinuity anywhere in it. A 3,008 reading
is arithmetically impossible on a 500-credit plan.

**Two.** The 500 readings all came from a shell, not from CI. Taken in sequence
they are internally consistent and unmistakably one small account:

| when | used | remaining | sum |
|---|---|---|---|
| `college-football.md` | 380 | 120 | 500 |
| `capture-cadence.md` (above) | 387 | 113 | 500 |
| this session | 391 | 109 | 500 |

Used ticks up, remaining ticks down, the pair always sums to 500. That is the
Odds API free tier.

**Three.** The last row is a live reading taken during this session with the key
this machine's shell has loaded, against `/v4/sports/` — the endpoint
`engine/lines.py` already documents as free (`active_sports`: *"This call is
free."*). It returned `x-requests-last: 0`, confirming it cost nothing. So the
shell key is on a 500 plan **right now**, on the same morning CI recorded 3,008.

Two accounts. Not one account read two ways, and not a per-endpoint sub-quota.

**A precision note.** The pair "used 380, remaining 113" sums to 493 and looks
incoherent. It is — it does not exist. It is one half of each of the first two
rows above, accidentally combined. Each real reading sums to exactly 500.

## What this changes, and what it does not

**The fuse is real and the addendum above stands.** The site runs on
`secrets.ODDS_API_KEY` — every workflow in `.github/workflows` uses it and
nothing uses anything else. That is the 3,008 account, burning 219 a day,
empty around **2026-09-11**, two days into NFL week 1. Nothing here relaxes
that. The 3,008 figure was the right number attached to the right key all
along.

**The throttling caution stands too, unchanged.** GitHub dropping scheduled
runs is still the only thing holding burn at 219/day, and honouring the crons
would still empty the account faster. Correcting the plan size does not buy a
single credit. **This is not a reason to loosen a cron.**

**Two statements elsewhere were wrong and are now corrected.** They are marked
in place above, and one more lives in `college-football.md`: that the 500
allowance "is why the live board is refreshing a few times a day". It is not.
This memo's own measurement found the cause — GitHub dropping `schedule`
events — and the board build was never budget-limited at three runs a day
anyway. That sentence asserted a cause the evidence in the same repo already
contradicted.

## What is still not known, and how to settle it

The plan **size** and **reset date** of the CI account. The evidence narrows it
but does not close it:

- On 2026-08-04 a reading of 7,535 remaining against 12,465 used summed to
  **20,000**, and `props.json` recorded 7,363 two days later. Those line up, so
  the CI account was a 20,000-credit plan at the start of August.
- Whether that pool refills monthly, and on what date, cannot be recovered from
  git: the balance series runs 2026-08-06 to 2026-08-28 and contains no month
  boundary. 12,465 credits were used by August 4th, which at today's ~220/day
  would take two months — so either the cycle does not start on the 1st, or
  early-August burn was far higher (`engine/backfill.py` spends 10 credits a
  call on historical odds, which would do it).

**This matters, because it changes the answer completely.** If the pool refills
on 2026-09-01 there is no crisis: the account refills before NFL week 1 and the
9/11 date is a prediction of a drought that will not happen. If it is a fixed
pool, or renews mid-month, the fuse is exactly as described.

**For Branden — the one thing to look at.** Log in at
`the-odds-api.com/account`. It shows the plan's monthly quota and the date the
usage counter resets. Two numbers, and they close this permanently:

1. **Monthly quota** — expected 20,000. If it says 500, then CI is running on
   the free key too and the situation is far worse than this memo says.
2. **Usage resets on** — if that date falls before 2026-09-09, the week 1
   deadline disappears and options B/C/D can be decided at leisure. If it falls
   after, the deadline is real and it is 12 days away.

**And it may answer itself for free.** `engine/lines.py` now records
`credits_remaining` *and* `credits_used` into `board.json` on every board build,
from headers that ride along on a call already paid for. The next scheduled run
writes the pair, and remaining + used **is** the plan size. A reset then shows
up as `credits_used` falling to near zero, which dates the anniversary without
anyone logging in anywhere. This was the "one reporting gap, small" noted at the
end of the addendum above; it is closed, and it was the gap that let a 26x
discrepancy hide in the first place.

## The lesson, which is the site's own

A wrong number in a planning doc is the same defect class this repo spends its
time fixing on the public pages. It got in the same way, too: a figure read once
in one context, written down as a general fact, and never put beside the other
figure that would have contradicted it. The repo already knows the fix, from
`figures.json` — **if two artifacts must agree, one command writes both.** The
balance now comes from one place, on every paid run, with the denominator
attached.
