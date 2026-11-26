#!/bin/bash
# A writer's checks from its own git worktree, on its own database: plan 9's unattended run (see the plan's
# "How to run this plan unattended"). The main stack's containers, database, test lock and tree are not touched.
#   bash scripts/dev/wt-check.sh <k> tests/test_a.py tests/test_b.py   # pytest on di_w<k>, then lint, then web
#   WT_AUTO=1 bash scripts/dev/wt-check.sh <k> [tests...]              # pytest on the tests impacted-tests.sh finds
#   WT_LINT=0 bash scripts/dev/wt-check.sh <k> tests/test_a.py          # pytest only (red-first runs)
#   WT_WEB=1 ...                                                         # force the web checks (0 skips them)
#   bash scripts/dev/wt-check.sh --prepare-db <name> <owner>            # create <name> from the template (lead-verify)
# Run it from the worktree root. Each run uses the main stack's images, network and postgres (project
# circularity-ui) with this worktree's code mounted: `docker compose -p circularity-ui run --rm --no-deps`.
# Impact-only: ruff check and ruff format --check run on the changed .py files only (changed = git diff against
# WT_BASE, default feature/plan-09-recover, plus untracked files); mypy (whole package, but its cache is kept in the
# named volume di_mypy_w<k>) and lint-imports run when any backend file changed, all in ONE container. Web (when
# frontend/ changed or WT_WEB=1): ONE container running tsc -b, `vitest related --run <changed src files>` and eslint
# on the changed files.
# pytest: database di_w<k> is created from a template database di_tpl_<owner>_<hash> (alembic head + ensure_sources,
# built once per hash of backend/migrations/versions and backend/di/connectors, stale ones dropped), so every run still
# starts from a clean, migrated, seeded database without migrating each time. WT_AUTO=1 takes the file list from
# impacted-tests.sh and refuses ALL (core, migrations or conftest changed): name the files then.
# Files that reset or fault the shared source-sim or call the running api are refused here: the lead runs them after
# the merge, through api-test.sh. Every step runs; exits 0 only if all pass. WT_VERBOSE=1 prints each step's output.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P="docker compose -p ${MAIN_PROJECT:-circularity-ui}"
PGUSER=${POSTGRES_USER:-circ}

# prepare_db <name> <owner>: drop <name>, create it from the template of <owner> (built when missing or stale).
prepare_db() {
  local name=$1 owner=$2 h tpl url
  h=$( { cat backend/migrations/versions/*.py; find backend/di/connectors -name '*.py' | LC_ALL=C sort | xargs cat; } | cksum | cut -d' ' -f1)
  tpl="di_tpl_${owner}_${h}"
  url=$(docker compose -p "${MAIN_PROJECT:-circularity-ui}" exec -T api printenv DI_DATABASE_URL </dev/null | tr -d '\r')
  [ -n "$url" ] || { echo "the main api container is not running" >&2; return 1; }
  PREP_URL="${url%/*}"
  # drop this owner's stale templates
  for old in $($P exec -T postgres psql -U "$PGUSER" -d postgres -Atc "select datname from pg_database where datname like 'di\_tpl\_${owner}\_%' and datname <> '$tpl'" </dev/null | tr -d '\r'); do
    $P exec -T postgres dropdb -U "$PGUSER" --if-exists "$old" </dev/null
  done
  if ! $P exec -T postgres psql -U "$PGUSER" -d postgres -Atc "select 1 from pg_database where datname='$tpl'" </dev/null | grep -q 1; then
    $P exec -T postgres createdb -U "$PGUSER" "$tpl" </dev/null || return 1
    if ! $P run --rm --no-deps -T -e DI_DATABASE_URL="$PREP_URL/$tpl" api sh -c \
      "alembic upgrade head >/dev/null 2>&1 && python -c 'from di.core.db import SessionLocal; from di.connectors.sync import ensure_sources; s = SessionLocal(); ensure_sources(s); s.commit()'" </dev/null; then
      $P exec -T postgres dropdb -U "$PGUSER" --if-exists "$tpl" </dev/null  # never leave a half-built template
      return 1
    fi
  fi
  $P exec -T postgres sh -c "dropdb -U $PGUSER --if-exists $name 2>/dev/null; createdb -U $PGUSER -T $tpl $name" </dev/null
}

if [ "${1:-}" = --prepare-db ]; then
  [ -f docker-compose.yml ] || { echo "run from the worktree root" >&2; exit 2; }
  prepare_db "${2:?usage: --prepare-db <name> <owner>}" "${3:?usage: --prepare-db <name> <owner>}"
  exit $?
fi

k=${1:?usage: wt-check.sh <writer number> [test files...]}
shift
case $k in *[!0-9]*) echo "writer number must be digits" >&2; exit 2 ;; esac
[ -f docker-compose.yml ] || { echo "run from the worktree root" >&2; exit 2; }
db="di_w$k"
report=""
fails=0
verbose() { [ -n "${WT_VERBOSE:-}" ] && printf '%s\n' "$1" | tail -n 60; return 0; }
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
  verbose "$out"
  return 0
}
# steps_from <output with "@@ <label> <rc>" markers>: one ok/FAIL entry per marker, the lines before it as detail
steps_from() {
  local out=$1 line buf="" label rc
  while IFS= read -r line; do
    line=${line%$'\r'}
    case $line in
      "@@ "*)
        rc=${line##* }; label=${line#@@ }; label=${label% *}
        if [ "$rc" = 0 ]; then report="${report}ok    $label"$'\n'
        elif [ "$rc" = skip ]; then report="${report}skip  $label"$'\n'
        else fails=$((fails + 1)); report="${report}FAIL  $label (exit $rc)"$'\n'"$(printf '%s' "$buf" | grep -v '^[[:space:]]*$' | tail -n 25)"$'\n'; fi
        buf="" ;;
      *) buf="${buf}${line}"$'\n' ;;
    esac
  done <<< "$out"
  verbose "$out"
}

base=${WT_BASE:-feature/plan-09-recover}
changed=$( { git diff --name-only --diff-filter=d "$base" 2>/dev/null; git ls-files --others --exclude-standard; } | LC_ALL=C sort -u)

files=("$@")
if [ "${WT_AUTO:-}" = 1 ]; then
  auto=$(bash "$HERE/impacted-tests.sh" "$base") || exit 1
  if [ "$auto" = ALL ]; then
    echo "WT_AUTO refused: a change in the shared core (core/, migrations, conftest, forbidden.py) impacts every test. Name the test files yourself." >&2
    exit 4
  fi
  for f in $auto; do files+=("$f"); done
  echo "WT_AUTO: ${#files[@]} impacted test file(s): ${files[*]}"
fi
if [ ${#files[@]} -gt 0 ]; then
  serial=""
  for f in "${files[@]}"; do
    if grep -q "_sim/\|/faults" "backend/$f" 2>/dev/null; then serial="$serial $f"; fi
  done
  if [ -n "$serial" ]; then
    echo "refused (the lead runs these after the merge, through api-test.sh):$serial" >&2
    exit 3
  fi
  prepare_db "$db" "w$k" || exit 1
  step "pytest on $db: ${files[*]}" $P run --rm --no-deps -T -e DI_DATABASE_URL="$PREP_URL/$db" -e PYTHONDONTWRITEBYTECODE= -e PYTHONPYCACHEPREFIX=/pyc -v "di_pyc_w$k:/pyc" api sh -c \
    "pytest -q -p no:cacheprovider -rfE ${files[*]}"
elif [ "${WT_AUTO:-}" = 1 ]; then
  report="${report}skip  pytest (no impacted test files)"$'\n'
fi

py=$(printf '%s\n' "$changed" | grep -E '^backend/.*\.py$' | sed 's#^backend/##')
if [ "${WT_LINT:-1}" = 1 ]; then
  if [ -z "$(printf '%s\n' "$changed" | grep '^backend/')" ]; then
    report="${report}skip  lint (no backend change vs $base)"$'\n'
  else
    # one container; each check prints "@@ <label> <rc>" after its output. $@ = the changed .py files
    script='if [ $# -gt 0 ]; then
  ruff check "$@" 2>&1; echo "@@ ruff check $?"
  ruff format --check "$@" 2>&1; echo "@@ ruff format --check $?"
else
  echo "@@ ruff check skip"; echo "@@ ruff format --check skip"
fi
mypy 2>&1; echo "@@ mypy $?"
lint-imports 2>&1; echo "@@ lint-imports $?"'
    out=$($P run --rm --no-deps -T -v "di_mypy_w$k:/app/.mypy_cache" -v "di_ruff_w$k:/app/.ruff_cache" -e RUFF_CACHE_DIR=/app/.ruff_cache \
      api sh -c "$script" sh $py </dev/null 2>&1)
    steps_from "$out"
  fi
fi

if [ "${WT_WEB:-}" = 1 ] || { [ "${WT_WEB:-}" != 0 ] && printf '%s\n' "$changed" | grep -q '^frontend/'; }; then
  src=$(printf '%s\n' "$changed" | grep -E '^frontend/src/.*\.(ts|tsx)$' | sed 's#^frontend/##')
  lintable=$(printf '%s\n' "$changed" | grep -E '^frontend/.*\.(ts|tsx|js|jsx|mjs)$' | grep -v '/node_modules/' | sed 's#^frontend/##')
  script='npx tsc -b 2>&1; echo "@@ tsc -b $?"
if [ -n "$SRC" ]; then npx vitest related --run $SRC 2>&1; echo "@@ vitest related $?"; else echo "@@ vitest related skip"; fi
if [ -n "$LINT" ]; then npx eslint $LINT 2>&1; echo "@@ eslint $?"; else echo "@@ eslint skip"; fi'
  out=$($P run --rm --no-deps -T -e SRC="$(echo $src)" -e LINT="$(echo $lintable)" web sh -c "$script" </dev/null 2>&1)
  steps_from "$out"
fi
printf '%s' "$report"
[ $fails -eq 0 ] && echo "wt-check: all passed" || echo "wt-check: $fails failed"
[ $fails -eq 0 ]
