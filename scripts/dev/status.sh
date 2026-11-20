#!/bin/bash
# Is the stack healthy, is an api test running or queued, and is anything holding database locks?
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
curl -sf -m 5 "$(api_url)/api/health" >/dev/null && echo "api: healthy" || echo "api: NOT answering"
curl -sf -m 5 "$(sim_url)/health" >/dev/null && echo "source-sim: healthy" || echo "source-sim: NOT answering"
docker compose ps --format '{{.Service}} {{.Status}}'
echo "api tests running or waiting for the lock:"
# the lock and the tests live in the api container; python:slim has no ps, so read /proc there (pid, elapsed, args)
docker compose exec -T api python - <<'EOF'
import os
tck = os.sysconf("SC_CLK_TCK")
up = float(open("/proc/uptime").read().split()[0])
for pid in sorted((p for p in os.listdir("/proc") if p.isdigit()), key=int):
    if int(pid) == os.getpid():
        continue
    try:
        args = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
        start = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        continue
    if "pytest -q" in args or "flock /tmp/di-pytest.lock" in args:
        s = max(0, int(up - start / tck))
        print(f"{pid:>7} {s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d} {args}"[:140])
EOF
echo "db sessions not idle:"
docker compose exec -T postgres psql -U circ -d di -tAc \
  "select pid, state, now()-state_change, left(query,60) from pg_stat_activity where datname='di' and state<>'idle' and pid<>pg_backend_pid()"
