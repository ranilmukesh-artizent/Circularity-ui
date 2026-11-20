#!/bin/bash
# Run selected api tests, serialized behind the api test lock (never run two api pytests at once).
#   bash scripts/dev/api-test.sh tests/test_screens_case.py tests/test_state.py
# Stops at the first failure (-x). Does not reset the simulator; most test modules reset di themselves.
# Exits with pytest's status (0 only when every selected test passed).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
api_lock
filtered '.' 40 docker compose exec -T api timeout 1800 pytest -q -p no:cacheprovider -x "$@"
