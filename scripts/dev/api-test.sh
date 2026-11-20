#!/bin/bash
# Run selected api tests, serialized behind the api test lock (never run two api pytests at once).
#   bash scripts/dev/api-test.sh tests/test_screens_case.py tests/test_state.py
# Stops at the first failure (-x). Does not reset the simulator; most test modules reset di themselves.
# The worker is stopped for the run (its syncs write the tables the tests reset: deadlocks) and started again after.
# Exits with pytest's status (0 only when every selected test passed); 1 if the lock cannot be taken. The 30-minute
# timeout runs inside the api container (coreutils timeout), like the lock.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
api_lock || exit 1
docker compose stop worker >/dev/null 2>&1
trap 'docker compose start worker >/dev/null 2>&1' EXIT
filtered '.' 40 docker compose exec -T api timeout 1800 pytest -q -p no:cacheprovider -x "$@"
