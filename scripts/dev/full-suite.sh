#!/bin/bash
# The full api suite (about 16-25 min, ~3,450 tests) from a reset simulator with the worker stopped, then the source-sim
# suite (about 1 min). Holds the api test lock. Prints only failures and the summary lines.
# Exits non-zero if either suite failed. Afterwards run scripts/dev/reset.sh to put the demo back to its starting
# state (it also restarts the worker).
#   bash scripts/dev/full-suite.sh            # everything
#   bash scripts/dev/full-suite.sh -k nav     # extra pytest arguments go to the api run
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
api_lock
docker compose stop worker >/dev/null 2>&1
curl -s -X POST localhost:8100/_sim/reset >/dev/null
echo "== api"
filtered '^(FAILED|ERROR)|passed|failed|error' 40 docker compose exec -T api pytest -q -p no:cacheprovider -rfE "$@"
api_rc=$?
echo "== source-sim"
filtered '^(FAILED|ERROR)|passed|failed' 15 docker compose exec -T source-sim pytest -q -p no:cacheprovider
sim_rc=$?
echo "== exit: api $api_rc, source-sim $sim_rc"
[ "$api_rc" -eq 0 ] && [ "$sim_rc" -eq 0 ]
