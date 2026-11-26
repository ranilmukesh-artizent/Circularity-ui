"""Put di back to the demo's starting state (cases, workspace collections, delegations, grants; journal and
instructions cleared), then seed what a person sees beyond the industrial book: demo cases for every other pack, agent runs
and proposals held for a person (tests/demo_seed.py; `--bare` skips it). Connector data is kept. Run:
docker compose exec -e PYTHONPATH=/app api python scripts/reset_starting.py
"""

import sys

from tests import starting

if __name__ == "__main__":
    starting.reset()
    if "--bare" in sys.argv[1:]:
        print("di reset to the starting state")
    else:
        from tests import demo_seed

        out = demo_seed.seed()
        n = sum(len(v) for v in out["cases"].values())
        print(
            f"di reset to the starting state, with {n} demo cases in {len(out['cases'])} packs and {len(out['runs'])} agent runs"
        )
