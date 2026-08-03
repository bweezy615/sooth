# Sealed — verifiable sports predictions

A prediction engine whose **record cannot be quietly rewritten.**

Every slate is hashed into a Merkle commitment before the first kickoff. After
the games settle we publish everything, and anyone can recompute the hash. If
we altered, removed, or back-dated a single pick, verification fails.

We do not accept wagers. We make no performance claims. Our own backtest loses
to the closing market and that number is on the front page.

---

## Run it

All commands from `/Users/b/pick-engine`. Node isn't needed; Python comes from
the local `.venv` that's already set up.

**Backtest the model** (walk-forward, 2016–2025, ~30s)

```bash
.venv/bin/python -m engine.backtest
```

**Prove the commitment scheme + calibration works**

```bash
.venv/bin/python scripts/verify_core.py
```

**Generate and seal a week's predictions** — must be run before kickoff

```bash
.venv/bin/python -m engine.pipeline.weekly --season 2026 --week 1
```

**Verify a sealed slate** (this is what a skeptic runs)

```bash
.venv/bin/python -c "from engine.commit import verify_slate; print(verify_slate('2026-W01-nfl','data/ledger'))"
```

**Preview the site**

```bash
cd site/public && python3 -m http.server 4173
# then open http://localhost:4173
```

---

## Layout

```
engine/
  schema.py          sport-agnostic Event / Line / Prediction / Result + odds math
  commit.py          SHA-256 Merkle commit-reveal. The differentiator.
  calibrate.py       isotonic calibration, fitted only on prior seasons
  backtest.py        walk-forward scoring vs the de-vigged market
  adapters/
    base.py          the contract every new sport implements
    nfl.py           nflverse ingest + the leakage guard
  models/elo.py      Elo with margin-of-victory damping
  pipeline/weekly.py predict -> calibrate -> cap -> seal -> publish
data/
  raw/               cached source data
  ledger/            *.commitment.json (pre-kickoff) + *.reveal.json (after)
site/public/         static site, deploys to Vercel as-is
docs/DECISIONS.md    what we chose, what the data forced us to change
```

## Adding a sport

Implement `engine/adapters/base.py` and nothing else. The backtester,
calibrator, commitment scheme and site are all sport-agnostic.

A sport is only marked **Live** when it has free, verifiable closing-line
history to grade against. Otherwise it ships as **In calibration** and is
labelled unproven everywhere it appears.

## The one rule

`feature_frame()` is the leakage boundary. Any column that wasn't knowable
before kickoff is banned — `adapters/nfl.py` asserts on the known offenders
(`temp`, `wind`, scores, results). A model trained on post-game weather
backtests beautifully and loses live. That is how most "AI picks" are built,
accidentally or otherwise.

See `docs/DECISIONS.md` for the findings, the compliance posture, and the open
items.
