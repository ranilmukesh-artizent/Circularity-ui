#!/bin/bash
# Restart api, worker and source-sim so they run the current code, and wait until they are healthy.
# Needed after: changes under /mnt/c that --reload misses (source-sim, sometimes api), any worker change (the worker
# never reloads), and any change to fixtures/golden (read once at start-up).
#   bash scripts/dev/restart.sh            # api worker source-sim
#   bash scripts/dev/restart.sh api        # only these services
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
services=("$@")
[ ${#services[@]} -eq 0 ] && services=(api worker source-sim)
docker compose restart "${services[@]}" >/dev/null 2>&1
wait_healthy
docker compose ps --format '{{.Service}} {{.Status}}'
