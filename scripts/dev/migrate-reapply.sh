#!/bin/bash
# Re-apply the migrations after BASE (default 0010: plan 6's, 0011 onwards; 0017 for plans 2 and 8) behind the api
# test lock: downgrade to BASE, then upgrade to head.
# Plan 6's tasks run in parallel and fill migrations reserved in advance; each is idempotent, so re-applying the
# chain picks up a filled migration that was first applied empty. Rows in plan 6's own tables are rebuilt by the
# migrations (seeded rows) or by the tests; nothing else is touched.
#   bash scripts/dev/migrate-reapply.sh [BASE]
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
BASE=${1:-0010}
api_lock || exit 1
docker compose exec -T api alembic downgrade "$BASE" 2>&1 | grep -vE "^INFO  \[alembic.runtime.migration\] (Context|Will assume)" | tail -20
docker compose exec -T api alembic upgrade head 2>&1 | grep -vE "^INFO  \[alembic.runtime.migration\] (Context|Will assume)" | tail -20
docker compose exec -T api alembic current 2>&1 | tail -1
