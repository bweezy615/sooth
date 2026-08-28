# Two ways this repo can look fine while producing nothing

Written 2026-08-28 by the supervisor agent, after the `capture-evidence`
defect (a workflow that installed the wrong dependency, failed both of its
steps, and reported success because each carried `continue-on-error`).

One half is **fixed**. The other half is **found, measured, and needs a
decision from Branden**, because the fix costs money or costs freshness and
neither is mine to choose.

---

## 1. Green over an empty run — swept, two fixed

Every workflow that uses `continue-on-error` was read.

| workflow | verdict |
|---|---|
| `capture.yml` | fine, deliberately. The Odds API board and the timeline are guarded, but the two ESPN capture steps are not, so a total failure is red. The file says so in a comment. |
| `capture-props.yml` | fine. No guard on the capture step at all. |
| `research.yml` | fine. Injuries and team form are guarded; `engine.research`, the step that composes the reports, is not. |
| `edges.yml` | **was broken.** Both steps guarded. If both died the job went green, the commit step printed "no change in edges data", and the Edges tab kept serving yesterday. |
| `props-live.yml` | **was broken.** The refresh is the whole job and it was guarded, so `engine.props` could have failed on every run — bad key, missing dep, API change — with the workflow reporting success each time. |

Both now carry a final step that fails the job when the meaningful work did
not happen. It sits **after** the commit deliberately: anything that was
written still gets saved before the run goes red. `edges.yml` keeps the guard
on middles, because a transient Odds API failure must not cost the moves
rebuild; it is the zero-credit step, which reads only committed capture and
has no legitimate reason to fail, that is now allowed to redden the run.

The general rule, for the next workflow: **the last meaningful step in a job
must be able to fail it.** A guard is for a step whose failure the rest of the
job can survive, never for all of them.

---

## 2. The schedules are not the schedules — Branden's call

Noticed while checking the above. `capture-odds` is set to `*/30 * * * *`,
which is 48 runs a day. Measured from `gh run list` on 2026-08-28:

```
06:52Z   05:34Z   (78 min apart)
05:34Z   2026-08-27 21:06Z   (8h 28m)
21:06Z   11:04Z   (10h 02m)
11:04Z   00:36Z   (10h 28m)
```

Roughly four to eight runs a day, with gaps up to ten and a half hours,
against a schedule asking for forty-eight. Every run **succeeds** — this is
GitHub declining to start scheduled runs, not anything failing. `refresh-edges`
is the same: set to every two hours, actual gaps of two to ten.

The consequence, measured at 14:25Z on 2026-08-28:

```
board.json     7.5h old        (designed: 30 min)
props.json     8.4h old
middles.json   8.4h old        (designed: 6h ceiling)
moves.json     7.4h old        (designed: 2h)
```

That is college football week one, and the board is the better part of a day
old. Nothing on the site claims a refresh cadence in words — that was checked
— and every surface that shows an age shows the real one, so the site is not
lying. It is just much less live than it is built to be.

**What needs deciding, and why it is not mine.** The plausible fixes all cost
something Branden owns:

- fewer scheduled workflows, or coarser crons, so GitHub honours the ones that
  remain — costs freshness, and overlaps with the Odds API budget question in
  `capture-cadence.md` that is already open;
- a paid Actions tier, or a self-hosted runner — costs money;
- an external ping (cron-job.org and friends) firing `workflow_dispatch`
  instead of relying on `schedule` — costs nothing but adds a dependency
  outside this repo, and dispatch is not throttled the way schedule is.

The third is the interesting one and would probably fix it outright. It is
still a change to how the whole site refreshes, so it is a decision, not a
defect.

---

## 3. /edges was quoting the wrong clock — fixed

Found while measuring the above, and a real honesty defect rather than an
infrastructure one.

`/edges` renders four payloads on three different schedules and displayed a
single `SNAPSHOT ... AGO` reading taken from `board.json`, the most frequently
refreshed of them. On a normal day that puts **"15M AGO" above a middles table
built from prices six hours older**, on a page whose own lede promises "the
timestamp is part of the data, not a footnote on it".

It reads honestly today only by accident: everything is equally stale because
of §2.

Fixed: each section now states the age of the payload it actually renders (the
older of the two, where a section reads two), and the status reading is the
**oldest** payload on the page rather than the freshest. Verified locally by
stamping `board.json` to now — before the change the header would have read
"0M AGO"; after it, it reads the 8.4h of the oldest feed, and the pulse stays
marked stale.

`index.html` and `game.html` also read `moves.json` and do not have this
problem: both label every row with its own `observed_at`.
