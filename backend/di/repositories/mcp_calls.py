"""The MCP call log's collection (the demo's CALLS): the workspace collection "mcp_calls", registered and seeded here
from fixtures/golden/screens/mcp.json. di.mcp.calllog appends the server's calls; the MCP screen reads it."""

from di.core import golden, state

_CALLS: list[dict] = golden.load("screens/mcp")["calls"]  # the demo's CALLS, newest first
# seeded oldest first (CALL-1 is the oldest) and read newest first, as the demo's log (new calls are unshifted)
state.register("mcp_calls", lambda: [(f"CALL-{i + 1}", c) for i, c in enumerate(reversed(_CALLS))])
