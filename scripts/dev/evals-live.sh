#!/bin/bash
# Run the agent eval datasets against each enabled real model (by hand or nightly), outside the gate (plan 9, P9-2.15; R16).
#   bash scripts/dev/evals-live.sh
# The same datasets and evaluators as tests/evals/test_evals.py, with the router's model in the loop instead of the scripted
# ones; for each model it writes eval_score (percent of cases that held), eval_prev (the last score) and eval_at to llm_model,
# and prints each model's id and scores. The router leaves a model out of a role when its score fell more than 10 points
# (di.services.llm.router.chain_for). The key is read only from the environment the api container already has (the row's key_ref
# names the variable): this script never reads or prints it and never reads .env. Without a key nothing runs (exit 1).
# It resets the demo's starting state at every case and at the end, so it takes the api test lock like api-test.sh (never run it
# beside a test run), and the worker is stopped for the run and started again after. A 60-minute timeout runs in the container.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
api_lock || exit 1
docker compose stop worker >/dev/null 2>&1
trap 'docker compose start worker >/dev/null 2>&1' EXIT
filtered '.' 40 docker compose exec -T api timeout 3600 python -m tests.evals.live
