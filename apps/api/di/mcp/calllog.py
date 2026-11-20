"""The MCP call log: every tool call, allowed, held or denied, in the workspace collection "mcp_calls".

The collection is the demo's CALLS, registered and seeded in di.reads.mcp_calls ( CALL-1 … CALL-64, read
newest first). A call is appended in the demo's shape (ACT.pgRun: ts, agent, tool, caseId, tenant, lat, outcome,
step), plus who called (`account`) and the refusal code (`code`, null for an allowed call), so the screen's call log,
its "held or denied" filter and its counts show server calls next to the demo's.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from di import state
from di.reads import mcp_calls  # noqa: F401  (registers the "mcp_calls" collection and its starting calls)

COLLECTION = "mcp_calls"


def iso_ms(t: datetime) -> str:
    """`new Date().toISOString()`: UTC, milliseconds, Z."""
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def record(s: Session, entry: dict) -> str:
    """Append one call (it becomes the newest); returns its id (CALL-<n>)."""
    n = state.next_number(s, COLLECTION, "CALL-", 0)
    state.add(s, COLLECTION, f"CALL-{n}", entry)
    return f"CALL-{n}"
