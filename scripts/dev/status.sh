#!/bin/bash
# Is the stack healthy, is an api test running or queued, and is anything holding database locks?
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
curl -sf -m 5 localhost:8000/api/health >/dev/null && echo "api: healthy" || echo "api: NOT answering"
curl -sf -m 5 localhost:8100/health >/dev/null && echo "source-sim: healthy" || echo "source-sim: NOT answering"
docker compose ps --format '{{.Service}} {{.Status}}'
echo "api tests running or waiting for the lock:"
ps -eo pid,etime,args | grep -v grep | grep -E "pytest -q|flock 9" | cut -c1-140
echo "db sessions not idle:"
docker compose exec -T postgres psql -U circ -d di -tAc \
  "select pid, state, now()-state_change, left(query,60) from pg_stat_activity where datname='di' and state<>'idle' and pid<>pg_backend_pid()"
