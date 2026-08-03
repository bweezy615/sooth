# Overnight report — 2026-08-03

Updated each pass. Newest work at the top of each section.

---

## Completed

### P0 — Commitment versioning ✅

**Problem found:** re-sealing Week 1 for the dual-model launch overwrote
commitment root `d081c00f…` with `4136512c…` *silently*. Revising predictions
before kickoff is legitimate; a root vanishing without trace is not — to an
outside reader it is indistinguishable from tampering, which defeats the
entire product.

**Fixed:** commitments are now versioned and append-only.

- `<slate>.commitment.v{N}.json` / `<slate>.reveal.v{N}.json`, retained forever
- Each carries `version` and `supersedes` (the prior root), forming a chain
- `commitment_history()` returns the full sequence
- `verify_slate(..., version=N)` verifies any version, so a reader who
  recorded an older root can still confirm it
- Re-committing identical predictions does **not** mint a new version
- Legacy unversioned files still verify (no migration required to read them)

**v1 was recoverable only because we happened to have committed to git.** That
is luck, not design, and it is precisely the accident this fix removes.

**Verification:**

```
$ python -c "from engine.commit import verify_slate, commitment_history; ..."
v1  n= 16  root=d081c00f901874be...  supersedes=None
v2  n= 32  root=4136512cf38a8074...  supersedes=d081c00f901874be
verify latest : True
verify v1     : True
verify v2     : True
```

The `/ledger` page now renders the superseded root alongside the current one,
with an explanation of why revisions before kickoff are legitimate.

Branch: `overnight/commitment-versioning`

---

## Verified this pass

- **Odds API credits spent: 0.** Budget for the night is 500; 7,580 remain on
  the plan.
- **Nothing under `data/capture/` or `data/ledger/` was rewritten.** The v1/v2
  migration only added files.
- **No secrets staged.** Checked with
  `git diff --staged | grep -iE 'apikey|api_key|[0-9a-f]{32}'` — clean.

## Outstanding / unverified

- **The GitHub Actions capture cron has still never fired unattended.** Every
  successful run so far was `workflow_dispatch` (manual). A watcher is armed
  and will report the first `schedule` run. Until that fires, autonomous
  capture is an assumption, not a fact. GitHub is known to delay or skip
  schedules on new repositories.
- **Vercel deploy still failing as of the last check.** Two fixes pushed
  (`framework: null`, then `.vercelignore` excluding `pyproject.toml`). If the
  build still fails, the fallback is setting Root Directory to `site/public`
  in project settings, which requires moving `vercel.json` into that folder —
  that is a change I should not make blind, since it breaks the current layout
  if the setting is not also changed.

## Decisions deferred to you

1. **Which model leads the front page.** Both now publish, labelled, as you
   asked. The table currently shows Independent first. That ordering is an
   editorial choice with real consequences — Independent is our honest opinion
   and worse; Consensus is better calibrated and mostly echoes the market.
2. **Whether superseded commitments should be shown by default or behind a
   disclosure.** Currently always visible. Maximally honest; also draws the
   eye to a revision that most readers will not need to care about.

## Reproduction commands

```bash
python -m engine.backtest                    # elo baseline, nflverse lines
python -m engine.models.ensemble             # 4-model walk-forward comparison
python -m engine.pipeline.weekly --season 2026 --week 1
python scripts/build_site.py
python -c "from engine.commit import verify_slate; print(verify_slate('2026-W01-nfl'))"
```
