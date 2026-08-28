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
step() {
  printf '%-46s' "$1"
  shift
  if out=$("$@" 2>&1); then
    echo "OK"
  else
    echo "FAIL"
    echo "$out" | tail -25 | sed 's/^/    /'
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
printf '%-46s' "site build is reproducible"
python scripts/build_site.py >/dev/null 2>&1
if git diff --quiet -- site/public/; then
  echo "OK"
else
  echo "FAIL"
  echo "    scripts/build_site.py changed site/public/ - the generator and the"
  echo "    site disagree. Decide which side is right before rebuilding over it:"
  git diff --stat -- site/public/ | sed 's/^/    /'
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "green"
else
  echo "NOT GREEN - do not push"
fi
exit "$fail"
