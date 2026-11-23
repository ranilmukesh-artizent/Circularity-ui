#!/bin/bash
# Lint the api and the web app inside their containers. Exits non-zero if any check fails; prints at most 60 lines.
#   bash scripts/dev/lint.sh
# api container (backend): ruff check, ruff format --check, mypy (config in backend/pyproject.toml), lint-imports
# (backend/.importlinter). web container (frontend): eslint and knip. Every check runs even after one fails.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
report=""
fails=0
check() { # check <label> <command...>: record the result and up to 8 lines of output of a failing check
  local label=$1 out rc
  shift
  out=$("$@" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    report="${report}ok    $label"$'\n'
  else
    fails=$((fails + 1))
    report="${report}FAIL  $label (exit $rc)"$'\n'"$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | tail -n 8)"$'\n'
  fi
}
check "ruff check" docker compose exec -T api ruff check .
check "ruff format --check" docker compose exec -T api ruff format --check .
check "mypy" docker compose exec -T api mypy
check "lint-imports" docker compose exec -T api lint-imports
check "eslint" docker compose exec -T web npx eslint .
check "knip" docker compose exec -T web npx knip
printf '%s' "$report" | head -n 58
[ $fails -eq 0 ] && echo "lint: all passed" || echo "lint: $fails failed"
[ $fails -eq 0 ]
