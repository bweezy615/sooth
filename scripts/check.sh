#!/usr/bin/env bash
# The full green gate. Nothing ships unless this exits 0.
#
# There is no CI workflow running tests for this repo — .github/workflows/ is
# all data capture. This script is the only thing standing between a bad change
# and sooth.bet, so run it before every push, not just when you feel unsure.
#
#     bash scripts/check.sh
#
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

fail=0
# A red run has to leave something behind. On 2026-08-27 this gate went red
# once, was green on the next seven runs at the same tree, and there was
# nothing left to look at - the later runs had overwritten pytest's lastfailed
# and the console output was gone. An intermittent failure you cannot read is
# indistinguishable from one that never happened. .tmp/ is gitignored.
LOG=".tmp/check-$(date -u +%Y%m%dT%H%M%SZ).log"
mkdir -p .tmp

step() {
  printf '%-46s' "$1"
  local name="$1"
  shift
  if out=$("$@" 2>&1); then
    echo "OK"
  else
    echo "FAIL"
    echo "$out" | tail -25 | sed 's/^/    /'
    { echo "=== FAILED: $name"; echo "\$ $*"; echo "$out"; echo; } >>"$LOG"
    fail=1
  fi
}

step "pytest" python -m pytest tests/ -q
for f in api/_auth.selfcheck.js api/alerts.selfcheck.js api/ask.selfcheck.js \
         api/picks.selfcheck.js tests/frontend/desk.selfcheck.js \
         tests/frontend/picks.selfcheck.js; do
  step "$f" node "$f"
done

# The generated pages must already match what the generator produces. This is
# also covered by tests/test_build_site.py, but running the real builder catches
# anything that only shows up outside the test's temp root.
#
# Compared against the tree as it was a moment ago, NOT against git HEAD. The
# first version of this step used `git diff --quiet -- site/public/`, which
# cannot tell "the builder rewrote a page" from "you edited a page and have not
# committed yet" — so the gate went red on every legitimate uncommitted change
# to site/public/, i.e. on most real work, and would only pass if you committed
# first. A gate you have to commit past is not a gate.
printf '%-46s' "site build is reproducible"
fingerprint() { find site/public -type f -exec sha256sum {} + | sort; }
before=$(fingerprint)
python scripts/build_site.py >/dev/null 2>&1
after=$(fingerprint)
if [ "$before" = "$after" ]; then
  echo "OK"
else
  echo "FAIL"
  echo "    scripts/build_site.py rewrote site/public/ - the generator and the"
  echo "    site disagree. Decide which side is right before rebuilding over it"
  echo "    (git diff will show what the builder just did):"
  diff <(echo "$before") <(echo "$after") | grep -o 'site/public/[^ ]*'     | sort -u | sed 's/^/    /'
  { echo "=== FAILED: site build is reproducible"
    diff <(echo "$before") <(echo "$after"); echo; } >>"$LOG"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "green"
else
  echo "NOT GREEN - do not push"
  echo "full output kept at $LOG"
fi
exit "$fail"
