#!/bin/bash
# Story matrix check (plan 9, R22 traceability): every story in the plan's "Story coverage matrix" names tests
# that exist.
#   bash scripts/dev/story-matrix.sh [phase]
# With a phase, only rows whose Task column starts with P9-<phase>. are checked; without one, every row.
# Env: STORY_MATRIX_PLAN (plan path), STORY_MATRIX_ROOT (repo root searched for tests).
# A test name is found as `def <name>` under backend/tests, or as the plain text in frontend/src *.test.ts(x).
# Output lines: BADID, TWICE, NOTEST, MISSING, then "story-matrix: R rows, T tests, M missing".
# Exit 1 on any of them or when the matrix heading is missing; 0 otherwise. Host tools only: bash, grep, awk.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLAN="${STORY_MATRIX_PLAN:-$REPO/docs/agents/plans/09-agentic-platform.md}"
ROOT="${STORY_MATRIX_ROOT:-$REPO}"
phase="$1"

if [ ! -f "$PLAN" ] || ! grep -qE '^#+ .*Story coverage matrix' "$PLAN"; then
  echo "story-matrix: no Story coverage matrix heading in $PLAN"
  exit 1
fi

# The first table after the heading: one "story<TAB>task<TAB>tests" line per data row.
rows=$(awk -F'|' '
  /^#+ .*Story coverage matrix/ && !seen { seen = 1; next }
  seen && !done && /^[ \t]*\|/ {
    intable = 1
    n++
    if (n <= 2) next   # header and separator
    for (i = 2; i <= 5; i++) { gsub(/^[ \t]+|[ \t\r]+$/, "", $i) }
    print $2 "\t" $4 "\t" $5
    next
  }
  seen && intable { done = 1 }
' "$PLAN")

rcount=0 tcount=0 missing=0 bad=0
seen_ids=" "
while IFS=$'\t' read -r story task tests; do
  [ -z "$story" ] && [ -z "$task" ] && continue
  if [ -n "$phase" ]; then
    case "$task" in "P9-$phase."*) ;; *) continue ;; esac
  fi
  rcount=$((rcount + 1))
  if ! printf '%s' "$story" | grep -qE '^[A-Z]{1,3}(-[A-Z0-9]{2,4})?-[0-9]{2}$'; then
    echo "BADID  $story"
    bad=$((bad + 1))
  fi
  case "$seen_ids" in
    *" $story "*) echo "TWICE  $story"; bad=$((bad + 1)) ;;
  esac
  seen_ids="$seen_ids$story "
  names=$(printf '%s' "$tests" | tr ',;' '\n\n' | tr -d '`' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$')
  if [ -z "$names" ]; then
    echo "NOTEST $story"
    bad=$((bad + 1))
    continue
  fi
  while IFS= read -r name; do
    tcount=$((tcount + 1))
    if grep -rqE "def $name\\b" "$ROOT/backend/tests" 2>/dev/null; then continue; fi
    if grep -rqF "$name" "$ROOT/frontend/src" --include='*.test.ts' --include='*.test.tsx' 2>/dev/null; then continue; fi
    echo "MISSING  $story  $task  $name"
    missing=$((missing + 1))
  done <<<"$names"
done <<<"$rows"

if [ -n "$phase" ] && [ "$rcount" -eq 0 ]; then
  echo "story-matrix: no rows for phase $phase"
  exit 0
fi
echo "story-matrix: $rcount rows, $tcount tests, $missing missing"
[ "$missing" -eq 0 ] && [ "$bad" -eq 0 ]
