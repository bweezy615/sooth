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
