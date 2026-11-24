#!/bin/bash
# The per-task gate of plan 9 (docs/agents/plans/09-agentic-platform.md, R4, R17). Runs, in order:
#   1. lint.sh;
#   2. api-test.sh <test files> (skipped when no files are given);
#   3. web-check.sh, if `git diff --name-only HEAD` (or an untracked file) touches frontend/;
#   4. the secret scan (R10): the staged and unstaged diff must hold no `gsk_` key-shaped string;
#   5. the plan-file check (R1): the plan may differ from its committed text only in ticked boxes.
# Every step runs; exits 0 only if all pass. Prints a summary line per step. Never edits a file or the git state.
#   bash scripts/dev/gate-p9.sh tests/test_health.py tests/test_x.py
# GATE_LINT, GATE_API and GATE_WEB replace the three commands (default: the real scripts), e.g. to test the gate:
#   GATE_LINT=true GATE_WEB=true GATE_API=false bash scripts/dev/gate-p9.sh tests/test_health.py   # exits 1
# GATE_PLAN replaces the plan path; GATE_PLAN_BASE (a file) replaces `git show HEAD:<plan>` as the text to compare to.
# Same structure as gate-mvp.sh, which stays as it is. Bash 3.2.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
dev="$REPO/scripts/dev"
lint_cmd=${GATE_LINT:-bash $dev/lint.sh}
api_cmd=${GATE_API:-bash $dev/api-test.sh}
web_cmd=${GATE_WEB:-bash $dev/web-check.sh}
plan=${GATE_PLAN:-docs/agents/plans/09-agentic-platform.md}
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

# The plan-file check: both texts with `- [x] ` read as `- [ ] ` must be byte-equal.
plan_check() {
  local base="" tmp_base="" norm_base norm_plan out line rc=0
  [ -f "$plan" ] || { echo "plan file $plan not found" >&2; return 1; }
  if [ -n "${GATE_PLAN_BASE:-}" ]; then
    [ -f "$GATE_PLAN_BASE" ] || { echo "GATE_PLAN_BASE $GATE_PLAN_BASE not found" >&2; return 1; }
    base=$GATE_PLAN_BASE
  elif git_ cat-file -e "HEAD:$plan" 2>/dev/null; then
    tmp_base=$(mktemp "${TMPDIR:-/tmp}/di-gate-base.XXXXXX") || return 1
    git_ show "HEAD:$plan" >"$tmp_base" || { rm -f "$tmp_base"; return 1; }
    base=$tmp_base
  else
    return 99 # not committed yet
  fi
  norm_base=$(mktemp "${TMPDIR:-/tmp}/di-gate-nb.XXXXXX") || return 1
  norm_plan=$(mktemp "${TMPDIR:-/tmp}/di-gate-np.XXXXXX") || return 1
  sed 's/^- \[x\] /- [ ] /' "$base" >"$norm_base"
  sed 's/^- \[x\] /- [ ] /' "$plan" >"$norm_plan"
  if ! out=$(cmp "$norm_base" "$norm_plan" 2>&1); then
    # cmp names the line ("differ: char 5, line 2"); when one text only ends early ("EOF on ... line 2") the next
    # line is the first difference.
    line=$(printf '%s\n' "$out" | sed -n 's/.*line \([0-9][0-9]*\).*/\1/p')
    case $out in *EOF*) line=$((${line:-0} + 1)) ;; esac
    echo "the plan file changed beyond ticked boxes (first difference at line $line)" >&2
    rc=1
  fi
  rm -f "$tmp_base" "$norm_base" "$norm_plan"
  return $rc
}
plan_check
rc=$?
if [ $rc -eq 99 ]; then
  summary="${summary}skip  plan file (not committed yet)"$'\n'
else
  step "plan file" $rc
fi

echo "== gate"
printf '%s' "$summary"
[ $fails -eq 0 ] && echo "gate: all passed" || echo "gate: $fails failed"
[ $fails -eq 0 ]
