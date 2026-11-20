#!/bin/bash
# Back to the demo's starting state: reset source-sim, reset di (cases, workspace state, journal, instructions;
# connector data is kept), restart the worker. Run after the full suite or after clicking writes in the browser.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
docker compose stop worker >/dev/null 2>&1
curl -s -X POST localhost:8100/_sim/reset >/dev/null
# reset_starting.py imports tests.starting, so /app must be on the path
docker compose exec -T -e PYTHONPATH=/app api python scripts/reset_starting.py 2>&1 | tail -3
docker compose start worker >/dev/null 2>&1
docker compose ps --format '{{.Service}} {{.Status}}'
