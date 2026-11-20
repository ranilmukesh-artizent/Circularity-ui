#!/bin/bash
# Shared by scripts/dev/*.sh: cd to the repo root (resolved from this file), and the api test lock.
# Run the dev scripts inside WSL, e.g. from Windows:
#   wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path-to>/Circularity-ui/scripts/dev/status.sh
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1

# One api pytest at a time: the suites share one database and reset it. Waits for the lock, holds it until exit.
api_lock() {
  exec 9>/tmp/di-pytest.lock
  echo "waiting for the api test lock..." >&2
  flock 9
}

# Wait until di-api (and source-sim) answer their health checks; prints how long it took.
wait_healthy() {
  for i in $(seq 1 90); do
    if curl -sf -m 3 localhost:8000/api/health >/dev/null && curl -sf -m 3 localhost:8100/health >/dev/null; then
      echo "api + source-sim healthy after ${i}s"
      return 0
    fi
    sleep 1
  done
  echo "api or source-sim NOT healthy after 90s" >&2
  return 1
}
