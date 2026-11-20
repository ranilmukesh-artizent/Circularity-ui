#!/bin/bash
# Typecheck and unit-test the web app inside the web container. Exits non-zero on any type error or failing test.
#   bash scripts/dev/web-check.sh          # tsc + vitest
#   bash scripts/dev/web-check.sh tsc      # typecheck only
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
out=$(docker compose exec -T web npx tsc --noEmit -p . 2>&1)
tsc_rc=$?
echo "$out" | grep -E "error TS" | head -60
echo "tsc errors: $(echo "$out" | grep -c 'error TS')"
[ "$1" = "tsc" ] && exit $tsc_rc
filtered '.' 8 docker compose exec -T web npx vitest run
test_rc=$?
[ "$tsc_rc" -eq 0 ] && [ "$test_rc" -eq 0 ]
