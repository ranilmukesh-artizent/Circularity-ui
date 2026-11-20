#!/bin/bash
# Wait until the worker has no due jobs (after a reset it syncs every source once, ~2-3 min). Use before browser
# checks that need instructions to go out promptly (the queue has no priorities yet: docs/agents/plans/02).
#   bash scripts/dev/wait-idle.sh [max_seconds=600]
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
max=${1:-600}
for ((t = 0; t <= max; t += 5)); do
  n=$(docker compose exec -T postgres psql -U circ -d di -tAc \
    "select count(*) from job where status in ('queued','running') and run_after <= now()")
  if [ "$n" = "0" ]; then echo "worker idle after ${t}s"; exit 0; fi
  sleep 5
done
echo "worker still has $n due jobs after ${max}s" >&2
exit 1
