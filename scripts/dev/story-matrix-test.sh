#!/bin/bash
# Proves story-matrix.sh against scripts/dev/fixtures/story-matrix (plan.md plus fake backend and frontend tests).
#   bash scripts/dev/story-matrix-test.sh
# Exit 0 when every case behaves as specified. Host tools only.
dev="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fx="$dev/fixtures/story-matrix"
fails=0
run() { STORY_MATRIX_PLAN="$fx/plan.md" STORY_MATRIX_ROOT="$fx" bash "$dev/story-matrix.sh" "$@" 2>&1; }
check() { # label wanted-exit wanted-substring output rc
  if [ "$5" = "$2" ] && printf '%s\n' "$4" | grep -qF -- "$3"; then
    echo "ok    $1"
  else
    echo "FAIL  $1: exit $5 (want $2), output: $4"
    fails=$((fails + 1))
  fi
}
out=$(run 1); rc=$?
check "clean phase, backend and frontend tests found" 0 "story-matrix: 3 rows, 5 tests, 0 missing" "$out" $rc
check "P9-1 does not match P9-10" 0 "3 rows" "$out" $rc
out=$(run 2); rc=$?
check "missing test named" 1 "MISSING  TF-02  P9-2.1  test_tf_02_absent" "$out" $rc
check "missing test counted" 1 "1 rows, 2 tests, 1 missing" "$out" $rc
out=$(run 3); rc=$?
check "bad story id" 1 "BADID  bad_id" "$out" $rc
out=$(run 4); rc=$?
check "story in two rows" 1 "TWICE  X-02" "$out" $rc
out=$(run 5); rc=$?
check "empty test list" 1 "NOTEST X-03" "$out" $rc
out=$(run 6); rc=$?
check "phase with no rows" 0 "story-matrix: no rows for phase 6" "$out" $rc
out=$(run 9); rc=$?
check "tables outside the matrix are ignored" 0 "no rows for phase 9" "$out" $rc
out=$(run); rc=$?
check "all phases fail on any gap" 1 "story-matrix: 9 rows" "$out" $rc
nohead="${TMPDIR:-/tmp}/sm-nohead.$$"
printf '# No matrix here\n' >"$nohead"
out=$(STORY_MATRIX_PLAN="$nohead" STORY_MATRIX_ROOT="$fx" bash "$dev/story-matrix.sh" 2>&1); rc=$?
rm -f "$nohead"
check "no matrix heading" 1 "no Story coverage matrix heading" "$out" $rc
[ $fails -eq 0 ] && echo "story-matrix-test: all passed" || echo "story-matrix-test: $fails failed"
[ $fails -eq 0 ]
