# Capture cadence and the Odds API budget

Written 2026-08-28 by the supervisor agent. **This memo asks for a decision and
makes none.** Cadence and spend were both reserved to Branden.

## The short version

Two problems are hiding each other, and each one is the reason the other has
not caused an outage yet.

1. `.github/workflows/capture.yml` asks for a run every 30 minutes. It is
   getting about three a day.
2. The Odds API plan is 500 credits a month. The board build spends 5 per run.
   Three runs a day is 450 a month — almost exactly the plan.

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
A 500/month allowance, and 22 board builds left this cycle.

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
