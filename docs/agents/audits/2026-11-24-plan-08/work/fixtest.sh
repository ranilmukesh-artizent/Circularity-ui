#!/bin/bash
# Run api tests from the fix worktree in a one-off container against the private database di_fix.
export MSYS_NO_PATHCONV=1
FIX='C:\repos\astra-prism-DI\ayush-ui\Circularity-ui-fix'
docker run --rm --network circularity-ui_default \
  -v "$FIX\backend:/app" -v "$FIX\fixtures:/fixtures" -v "$FIX\ruff.toml:/ruff.toml" -w /app \
  -e DI_DATABASE_URL=postgresql+psycopg://circ:circ@postgres:5432/${FIX_DB:-di_fix} -e DI_SOURCE_SIM_URL=http://source-sim:8100 \
  -e DI_CLOCK=sim -e DI_ENV=dev -e DI_INSTRUCTIONS=true -e ASK_PROVIDER=groq \
  circularity-ui-api pytest -q -p no:cacheprovider -rfE "$@"
