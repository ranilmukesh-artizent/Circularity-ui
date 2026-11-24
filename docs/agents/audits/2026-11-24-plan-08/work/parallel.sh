#!/bin/bash
# The api tests that are safe to run side by side, in N shards at once, each in a one-off container on its own
# database (di_p1..di_pN on the shared postgres). Usage (Git Bash, from anywhere):
#   WT=Circularity-ui-merge N=4 TAG=merge bash parallel.sh
# Left out (they run in the usual serial suite, scripts/dev/full-suite.sh): the files that reset source-sim or set its
# faults (shared by every shard) and the ones that call the running api or need its webhooks/stream.
# Shards are balanced by each file's time in evidence/baseline-api-junit.xml. Logs: evidence/par-<TAG>-<k>.log.
set -u
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
EV="$HERE/../evidence"
WT="${WT:-Circularity-ui-merge}"; N="${N:-4}"; TAG="${TAG:-par}"
FIX="C:/repos/astra-prism-DI/ayush-ui/$WT"
MAIN="C:/repos/astra-prism-DI/ayush-ui/Circularity-ui"

SERIAL_ONLY="$(cd "$FIX/backend" && grep -l "_sim/\|/faults" tests/test_*.py)
tests/test_mcp_server.py
tests/test_mcp_modeler.py
tests/test_mcp_client_source.py
tests/test_webhooks.py
tests/test_stream.py
tests/test_health.py
tests/test_stream_workflows.py
tests/test_workflow_open_case.py
tests/test_screens_home.py
tests/test_writes_access.py
tests/test_screens_reference.py"

SHARDS="$(cd "$FIX/backend" && ls tests/test_*.py | SERIAL="$SERIAL_ONLY" N="$N" JUNIT="$(cygpath -m "$EV/baseline-api-junit.xml")" python -c '
import os, sys, collections, xml.etree.ElementTree as E
serial = set(os.environ["SERIAL"].split())
files = [f for f in sys.stdin.read().split() if f not in serial]
t = collections.Counter()
for c in E.parse(os.environ["JUNIT"]).getroot().iter("testcase"):
    t["tests/" + c.get("classname", "").split(".")[-1] + ".py"] += float(c.get("time") or 0)
n = int(os.environ["N"]); bins = [[0.0, []] for _ in range(n)]
for f in sorted(files, key=lambda f: -t.get(f, 30.0)):  # a new file: guess 30 s
    b = min(bins, key=lambda b: b[0]); b[0] += t.get(f, 30.0); b[1].append(f)
for b in bins: print(" ".join(b[1]))
' | tr -d '\r')"

[ "$(echo "$SHARDS" | wc -w)" -gt 0 ] || { echo "no shards: the split failed"; exit 2; }
echo "serial-only (not run here): $(echo "$SERIAL_ONLY" | wc -l) files"
# the sources the worker registers when it starts (di.worker.startup); the tests expect them
SEED="from di.core.db import SessionLocal; from di.connectors.sync import ensure_sources; s = SessionLocal(); ensure_sources(s); s.commit()"
k=0; pids=()
while IFS= read -r files; do
  k=$((k + 1)); db="di_p$k"
  [ -n "$files" ] || { echo "shard $k is empty"; exit 2; }
  docker compose -f "$MAIN/docker-compose.yml" exec -T postgres sh -c "dropdb -U circ --if-exists $db; createdb -U circ $db" </dev/null >/dev/null
  echo "shard $k: $(echo $files | wc -w) files on $db"
  docker run --rm --network circularity-ui_default \
    -v "$FIX/backend:/app" -v "$FIX/fixtures:/fixtures" -v "$FIX/ruff.toml:/ruff.toml" -w /app \
    -e DI_DATABASE_URL=postgresql+psycopg://circ:circ@postgres:5432/$db -e DI_SOURCE_SIM_URL=http://source-sim:8100 \
    -e DI_CLOCK=sim -e DI_ENV=dev -e DI_INSTRUCTIONS=true -e ASK_PROVIDER=groq \
    circularity-ui-api sh -c "alembic upgrade head >/dev/null && python -c '$SEED' && pytest -q -p no:cacheprovider -rfE $files"     </dev/null > "$EV/par-$TAG-$k.log" 2>&1 &
  pids+=($!)
done <<< "$SHARDS"

rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
for i in $(seq 1 "$k"); do echo "shard $i: $(tail -1 "$EV/par-$TAG-$i.log")"; done
grep -h "^FAILED\|^ERROR" "$EV"/par-"$TAG"-*.log || true
exit $rc
