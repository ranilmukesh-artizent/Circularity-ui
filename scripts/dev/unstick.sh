#!/bin/bash
# When di-api stops answering: list the sessions that are not idle, terminate sessions idle in a transaction for
# more than a minute (they hold locks others wait on), restart the api and wait for health.
# Restarting the api also kills any pytest running inside its container.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
q() { docker compose exec -T postgres psql -U circ -d di -tAc "$1"; }
q "select pid, state, now()-state_change as for, left(query,70) from pg_stat_activity where datname='di' and state <> 'idle' and pid <> pg_backend_pid() order by state_change"
echo "--- terminating idle-in-transaction sessions older than 1 minute"
q "select pg_terminate_backend(pid) from pg_stat_activity where datname='di' and state like 'idle in transaction%' and now()-state_change > interval '1 minute'"
docker compose restart api >/dev/null 2>&1
wait_healthy
