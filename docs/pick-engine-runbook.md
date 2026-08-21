# Pick Engine runbook

## Normal week (all automatic)
- **Wed 09:00 ET** — `seal.yml` seals the next slate: ledger + `data/pro` +
  redacted public payload, one commit. The push is the timestamp anchor.
- **Tue 09:00 ET** — `grade.yml` grades the latest slate, publishes
  `{slate}.graded.json`, refolds `pickengine-record.json`, one commit.

## If Wednesday's seal cron missed
Run it by hand — BEFORE the first kickoff or not at all:

    python scripts/next_slate_week.py            # prints "SEASON WEEK"
    python -m engine.pipeline.weekly --season 2026 --week N
    git add data/ledger data/pro site/public/data
    git commit -m "seal: 2026-W0N-nfl (manual)" && git push

`commit.py` refuses to seal past kickoff. If it refuses, the answer is no
slate this week — never a backdated one. That refusal is the product.

## If Tuesday's grade cron missed
    python -m engine.grade --slate "$(python -c "import json;print(json.load(open('site/public/data/slates.json'))['latest'])")" --publish
    python scripts/publish_record.py
    git add site/public/data data/ledger && git commit -m "grade: manual" && git push

## Invariants (do not negotiate)
- No published number outside `published_figures.py` / `publish_record.py` output.
- Losses render identically to wins. `clv:null` keeps its reason verbatim.
- Redaction happens in Python at write time; `/api/picks` is the only gate.
- Deferred by written decision (see plan): market-blend model, QB feature,
  line-movement feature (unbacktestable on nflverse closes), Stripe webhook
  re-check (v1 accepts the 60-day cookie gap).
