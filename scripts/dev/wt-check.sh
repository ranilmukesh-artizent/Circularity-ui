#!/bin/bash
# A writer's checks from its own git worktree, on its own database: plan 9's unattended run (see the plan's
# "How to run this plan unattended"). The main stack's containers, database, test lock and tree are not touched.
#   bash scripts/dev/wt-check.sh <k> tests/test_a.py tests/test_b.py   # pytest on di_w<k>, then lint, then web
#   WT_LINT=0 bash scripts/dev/wt-check.sh <k> tests/test_a.py          # pytest only (red-first runs)
#   WT_WEB=1 ...                                                         # force the web checks
# Run it from the worktree root. Each run uses the main stack's images, network and postgres (project
# circularity-ui) with this worktree's code mounted: `docker compose -p circularity-ui run --rm --no-deps`.
# pytest: database di_w<k> dropped and created fresh, migrated, sources registered (as parallel-suite.sh does).
# Files that reset or fault the shared source-sim or call the running api are refused here: the lead runs them after
# the merge, through api-test.sh. Lint: ruff check, ruff format --check, mypy, lint-imports. Web (when frontend/
# differs from the main branch or WT_WEB=1): tsc -b, vitest run, eslint. Every step runs; exits 0 only if all pass.
export MSYS_NO_PATHCONV=1
k=${1:?usage: wt-check.sh <writer number> [test files...]}
shift
case $k in *[!0-9]*) echo "writer number must be digits" >&2; exit 2 ;; esac
[ -f docker-compose.yml ] || { echo "run from the worktree root" >&2; exit 2; }
P="docker compose -p ${MAIN_PROJECT:-circularity-ui}"
PGUSER=${POSTGRES_USER:-circ}
db="di_w$k"
report=""
fails=0
step() { # step <label> <command...>
  local label=$1 out rc
  shift
  out=$("$@" 2>&1 </dev/null)
  rc=$?
  if [ $rc -eq 0 ]; then
    report="${report}ok    $label"$'\n'
  else
    fails=$((fails + 1))
    report="${report}FAIL  $label (exit $rc)"$'\n'"$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | tail -n 25)"$'\n'
  fi
  [ -n "${WT_VERBOSE:-}" ] && printf '%s\n' "$out" | tail -n 60
  return 0
}
if [ $# -gt 0 ]; then
  serial=""
  for f in "$@"; do
    if grep -q "_sim/\|/faults" "backend/$f" 2>/dev/null; then serial="$serial $f"; fi
  done
  if [ -n "$serial" ]; then
    echo "refused (the lead runs these after the merge, through api-test.sh):$serial" >&2
    exit 3
  fi
  url=$(docker compose -p "${MAIN_PROJECT:-circularity-ui}" exec -T api printenv DI_DATABASE_URL </dev/null | tr -d '\r')
  [ -n "$url" ] || { echo "the main api container is not running" >&2; exit 1; }
  $P exec -T postgres sh -c "dropdb -U $PGUSER --if-exists $db 2>/dev/null; createdb -U $PGUSER $db" </dev/null || exit 1
  step "pytest on $db: $*" $P run --rm --no-deps -T -e DI_DATABASE_URL="${url%/*}/$db" api sh -c \
    "alembic upgrade head >/dev/null 2>&1 && python -c 'from di.core.db import SessionLocal; from di.connectors.sync import ensure_sources; s = SessionLocal(); ensure_sources(s); s.commit()' && pytest -q -p no:cacheprovider -rfE $*"
fi
if [ "${WT_LINT:-1}" = 1 ]; then
  step "ruff check" $P run --rm --no-deps -T api ruff check .
  step "ruff format --check" $P run --rm --no-deps -T api ruff format --check .
  step "mypy" $P run --rm --no-deps -T api mypy
  step "lint-imports" $P run --rm --no-deps -T api lint-imports
fi
base=${WT_BASE:-feature/plan-09-recover}
if [ "${WT_WEB:-}" = 1 ] || { [ "${WT_WEB:-}" != 0 ] && { git diff --name-only "$base" -- frontend | grep -q . || git ls-files --others --exclude-standard frontend | grep -q .; }; }; then
  step "tsc -b" $P run --rm --no-deps -T web npx tsc -b
  step "vitest run" $P run --rm --no-deps -T web npx vitest run
  step "eslint" $P run --rm --no-deps -T web npx eslint .
fi
printf '%s' "$report"
[ $fails -eq 0 ] && echo "wt-check: all passed" || echo "wt-check: $fails failed"
[ $fails -eq 0 ]
