#!/usr/bin/env bash
# The live check of the assistant over real HTTP (ai-tasks 8.1): see ai-live-check.mjs. Needs host Node 20+.
set -euo pipefail
cd "$(dirname "$0")/../.."
exec node scripts/dev/ai-live-check.mjs "$@"
