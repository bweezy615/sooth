#!/bin/bash
# Rebuild the static site from captured data and deploy to Vercel.
# Invoked by launchd (co.sooth.publish) ~30 min after each capture tick.
# Same philosophy as capture.sh: dumb, absolute paths, never fail silently.
set -uo pipefail

REPO="/Users/b/pick-engine"
LOG="$REPO/data/capture/publish.log"
mkdir -p "$(dirname "$LOG")"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
nvm use 22 >/dev/null 2>&1
# launchd starts with a bare PATH; vercel lives in ~/.local/node/bin.
export PATH="$HOME/.local/node/bin:/usr/local/bin:$PATH"

cd "$REPO" || { echo "$(date -u +%FT%TZ) FATAL cannot cd $REPO" >>"$LOG"; exit 1; }

# Refresh the paid-API board at most twice a day (~8 credits/day, fits the
# 500/month tier). ESPN capture is free and runs on its own job.
BOARD="$REPO/site/public/data/board.json"
AGE_H=999
[ -f "$BOARD" ] && AGE_H=$(( ( $(date +%s) - $(stat -f %m "$BOARD") ) / 3600 ))
if [ "$AGE_H" -ge 12 ]; then
  echo "$(date -u +%FT%TZ) BOARD refresh (age ${AGE_H}h)" >>"$LOG"
  "$REPO/.venv/bin/python" -m engine.lines --window-hours 36 --max-credits 60 >>"$LOG" 2>&1 \
    || echo "$(date -u +%FT%TZ) BOARD refresh FAILED — keeping previous board" >>"$LOG"
else
  echo "$(date -u +%FT%TZ) BOARD fresh (age ${AGE_H}h) — skipping paid refresh" >>"$LOG"
fi

# Player props: attempt every cycle so the board picks up new slates within
# ~3h of books posting them. Cheap when books have nothing up: the engine
# bails after two empty events (~6 credits) and keeps the previous snapshot.
PROPS="$REPO/site/public/data/props.json"
# Freshness is judged by the CONTENT (generated_at / checked_at), never file
# mtime — annotation rewrites touch the file without refreshing the data.
PAGE_H=$("$REPO/.venv/bin/python" - <<'PY'
import json, datetime
try:
    d = json.load(open("/Users/b/pick-engine/site/public/data/props.json"))
    ts = max(d.get("generated_at", ""), d.get("checked_at", ""))
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    print(int((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() // 3600))
except Exception:
    print(999)
PY
)
if [ "$PAGE_H" -ge 2 ]; then
  echo "$(date -u +%FT%TZ) PROPS refresh (content age ${PAGE_H}h)" >>"$LOG"
  GEN_BEFORE=$(grep -m1 '"generated_at"' "$PROPS" 2>/dev/null || echo none)
  if "$REPO/.venv/bin/python" -m engine.props --window-hours 30 --max-credits 20 >>"$LOG" 2>&1; then
    GEN_AFTER=$(grep -m1 '"generated_at"' "$PROPS" 2>/dev/null || echo none)
    if [ "$GEN_BEFORE" != "$GEN_AFTER" ]; then
      # Fresh capture: annotate with player game-log hit rates (free API).
      # A kept closing snapshot is NOT re-annotated — rosters move on.
      "$REPO/.venv/bin/python" -m engine.hitrates >>"$LOG" 2>&1 \
        || echo "$(date -u +%FT%TZ) HITRATES FAILED — props stay unannotated" >>"$LOG"
    else
      echo "$(date -u +%FT%TZ) PROPS kept previous snapshot — hitrates skipped" >>"$LOG"
    fi
  else
    echo "$(date -u +%FT%TZ) PROPS refresh FAILED — keeping previous board" >>"$LOG"
  fi
else
  echo "$(date -u +%FT%TZ) PROPS fresh (content age ${PAGE_H}h) — skipping" >>"$LOG"
fi

# Middles/arbs: spreads+totals in one bulk call per sport (~8 credits),
# same 12h age gate as the board.
MID="$REPO/site/public/data/middles.json"
MID_H=999
[ -f "$MID" ] && MID_H=$(( ( $(date +%s) - $(stat -f %m "$MID") ) / 3600 ))
if [ "$MID_H" -ge 12 ]; then
  echo "$(date -u +%FT%TZ) MIDDLES refresh (age ${MID_H}h)" >>"$LOG"
  "$REPO/.venv/bin/python" -m engine.middles --window-hours 36 >>"$LOG" 2>&1 \
    || echo "$(date -u +%FT%TZ) MIDDLES refresh FAILED" >>"$LOG"
else
  echo "$(date -u +%FT%TZ) MIDDLES fresh (age ${MID_H}h) — skipping" >>"$LOG"
fi

# Line-movement scan over our own capture history. Free — no API calls.
"$REPO/.venv/bin/python" -m engine.alerts --out "$REPO/site/public/data/moves.json" >>"$LOG" 2>&1 \
  || echo "$(date -u +%FT%TZ) MOVES scan FAILED" >>"$LOG"

echo "$(date -u +%FT%TZ) BUILD start" >>"$LOG"
if ! "$REPO/.venv/bin/python" "$REPO/scripts/build_site.py" >>"$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) BUILD FAILED — not deploying stale output" >>"$LOG"
  exit 1
fi

if ! command -v vercel >/dev/null 2>&1; then
  echo "$(date -u +%FT%TZ) DEPLOY SKIPPED — vercel CLI not on PATH" >>"$LOG"
  exit 1
fi

echo "$(date -u +%FT%TZ) DEPLOY start" >>"$LOG"
if vercel --prod --yes >>"$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) DEPLOY OK" >>"$LOG"
else
  rc=$?
  echo "$(date -u +%FT%TZ) DEPLOY FAILED rc=$rc (vercel login?)" >>"$LOG"
  tail -n 2000 "$LOG" >"$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
  exit 1
fi

tail -n 2000 "$LOG" >"$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
