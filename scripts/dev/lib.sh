#!/bin/bash
# Shared by scripts/dev/*.sh: cd to the repo root (resolved from this file), host URLs, and the api test lock.
# The scripts run in plain bash (3.2 or later) on Linux, macOS and Git Bash on Windows. The host needs only docker
# (Compose v2) and curl: the test lock, timeouts, psql, python and node all run inside the containers.
#   bash scripts/dev/status.sh
# (On a Windows machine whose Docker runs inside WSL, call them through WSL instead:
#   wsl -d Ubuntu-24.04 -u root -- bash /mnt/c/<path-to>/Circularity-ui/scripts/dev/status.sh)
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

# The host URL of a service's published port: the port Compose actually published (so API_PORT, SIM_PORT ... from
# the environment or .env are honoured), else the variable, else the default.
#   host_url api 8000 API_PORT 8000   ->   http://localhost:8000
host_url() { # service container_port variable default
  local hp
  hp=$(docker compose port "$1" "$2" 2>/dev/null | tail -n 1)
  hp=${hp##*:}
  case $hp in '' | *[!0-9]*) hp=${!3:-$4} ;; esac
  printf 'http://localhost:%s' "$hp"
}
api_url() { host_url api 8000 API_PORT 8000; }
sim_url() { host_url source-sim 8100 SIM_PORT 8100; }

# One api pytest at a time: the suites share one database and reset it. Waits for the lock, holds it until exit.
# The lock is a flock on /tmp/di-pytest.lock INSIDE the api container, so the host needs no flock. A holder process
# runs there (flock ... cat) whose stdin is a pipe from this shell on fd 9: when this script exits, however it
# ends, the pipe closes, `cat` sees end of input, and flock releases the lock. Commands this script starts inherit
# fd 9, so the lock is also held while they run (as with a host flock).
api_lock() {
  local state f
  f=$(mktemp "${TMPDIR:-/tmp}/di-lock.XXXXXX") || return 1
  echo "waiting for the api test lock..." >&2
  # shellcheck disable=SC2016  # $f is expanded by the subshell, the single-quoted part runs in the container
  exec 9> >(
    docker compose exec -T api flock /tmp/di-pytest.lock sh -c 'echo locked; exec cat >/dev/null' >"$f" 2>&1
    rc=$?
    if grep -q '^locked' "$f" 2>/dev/null; then rm -f "$f"; else echo "ended with exit $rc" >>"$f"; fi
  )
  while :; do
    state=$(cat "$f" 2>/dev/null)
    case $state in
      locked*) return 0 ;;
      *"ended with exit"*)
        printf 'could not take the api test lock (is the api container running?):\n%s\n' "$state" >&2
        rm -f "$f"
        return 1
        ;;
    esac
    sleep 1
  done
}

# Wait until di-api (and source-sim) answer their health checks; prints how long it took.
wait_healthy() {
  local start=$SECONDS api sim
  while [ $((SECONDS - start)) -lt 90 ]; do
    api=$(api_url) sim=$(sim_url) # asked each time: a restarting container may not report its port yet
    if curl -sf -m 3 "$api/api/health" >/dev/null && curl -sf -m 3 "$sim/health" >/dev/null; then
      echo "api + source-sim healthy after $((SECONDS - start + 1))s"
      return 0
    fi
    sleep 1
  done
  echo "api or source-sim NOT healthy after 90s" >&2
  return 1
}
