#!/bin/bash
# tsc + vitest (+ eslint/knip with "lint") for a worktree's frontend (WT, default Circularity-ui-merge; node_modules in
# volume NM, default merge_node_modules, filled once with npm ci). `vitest <file>` runs one file.
export MSYS_NO_PATHCONV=1
FIX="C:/repos/astra-prism-DI/ayush-ui/${WT:-Circularity-ui-merge}"
NM=${NM:-merge_node_modules}
run() { docker run --rm -v "$FIX/frontend:/app" -v "$NM:/app/node_modules" -w /app circularity-ui-web sh -c "$1"; }
if [ "$1" = "vitest" ]; then shift; run "npx vitest run $*"; exit $?; fi
if [ "$1" = "install" ]; then run "npm ci --no-audit --no-fund >/dev/null 2>&1; echo npm-ci \$?"; exit $?; fi
run "npx tsc -b && npx vitest run" || exit 1
[ "$1" = "lint" ] && run "npx eslint . && npx knip"
