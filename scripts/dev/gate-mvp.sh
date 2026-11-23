#!/bin/bash
# The per-task gate of plan 08 (docs/agents/plans/08-mvp-decision-platform.md, R4 and R17). Runs, in order:
#   1. lint.sh;
#   2. api-test.sh <test files> (skipped when no files are given);
#   3. web-check.sh, if `git diff --name-only HEAD` (or an untracked file) touches frontend/;
#   4. the secret scan (R10): the staged and unstaged diff must hold no `gsk_` key-shaped string.
# Every step runs; exits 0 only if all pass. Prints a summary line per step.
#   bash scripts/dev/gate-mvp.sh tests/test_health.py tests/test_x.py
# GATE_LINT, GATE_API and GATE_WEB replace the three commands (default: the real scripts), e.g. to test the gate:
#   GATE_LINT=true GATE_WEB=true GATE_API=false bash scripts/dev/gate-mvp.sh tests/test_health.py   # exits 1
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
dev="$REPO/scripts/dev"
lint_cmd=${GATE_LINT:-bash $dev/lint.sh}
api_cmd=${GATE_API:-bash $dev/api-test.sh}
web_cmd=${GATE_WEB:-bash $dev/web-check.sh}
# The checkout may belong to another user (e.g. /mnt/c from WSL as root), and file modes may not be tracked there.
git_() { git -c safe.directory="$REPO" -c core.fileMode=false "$@"; }

summary=""
fails=0
step() { # step <label> <rc>
  if [ "$2" -eq 0 ]; then
    summary="${summary}ok    $1"$'\n'
  else
    summary="${summary}FAIL  $1 (exit $2)"$'\n'
    fails=$((fails + 1))
  fi
}

echo "== lint"
$lint_cmd
step lint $?

if [ $# -gt 0 ]; then
  echo "== api tests: $*"
  $api_cmd "$@"
  step "api tests" $?
else
  summary="${summary}skip  api tests (no files given)"$'\n'
fi

changed=$(git_ diff --name-only HEAD && git_ ls-files --others --exclude-standard -- frontend)
rc=$?
if [ $rc -ne 0 ]; then
  echo "git could not list the changed files" >&2
  step "changed files (git)" $rc
elif printf '%s\n' "$changed" | grep -q '^frontend/'; then
  echo "== web check"
  $web_cmd
  step "web check" $?
else
  summary="${summary}skip  web check (frontend/ unchanged)"$'\n'
fi

# Never print the match itself (AGENTS.md rule 4): only whether there is one.
if git_ diff HEAD | grep -qE 'gsk_[A-Za-z0-9]{20,}'; then
  echo "a key-shaped string (gsk_...) is in the diff: remove it before committing" >&2
  step "secret scan" 1
else
  step "secret scan" 0
fi

echo "== gate"
printf '%s' "$summary"
[ $fails -eq 0 ] && echo "gate: all passed" || echo "gate: $fails failed"
[ $fails -eq 0 ]
