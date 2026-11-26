#!/bin/bash
# Plan 9 lead's verify after cherry-picking a writer's task (see the plan's "How to run this plan unattended").
#   bash scripts/dev/lead-verify.sh [--suite] [--smoke] [--impacted[=<base>]] [api test files...]
# --impacted (base default feature/plan-09-recover): only what the change touches. impacted-tests.sh lists the test
# files; those parallel-suite.sh keeps serial go through api-test.sh (with the given files), the rest run in N shards
# (default 3) on private databases di_imp<k> made from the template database (wt-check.sh --prepare-db); lint and web
# run once on the changed files (wt-check.sh 0, mypy cache kept). ALL (core, migrations, conftest changed) falls back
# to the parallel-suite. Without --impacted, lint.sh and web-check.sh run in full as before.
# Always: migrate-reapply 0028 (reserved migrations a task filled), restart (the worker never reloads), the given test
# files through api-test.sh (the task's own and its serial-only ones), lint, web-check. --suite also runs the api
# parallel-suite (N=3 by default; every few merges and at gates). --smoke also runs smoke-pages for the 11 accounts
# after reset and wait-idle, then resets. Prints one summary line per step; exits 0 only if every step passed.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
export MSYS_NO_PATHCONV=1
suite=0; smoke=0; impacted=0; ibase=feature/plan-09-recover
while [ "${1:-}" = --suite ] || [ "${1:-}" = --smoke ] || [[ "${1:-}" == --impacted* ]]; do
  [ "$1" = --suite ] && suite=1
  [ "$1" = --smoke ] && smoke=1
  case $1 in --impacted) impacted=1 ;; --impacted=*) impacted=1; ibase=${1#--impacted=} ;; esac
  shift
done
fails=0
ok() { echo "ok    $1"; }
bad() { echo "FAIL  $1"; fails=$((fails + 1)); }
bash scripts/dev/migrate-reapply.sh 0028 >/dev/null 2>&1 && ok "migrate-reapply 0028" || bad "migrate-reapply 0028"
bash scripts/dev/restart.sh >/dev/null 2>&1 && ok "restart" || bad "restart"
if [ "$suite" = 1 ]; then
  out=$(N=${N:-3} bash scripts/dev/parallel-suite.sh 2>&1); rc=$?
  printf '%s\n' "$out" | grep -E "^shard [0-9]+: .*(passed|failed)|^FAILED"
  [ $rc -eq 0 ] && ok "parallel-suite" || bad "parallel-suite"
fi
if [ "$impacted" = 1 ]; then
  imp=$(bash scripts/dev/impacted-tests.sh "$ibase")
  if [ "$imp" = ALL ]; then
    echo "impacted: ALL (shared core changed), running the parallel-suite"
    out=$(N=${N:-3} bash scripts/dev/parallel-suite.sh 2>&1); rc=$?
    printf '%s\n' "$out" | grep -E "^shard [0-9]+: .*(passed|failed)|^FAILED"
    [ $rc -eq 0 ] && ok "parallel-suite" || bad "parallel-suite"
  elif [ -z "$imp" ]; then
    echo "impacted: no test files"
  else
    serial_all=$(bash scripts/dev/parallel-suite.sh --list | sed -n 's/^serial-only ([0-9]* files): //p')
    ser=""; par=""
    for f in $imp; do case " $serial_all " in *" $f "*) ser="$ser $f" ;; *) par="$par $f" ;; esac; done
    echo "impacted: $(echo $imp | wc -w) files; serial-only:${ser:- none}"
    if [ -n "$par" ]; then
      n=${N:-3}; cnt=$(echo $par | wc -w); [ "$n" -gt "$cnt" ] && n=$cnt
      url=$(docker compose exec -T api printenv DI_DATABASE_URL </dev/null | tr -d '\r'); mkdir -p test-results/impacted
      shards=$(printf '%s\n' $par | awk -v n="$n" 'FILENAME == ARGV[1] { if ($1 !~ /^#/) t[$2] = $1; next }
        NF { f[++m] = $0; w[m] = ($0 in t) ? t[$0] : 30 }
        END { for (i = 1; i <= m; i++) for (j = i + 1; j <= m; j++) if (w[j] > w[i]) { x = w[i]; w[i] = w[j]; w[j] = x; x = f[i]; f[i] = f[j]; f[j] = x }
          for (i = 1; i <= m; i++) { b = 1; for (k = 2; k <= n; k++) if (load[k] < load[b]) b = k; load[b] += w[i]; s[b] = s[b] " " f[i] }
          for (k = 1; k <= n; k++) print s[k] }' scripts/dev/test-times.txt -)
      k=0; pids=()
      while IFS= read -r files; do
        k=$((k + 1)); [ -n "$files" ] || continue
        bash scripts/dev/wt-check.sh --prepare-db "di_imp$k" lead </dev/null || { bad "prepare di_imp$k"; continue; }
        docker compose run --rm --no-deps -T -e DI_DATABASE_URL="${url%/*}/di_imp$k" -e PYTHONDONTWRITEBYTECODE= -e PYTHONPYCACHEPREFIX=/pyc -v di_pyc_lead:/pyc api sh -c "pytest -q -p no:cacheprovider -rfE $files" \
          </dev/null >"test-results/impacted/shard-$k.log" 2>&1 &
        pids+=($!)
      done <<< "$shards"
      prc=0; for p in "${pids[@]}"; do wait "$p" || prc=1; done
      for i in $(seq 1 "$k"); do echo "shard $i: $(grep -E '(passed|failed|error)( |,)' "test-results/impacted/shard-$i.log" | tail -n 1)"; done
      grep -h '^FAILED\|^ERROR' test-results/impacted/shard-*.log
      for i in $(seq 1 "$k"); do docker compose exec -T postgres dropdb -U "${POSTGRES_USER:-circ}" --if-exists "di_imp$i" </dev/null; done
      [ $prc -eq 0 ] && ok "impacted tests (sharded)" || bad "impacted tests (sharded)"
    fi
    # shellcheck disable=SC2086
    [ -n "$ser" ] && set -- "$@" $ser
  fi
fi
if [ $# -gt 0 ]; then
  out=$(bash scripts/dev/api-test.sh "$@" 2>&1); rc=$?
  printf '%s\n' "$out" | grep -E "(passed|failed|error)( |,)" | tail -n 1
  printf '%s\n' "$out" | grep -E "^FAILED|^ERROR|^E   |^tests/.*:[0-9]+: " | head -20  # the failing test, its error, its line
  printf '%s\n' "$out" > "${LEAD_LOG:-test-results/lead-verify-api.log}" 2>/dev/null || true
  [ $rc -eq 0 ] && ok "api-test $*" || bad "api-test"
fi
if [ "$impacted" = 1 ]; then
  out=$(WT_BASE=$ibase bash scripts/dev/wt-check.sh 0 2>&1); rc=$?
  printf '%s\n' "$out" | grep -vE "^wt-check"
  [ $rc -eq 0 ] && ok "lint + web (impact-only)" || bad "lint + web (impact-only)"
else
  bash scripts/dev/lint.sh >/tmp/lead-lint.log 2>&1 && ok "lint" || { bad "lint"; grep -A8 FAIL /tmp/lead-lint.log | head -20; }
  out=$(bash scripts/dev/web-check.sh 2>&1); rc=$?
  printf '%s\n' "$out" | sed 's/\x1b\[[0-9;]*m//g' | grep -E "tsc errors|Tests .*(passed|failed)"
  [ $rc -eq 0 ] && ok "web-check" || bad "web-check"
fi
if [ "$smoke" = 1 ]; then
  bash scripts/dev/reset.sh >/dev/null 2>&1; bash scripts/dev/wait-idle.sh | tail -n 1
  out=$(node frontend/scripts/smoke-pages.mjs "http://localhost:${WEB_PORT:-5173}" 2>&1); rc=$?
  printf '%s\n' "$out" | grep -E "routes, [0-9]+ failing" | tr '\n' ' '; echo
  [ $rc -eq 0 ] && ok "smoke-pages" || bad "smoke-pages"
  bash scripts/dev/reset.sh >/dev/null 2>&1
fi
[ $fails -eq 0 ] && echo "lead-verify: all passed" || echo "lead-verify: $fails failed"
[ $fails -eq 0 ]
