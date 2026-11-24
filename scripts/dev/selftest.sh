#!/bin/bash
# Checks that the dev scripts report failures through their exit status (the agent loop's gate relies on it).
#   bash scripts/dev/selftest.sh
# Also checks that the api test lock serializes takers and is released when its holder dies.
# Also checks that gate-mvp.sh and gate-p9.sh (incl. its plan-file check) fail when one step fails (steps stubbed
# through GATE_LINT, GATE_API, GATE_WEB).
# Takes ~2 min. Plants a temporary type error under frontend/src and removes it again.
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

# The api test lock lives in the api container (lib.sh api_lock). A holder takes it in the background and says so in
# $mark; its sleep runs with fd 9 closed, so only the holder's own shell keeps the lock.
mark=$(mktemp "${TMPDIR:-/tmp}/di-selftest.XXXXXX")
plan_base=$(mktemp "${TMPDIR:-/tmp}/di-selftest-base.XXXXXX")
plan_new=$(mktemp "${TMPDIR:-/tmp}/di-selftest-plan.XXXXXX")
trap 'rm -f "$mark" "$plan_base" "$plan_new"' EXIT
hold_lock() { # seconds
  : >"$mark"
  # shellcheck disable=SC2016  # expanded by the inner bash
  bash -c 'source "$1"; api_lock 2>/dev/null || exit 1; echo held >"$2"; sleep "$3" 9>&-' _ "$dev/lib.sh" "$mark" "$1" &
  holder=$!
  for _ in $(seq 1 60); do [ -s "$mark" ] && return 0; sleep 1; done
  return 1
}
take_lock_within() { # min max: take the lock and release it; true if that took min..max seconds
  local t0=$SECONDS took
  # shellcheck disable=SC2016
  bash -c 'source "$1"; api_lock 2>/dev/null' _ "$dev/lib.sh" || return 1
  took=$((SECONDS - t0))
  [ "$took" -ge "$1" ] && [ "$took" -le "$2" ]
}
expect 0 "api lock, taken by a holder for 8s" hold_lock 8
expect 0 "api lock, a second taker waits for the holder (5-30s)" take_lock_within 5 30
wait "$holder"
expect 0 "api lock, taken by a holder that is then killed" hold_lock 30
kill -9 "$holder" 2>/dev/null
wait "$holder" 2>/dev/null
expect 0 "api lock, released when its holder is killed (0-15s)" take_lock_within 0 15

expect 0 "api-test.sh, a passing test" bash "$dev/api-test.sh" tests/test_screens_reference.py::test_case_scope_map
expect nonzero "api-test.sh, a missing test file" bash "$dev/api-test.sh" tests/test_no_such_file.py

planted="$REPO/frontend/src/__selftest_type_error.ts"
trap 'rm -f "$planted" "$mark" "$plan_base" "$plan_new"' EXIT
printf 'export const broken: number = "not a number";\n' >"$planted"
expect nonzero "web-check.sh tsc, with a type error" bash "$dev/web-check.sh" tsc
rm -f "$planted"
expect 0 "web-check.sh tsc, clean" bash "$dev/web-check.sh" tsc

# gate-mvp.sh (plan 08) with its steps stubbed through GATE_LINT, GATE_API and GATE_WEB.
expect nonzero "gate-mvp.sh, failing api step" \
  env GATE_LINT=true GATE_WEB=true GATE_API=false bash "$dev/gate-mvp.sh" tests/test_health.py
expect 0 "gate-mvp.sh, every step passing" \
  env GATE_LINT=true GATE_WEB=true GATE_API=true bash "$dev/gate-mvp.sh" tests/test_health.py
expect 0 "gate-mvp.sh, the real api-test.sh on a passing test" \
  env GATE_LINT=true GATE_WEB=true bash "$dev/gate-mvp.sh" tests/test_health.py

# gate-p9.sh (plan 9): the same three stubs, and the plan-file check with GATE_PLAN_BASE and GATE_PLAN.
expect nonzero "gate-p9.sh, failing api step"   env GATE_LINT=true GATE_WEB=true GATE_API=false bash "$dev/gate-p9.sh" tests/test_health.py
expect 0 "gate-p9.sh, every step passing"   env GATE_LINT=true GATE_WEB=true GATE_API=true bash "$dev/gate-p9.sh" tests/test_health.py
printf -- '- [ ] P9-0.1 x
text
' >"$plan_base"
printf -- '- [x] P9-0.1 x
text
' >"$plan_new"
expect 0 "gate-p9.sh, plan file with only a ticked box"   env GATE_LINT=true GATE_WEB=true GATE_API=true GATE_PLAN_BASE="$plan_base" GATE_PLAN="$plan_new" bash "$dev/gate-p9.sh"
printf -- '- [x] P9-0.1 x
text changed
' >"$plan_new"
expect nonzero "gate-p9.sh, plan file changed beyond a ticked box"   env GATE_LINT=true GATE_WEB=true GATE_API=true GATE_PLAN_BASE="$plan_base" GATE_PLAN="$plan_new" bash "$dev/gate-p9.sh"
expect 0 "gate-p9.sh, the real api-test.sh on a passing test"   env GATE_LINT=true GATE_WEB=true bash "$dev/gate-p9.sh" tests/test_health.py

# story-matrix.sh (plan 9, R22): its own test against fixtures.
expect 0 "story-matrix-test.sh, every case of the matrix check" bash "$dev/story-matrix-test.sh"

[ $fails -eq 0 ] && echo "selftest: all passed" || echo "selftest: $fails failed"
[ $fails -eq 0 ]
