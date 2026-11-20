#!/bin/bash
# Shared by scripts/dev/*.sh: cd to the repo root (resolved from this file), and the api test lock.
# Run the dev scripts inside WSL, e.g. from Windows:
#   wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path-to>/Circularity-ui/scripts/dev/status.sh
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
set -o pipefail  # a pipeline fails when any command in it fails, not only the last one

# Run a command, print only the output lines matching PATTERN (the last N of them), and return the command's own
# exit status, so scripts can filter noisy output and still gate on the result.
#   filtered 'passed|failed' 40 docker compose exec -T api pytest -q tests/test_x.py
filtered() {
  local pattern=$1 n=$2 out rc
  shift 2
  out=$("$@" 2>&1)
  rc=$?
  printf '%s\n' "$out" | grep -E -- "$pattern" | tail -n "$n"
  return $rc
}

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
