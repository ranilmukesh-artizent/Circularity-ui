#!/bin/bash
# Browser smokes on the main stack, each from the demo's starting state; logs to the audit's evidence folder.
#   bash smokes.sh <tag>        (tag: baseline | after)
export MSYS_NO_PATHCONV=1
R=/c/repos/astra-prism-DI/ayush-ui/Circularity-ui
E=$R/docs/agents/audits/2026-11-24-plan-08/evidence
TAG=${1:-baseline}
cd $R
one() { # one <name> <script>
  bash scripts/dev/reset.sh >/dev/null 2>&1; bash scripts/dev/wait-idle.sh >/dev/null 2>&1
  ( cd frontend && timeout 1500 node scripts/$2 http://localhost:5173 ) > "$E/$TAG-smoke-$1.log" 2>&1
  echo "$1 exit $?" | tee -a "$E/$TAG-smoke-$1.log"
}
one pages smoke-pages.mjs
one rt1048 smoke-rt1048.mjs
one modeler smoke-modeler.mjs
one mvp smoke-mvp.mjs
bash scripts/dev/reset.sh >/dev/null 2>&1
