#!/bin/bash
# Typecheck and unit-test the web app inside the web container.
#   bash scripts/dev/web-check.sh          # tsc + vitest
#   bash scripts/dev/web-check.sh tsc      # typecheck only
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
out=$(docker compose exec -T web npx tsc --noEmit -p . 2>&1)
echo "$out" | grep -E "error TS" | head -60
echo "tsc errors: $(echo "$out" | grep -c 'error TS')"
[ "$1" = "tsc" ] && exit 0
docker compose exec -T web npx vitest run 2>&1 | tail -6
