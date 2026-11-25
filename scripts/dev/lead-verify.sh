#!/bin/bash
# Plan 9 lead's verify after cherry-picking a writer's task (see the plan's "How to run this plan unattended").
#   bash scripts/dev/lead-verify.sh [--suite] [--smoke] [api test files...]
# Always: migrate-reapply 0028 (reserved migrations a task filled), restart (the worker never reloads), the given test
# files through api-test.sh (the task's own and its serial-only ones), lint, web-check. --suite also runs the api
# parallel-suite (N=3 by default; every few merges and at gates). --smoke also runs smoke-pages for the 11 accounts
# after reset and wait-idle, then resets. Prints one summary line per step; exits 0 only if every step passed.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
export MSYS_NO_PATHCONV=1
suite=0; smoke=0
while [ "${1:-}" = --suite ] || [ "${1:-}" = --smoke ]; do
  [ "$1" = --suite ] && suite=1; [ "$1" = --smoke ] && smoke=1; shift
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
if [ $# -gt 0 ]; then
  out=$(bash scripts/dev/api-test.sh "$@" 2>&1); rc=$?
  printf '%s\n' "$out" | grep -E "(passed|failed|error)( |,)" | tail -n 1
  printf '%s\n' "$out" | grep -E "^FAILED|^ERROR" | head -10
  [ $rc -eq 0 ] && ok "api-test $*" || bad "api-test"
fi
bash scripts/dev/lint.sh >/tmp/lead-lint.log 2>&1 && ok "lint" || { bad "lint"; grep -A8 FAIL /tmp/lead-lint.log | head -20; }
out=$(bash scripts/dev/web-check.sh 2>&1); rc=$?
printf '%s\n' "$out" | sed 's/\x1b\[[0-9;]*m//g' | grep -E "tsc errors|Tests .*(passed|failed)"
[ $rc -eq 0 ] && ok "web-check" || bad "web-check"
if [ "$smoke" = 1 ]; then
  bash scripts/dev/reset.sh >/dev/null 2>&1; bash scripts/dev/wait-idle.sh | tail -n 1
  out=$(node frontend/scripts/smoke-pages.mjs "http://localhost:${WEB_PORT:-5173}" 2>&1); rc=$?
  printf '%s\n' "$out" | grep -E "routes, [0-9]+ failing" | tr '\n' ' '; echo
  [ $rc -eq 0 ] && ok "smoke-pages" || bad "smoke-pages"
  bash scripts/dev/reset.sh >/dev/null 2>&1
fi
[ $fails -eq 0 ] && echo "lead-verify: all passed" || echo "lead-verify: $fails failed"
[ $fails -eq 0 ]
