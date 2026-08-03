#!/bin/bash
# Odds capture wrapper. Invoked by launchd (local) and GitHub Actions (remote).
# Deliberately dumb: no arguments, absolute paths, logs everything.
# A closing line we don't capture is one we can never get back, so this script
# must never fail silently.
set -uo pipefail

REPO="/Users/b/pick-engine"
LOG="$REPO/data/capture/capture.log"
mkdir -p "$(dirname "$LOG")"

cd "$REPO" || { echo "$(date -u +%FT%TZ) FATAL cannot cd $REPO" >>"$LOG"; exit 1; }

echo "$(date -u +%FT%TZ) START" >>"$LOG"
if "$REPO/.venv/bin/python" -m engine.capture --season 2026 --weeks 2 >>"$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) OK" >>"$LOG"
else
  echo "$(date -u +%FT%TZ) FAILED rc=$?" >>"$LOG"
fi

# Keep the log from growing without bound.
tail -n 2000 "$LOG" >"$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
