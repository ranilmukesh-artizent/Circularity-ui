"""Put di back to the demo's starting state (cases, workspace collections, delegations, grants; journal and
instructions cleared). Connector data is kept. Run: docker compose exec -e PYTHONPATH=/app api python scripts/reset_starting.py
"""

from tests import starting

if __name__ == "__main__":
    starting.reset()
    print("di reset to the starting state")
