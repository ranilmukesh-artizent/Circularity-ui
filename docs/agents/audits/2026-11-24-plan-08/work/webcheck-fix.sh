#!/bin/bash
# tsc + vitest (+ eslint with "lint") for the FIX WORKTREE's frontend, in a one-off container from the web image.
# node_modules live in the docker volume fix_node_modules (filled once by `npm ci`). Usage:
#   bash webcheck-fix.sh            # tsc -b and vitest run
#   bash webcheck-fix.sh lint       # also eslint and knip
#   bash webcheck-fix.sh vitest src/api/orgs.test.ts   # one vitest file
export MSYS_NO_PATHCONV=1
FIX='C:\repos\astra-prism-DI\ayush-ui\Circularity-ui-fix'
run() { docker run --rm -v "$FIX\frontend:/app" -v fix_node_modules:/app/node_modules -w /app circularity-ui-web sh -c "$1"; }
if [ "$1" = "vitest" ]; then shift; run "npx vitest run $*"; exit $?; fi
run "npx tsc -b && npx vitest run" || exit 1
[ "$1" = "lint" ] && run "npx eslint . && npx knip"
