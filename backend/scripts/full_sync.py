"""Sync every source once, in full, and print a summary: records, facts, failures, and the open conflicts by field.

docker compose exec -T api python scripts/full_sync.py
"""

from sqlalchemy import text

from di.connectors.registry import ADAPTERS
from di.connectors.sync import ensure_sources, run_sync
from di.core.db import SessionLocal

# order matters for adapters that look up another source's facts (bom reads plm's configuration_item)
FIRST = ["eam", "plm", "lease", "wms", "rl", "oms"]


def main() -> None:
    with SessionLocal() as s:
        ensure_sources(s)
    order = FIRST + sorted(set(ADAPTERS) - set(FIRST))
    print(f"{'source':8} {'status':8} {'read':>6} {'facts':>7} {'failed':>6}  error")
    for sid in order:
        out = run_sync(sid, "manual", full=True)
        print(
            f"{sid:8} {out['status']:8} {out.get('records_read', 0):>6} {out.get('facts_written', 0):>7} "
            f"{out.get('records_failed', 0):>6}  {(out.get('error') or '')[:80]}"
        )
    with SessionLocal() as s:
        print("\nopen conflicts by field (authority):")
        for r in s.execute(
            text(
                "SELECT model || '.' || field AS f, authority, count(*) AS n, string_agg(DISTINCT k, ',') AS srcs FROM ("
                "  SELECT c.*, jsonb_object_keys(c.\"values\") AS k FROM conflict c WHERE status = 'open') x "
                "GROUP BY 1, 2 ORDER BY 3 DESC"
            )
        ):
            print(f"  {r.f:40} {r.n:>5}  authority {r.authority:7} sources {r.srcs}")
        print(
            "\ncanonical records by model:",
            dict(s.execute(text("SELECT model, count(*) FROM canonical GROUP BY 1 ORDER BY 1")).all()),
        )


if __name__ == "__main__":
    main()
