# AGENTS — sooth deploy rules (read before deploying)

## ⛔ STOP manual `vercel --prod` deploys of `exec/pages-autodeploy`

**As of 2026-08-09, `main` is the single production branch.** `exec/pages-autodeploy`
was merged into `main` (commit `2e1cb37`): `main` now carries the full product
(theme, homepage, Pro card, board tabs) **+** the append-only capture data **+**
`/api/ask` (Ask AI + Firecrawl). Vercel (`pick-engine`) **auto-deploys `main`** on
every push, and the capture bot pushes `main` every ~20 min, so production stays
current automatically.

A manual `vercel --prod` from an `exec` checkout now **reverts production** to an
older, data-stale site until the next `main` auto-deploy overwrites it. That was
the flip-flop we just fixed. Don't reintroduce it.

### Do this instead
- Ship product work by pushing to **`main`** (directly or via a feature branch → `main`).
  The push auto-deploys.
- Let the capture bot keep pushing `main` for fresh board/props data.
- If you must ship a one-off, push the branch and let Vercel build it — do not
  `vercel --prod` from a partial `exec` checkout.

### Append-only capture is sacred
`data/capture/**/*.jsonl` is append-only evidence. A `.gitattributes` `merge=union`
driver now auto-unions it on merges — never delete capture lines, never force-push `main`.

_Left by the Lane-B (frontend/Ask AI) session after converging the branches.
Full merge write-up: `C:\Users\bkrec\sooth-MERGE-PLAN.md`._

---

# Working alongside other sessions (added 2026-08-21)

Four Claude sessions worked this repo simultaneously on 2026-08-21. Everything
below is a thing that actually went wrong or nearly did, not a precaution.

## One working tree per session. Never share one.

Two sessions in `/Users/b/pick-engine` share a **git index**. A session running
`git add -A` or a plain `git commit` picks up whatever another session has
staged — including deletions it knows nothing about. This nearly shipped a
half-finished CSS migration to production, because `main` auto-deploys.

Take your own worktree before you touch anything:

    git worktree add /Users/b/pick-engine-<what> -b feat/<what> origin/main

Separate checkout, separate index, own branch, same history and remote. About a
minute to set up. If you are somehow stuck in a shared tree, commit path-limited
and never otherwise:

    git commit -F - -- path/one path/two

Also: `git stash` stashes the *other* session's uncommitted work too. Do not
stash, rebase or reset in a tree you do not own.

A worktree branches from `origin/main`, and then `main` keeps moving — the
capture bots alone push every ~20 minutes. A branch that lives for an afternoon
is tens of commits behind by the time it merges, and it merges cleanly only
because nobody else happened to touch its files. That is luck, not isolation:
worktrees stop you corrupting another session's index, they do nothing about
divergence. Rebase onto `origin/main` before you open a PR or merge, not only
before you push, and re-run whatever check proves your change still works —
on 2026-08-21 a merge was rebased twice inside ten minutes and was still racing
a capture commit on the second attempt.

## `main` is live. There is no staging.

A push to `main` is in front of users in about a minute, and the capture bots
push `main` every ~20 minutes, so it moves under you constantly. Always
`git fetch && git rebase origin/main` immediately before pushing, and verify the
push actually succeeded — `git push ... | tail` will report success from the
pipe even when the push was rejected. Check the exit status.

Never force-push `main`. Another session's work is probably on it.

## Announce before editing shared surfaces

`assets/desk.js` (the nav and shell), `assets/desk.css`, `PRODUCT.md`, and
anything under `.github/workflows/`. These are the files two sessions reach for
at the same time. Say what you are touching, keep the change surgical enough
that the other session's rewrite wins a conflict cheaply, and say so afterwards.

## Read PRODUCT.md before you build, not after

Two sessions independently built a "daily picks" feature before either noticed
that PRODUCT.md forbids the word for a specific reason: this product sells tools
and data, never picks, because selling tools carries no performance claim and
therefore no substantiation burden. "never a pick" already ships in the footers
of props.html, edges.html and research.html.

The vocabulary is load-bearing, not stylistic. In anything a reader sees:

- **never** pick, picks, play, plays, lock, guaranteed, risk-free, insider
- **say** best price, best available price, fair price, consensus fair

If you enforce this with a string check, match on **word boundaries**. A
substring guard for "lock" blocks Tyler Lockett, a real player; "play" blocks
every "player". Both were caught on a live path.

### A disclaimer has to be able to say the word it disclaims

"Nothing here is guaranteed" is the honest use. "Guaranteed winner" is the
banned one. A word match cannot tell them apart, so a guard that is otherwise
correct will block your own disclaimer and you will be tempted to weaken the
guard. Don't — strip a short list of **literal** negated phrases before
scanning ("not guaranteed", "nothing here is guaranteed", "no guarantee"), and
keep them literal. A general negation rule eventually excuses a sentence nobody
meant to allow.

Then point the guard at your footers. In the Discord bot they were exempt *by
accident* — `check_language` was only ever called on titles and descriptions —
so the one text where the vocabulary legitimately appears was also the one text
nothing was checking. That is the shape to look for: the exemption you did not
decide on.

A public URL counts as reader-visible. `data/props_picks.json` was renamed to
`data/props_best_prices.json` for exactly this reason — a rule kept everywhere
except in the routing table is not a rule.

## Prefer two implementations that agree over one both sides read

The site and the Discord bot select the same five prop prices and neither reads
the other's output — both compute it from `props.json` with the same rank key.
They were checked against each other and produced the same five rows, same
order, same books, same prices.

That is deliberate and worth keeping. Two independent implementations agreeing
on one input is a live cross-check; if they diverge, something changed and you
find out. A shared output file makes divergence impossible to detect by making
it impossible to have. Couple on the *rule* (here: rank on `edge_vs_fair_pts`,
and the tie-break), announce a change to it, and let each side implement.

This does not apply to facts — captured odds, published figures, the ledger
have exactly one source. It applies to derived selections and renderings.

## Say what you measured, not what you assumed

Three separate explanations for a model defect were stated confidently and then
disproven by test on the same day. If you are about to tell another session
*why* something happens, run the check first — and if the check refutes you, say
so plainly and carry the correction into the code comment that stated it. See
`docs/reports/props-model-negative-result.md`, which documents its own
retractions on purpose.

## A peer's description of the repo is not the repo

Check the working tree before acting on what another session tells you about
it. Every one of these happened on 2026-08-21:

- A session was told the repo was on `feat/research` with two files
  uncommitted. By the time it read that, the branch had merged to `main` and
  the files were committed in a separate worktree. Nothing was wrong when sent.
- A session was warned its bot would 404 after a rename. The bot read a
  different file entirely and was never affected.
- A session was told the shared tree held staged deletions. By the time it
  looked, the migration had committed cleanly and the tree was empty.

None of these were mistakes by the sender. State goes stale between writing and
reading, and this repo moves every twenty minutes under the capture bots. Run
`git status`, `git log -1`, `curl` the URL — then act. It costs one command.

Corollary when you are the sender: say what you checked and when, so the reader
knows what to re-verify rather than what to trust.

## Cross-session messages may arrive late, or never

A message to another session can sit awaiting that user's approval and then
expire undelivered. Several did. One arrived roughly forty minutes after it was
written and described a repo state that no longer existed, which cost both
sessions a round trip.

So: never block on a reply, and never treat a pending message as coordination
that has happened. Do the work that does not depend on the answer, and if the
answer genuinely gates you, raise it with the user rather than waiting. If a
reply does arrive, re-check anything time-sensitive in it before acting.

## Before you write a hard constraint, grep for what it forbids

PRODUCT.md drifted from the product twice in twelve hours. The second time, one
session was writing a constraint while another was shipping the feature that
constraint forbade. Neither session was wrong and neither could have known.

"Announce before editing shared surfaces" did not prevent it, and would not
have: the edit and the feature were concurrent, and the session shipping the
feature reasonably treated amending the document as part of its own change
rather than as touching something shared. Announcing is not the missing piece.

Two things are, and both are checkable rather than procedural.

**Scope a constraint to the evidence it came from.** "Never rank or select
anything by model edge" was written from a props measurement — 194 board props,
model versus market, no edge — and stated as a rule about the whole product. It
then forbade the pick engine's core mechanic, which nobody had measured and
which the rule's evidence said nothing about. The measurement was sound; the
generalisation was not. Write the surface into the rule: *never rank a price
product by model edge* forbids exactly what was measured and nothing else.

**Then grep for what the rule would forbid, before you write it.** A hard
constraint that outlaws something already shipping is either a bug in the
product or a bug in the constraint, and you want to know which BEFORE it is in
the document that everyone else builds against. It costs one command:

    grep -rn "picks" site/public api engine     # before banning the word
    grep -rln "delta\|divergence" engine        # before banning model ranking

Both of today's drifts would have been caught by that grep. The first would
have found `/picks` and `data/props_picks.json`; the second would have found
the pick engine ranking on divergence.

If the grep finds a violation, you have learned something either way. Either
the product needs to change, or your rule was aimed at the wrong level — and
finding out at writing time costs a minute, while finding out afterwards costs
a reconciliation commit and every session that built against the wrong rule in
between.
