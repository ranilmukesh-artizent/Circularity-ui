#!/bin/bash
# The api test files that are safe side by side, in N shards at once, each on its own database. A fast pre-check
# (~7-11 min with 4 shards against ~32 min serial); the serial full suite (full-suite.sh) stays the gate.
#   bash scripts/dev/parallel-suite.sh            # 4 shards
#   N=6 bash scripts/dev/parallel-suite.sh        # 6 shards
#   bash scripts/dev/parallel-suite.sh --list     # print the shards and the serial-only files, run nothing
# Each shard is `docker compose run --rm --no-deps api` (the api's image, code mount, network and environment) with
# DI_DATABASE_URL pointing at its own database di_par1..di_parN on the stack's postgres: dropped and created fresh,
# migrated (alembic upgrade head), the sources registered as the worker does at start (ensure_sources), then pytest.
# The main database, the api test lock and the running stack are not touched, so it may run beside other work, but
# not beside full-suite.sh (both use the shared source-sim) and best not on battery.
# Left out, for the serial suite: files that reset or fault the shared source-sim (they call /_sim/), files that call
# the running api or its stream/webhooks, and files that need a fabric the running stack has synced (they fail on any
# fresh database, also on unchanged code). Shards are balanced by scripts/dev/test-times.txt.
# Logs: $OUT (default test-results/parallel/) shard-<k>.log. Exits 0 only if every shard passed. KEEP=1 keeps the DBs.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
export MSYS_NO_PATHCONV=1  # Git Bash: pass container paths through unchanged
N=${N:-4}
OUT=${OUT:-test-results/parallel}
PGUSER=${POSTGRES_USER:-circ}

SERIAL_EXTRA="tests/test_mcp_server.py tests/test_mcp_modeler.py tests/test_mcp_client_source.py tests/test_webhooks.py
tests/test_stream.py tests/test_stream_workflows.py tests/test_health.py tests/test_workflow_open_case.py
tests/test_screens_home.py tests/test_writes_access.py tests/test_screens_reference.py tests/test_reads_workspace.py"

all=$(cd backend && ls tests/test_*.py | LC_ALL=C sort) || exit 1
serial=$( { (cd backend && grep -l "_sim/\|/faults" tests/test_*.py); printf '%s\n' $SERIAL_EXTRA; } | LC_ALL=C sort -u)
safe=$(printf '%s\n' "$all" | grep -vxF -f <(printf '%s\n' "$serial"))

# greedy split: the slowest file first, each into the lightest shard (times from test-times.txt, 30 s if unknown)
shards=$(printf '%s\n' "$safe" | awk -v n="$N" '
  FILENAME == ARGV[1] { if ($1 !~ /^#/) t[$2] = $1; next }
  NF { f[++m] = $0; w[m] = ($0 in t) ? t[$0] : 30 }
  END {
    for (i = 1; i <= m; i++) for (j = i + 1; j <= m; j++) if (w[j] > w[i]) { x = w[i]; w[i] = w[j]; w[j] = x; x = f[i]; f[i] = f[j]; f[j] = x }
    for (i = 1; i <= m; i++) { b = 1; for (k = 2; k <= n; k++) if (load[k] < load[b]) b = k; load[b] += w[i]; s[b] = s[b] " " f[i] }
    for (k = 1; k <= n; k++) print s[k]
  }' scripts/dev/test-times.txt -)

if [ "${1:-}" = --list ]; then
  k=0; while IFS= read -r files; do k=$((k + 1)); echo "shard $k ($(echo $files | wc -w) files):$files"; done <<< "$shards"
  echo "serial-only ($(printf '%s\n' "$serial" | wc -l) files): $(echo $serial)"
  exit 0
fi

mkdir -p "$OUT"
url=$(docker compose exec -T api printenv DI_DATABASE_URL </dev/null) || { echo "the api container is not running" >&2; exit 1; }
url=$(printf '%s' "$url" | tr -d '\r')  # Docker Desktop on Windows may end the line with CR
k=0; pids=()
while IFS= read -r files; do
  k=$((k + 1)); db="di_par$k"
  [ -n "$files" ] || { echo "shard $k is empty: use fewer shards" >&2; exit 2; }
  docker compose exec -T postgres sh -c "dropdb -U $PGUSER --if-exists $db 2>/dev/null; createdb -U $PGUSER $db" </dev/null || exit 1
  echo "shard $k: $(echo $files | wc -w) files on $db"
  # </dev/null: docker reads stdin and would eat the rest of this loop's input
  docker compose run --rm --no-deps -T -e DI_DATABASE_URL="${url%/*}/$db" api sh -c \
    "alembic upgrade head >/dev/null && python -c 'from di.core.db import SessionLocal; from di.connectors.sync import ensure_sources; s = SessionLocal(); ensure_sources(s); s.commit()' && pytest -q -p no:cacheprovider -rfE $files" \
    </dev/null >"$OUT/shard-$k.log" 2>&1 &
  pids+=($!)
done <<< "$shards"

rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
for i in $(seq 1 "$k"); do echo "shard $i: $(grep -E '(passed|failed|error)( |,)' "$OUT/shard-$i.log" | tail -n 1)"; done
grep -h '^FAILED\|^ERROR' "$OUT"/shard-*.log
echo "not run here (serial suite): $(printf '%s\n' "$serial" | wc -l) files"
[ -n "${KEEP:-}" ] || for i in $(seq 1 "$k"); do docker compose exec -T postgres dropdb -U "$PGUSER" --if-exists "di_par$i" </dev/null; done
exit $rc
