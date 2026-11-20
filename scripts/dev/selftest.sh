#!/bin/bash
# Checks that the dev scripts report failures through their exit status (the agent loop's gate relies on it).
#   bash scripts/dev/selftest.sh
# Takes ~1-2 min. Plants a temporary type error under apps/web/src and removes it again.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
dev="$REPO/scripts/dev"
fails=0
expect() { # expect <0|nonzero> <label> <command...>
  local want=$1 label=$2
  shift 2
  "$@" >/dev/null 2>&1
  local rc=$?
  if { [ "$want" = 0 ] && [ $rc -eq 0 ]; } || { [ "$want" = nonzero ] && [ $rc -ne 0 ]; }; then
    echo "ok    $label (exit $rc)"
  else
    echo "FAIL  $label: wanted $want, got exit $rc"
    fails=$((fails + 1))
  fi
}

expect 0 "api-test.sh, a passing test" bash "$dev/api-test.sh" tests/test_screens_reference.py::test_case_scope_map
expect nonzero "api-test.sh, a missing test file" bash "$dev/api-test.sh" tests/test_no_such_file.py

planted="$REPO/apps/web/src/__selftest_type_error.ts"
trap 'rm -f "$planted"' EXIT
printf 'export const broken: number = "not a number";\n' >"$planted"
expect nonzero "web-check.sh tsc, with a type error" bash "$dev/web-check.sh" tsc
rm -f "$planted"
expect 0 "web-check.sh tsc, clean" bash "$dev/web-check.sh" tsc

[ $fails -eq 0 ] && echo "selftest: all passed" || echo "selftest: $fails failed"
[ $fails -eq 0 ]
