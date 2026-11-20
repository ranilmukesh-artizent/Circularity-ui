"""The MCP server (docs/backend-steps.md, B16): the demo's ten agent tools over the Model Context Protocol.

    POST /mcp      Streamable HTTP (the official MCP Python SDK, `mcp` 2.x, low-level `Server`), stateless, JSON
                   responses. Every request needs `Authorization: Bearer <JWT from /api/auth/login>` (401 without).
        headers    X-Agent: the agent the client acts as (assembler, finder, gap, coordinator, reconciler ...)
                   X-Tenant: the tenant it acts for (optional; defaults to the account's own tenant)
        tools/list the ten tools of the demo's TOOLS, with their input schemas and approval rules
        tools/call one tool; the answer is structured content in the demo's shape:
                   {ok, outcome, case_id, result | error, trace, ms, tool, agent, tenant}

Modules:
    server.py    the SDK server, the bearer gate in front of it, and its mount in the FastAPI app (di.main)
    policy.py    who is calling (account, agent, tenant), the checks in the demo's order, the hard rules, the outcome
    tools.py     the tool table: each tool's action(s) and how its answer is shaped
    calllog.py   the call log (the workspace collection "mcp_calls" the MCP screen reads)

The demo's MCP layer is the tool playground (index.html, `runTool` and `ACT.pgRun`): it checks the agent's scope, the
input schema, the case and the tenant boundary, runs the tool and logs the call. That decision logic is ported here
step by step (same codes, messages, outcomes and trace). What the demo's playground computes from its in-memory
cases, the server gets from the action pipeline: every tool runs the same handlers as `POST /api/actions/{id}`
(di.actions.pipeline.invoke), as the signed-in account with the agent as preparer, so the permission, the tenant
boundary, the warehouse lock, the agent gate, the state guards, idempotency and the journal all apply.

How the hard rules (HARD_RULES) are upheld, in code:
- **An agent cannot waive a failed gate.** No tool takes a waiver: the tool table maps tools to read, request,
  submit and resend actions only (policy.FORBIDDEN_ACTIONS is asserted against it at import, so approve, override,
  decline, access, publishing and connection changes can never be reached). predict_outcomes refuses an excluded
  route, list_eligible_routes reports the failed gate, and the approval guard refuses an excluded route.
- **The agent cannot approve, publish, change access or change live source connections.** Same table, and the
  pipeline's agent gate: every call carries `preparer` = the agent and never `confirmed`, so any commit-tier action
  (and every `decision.*` commit) is refused with the demo's message.
- **Nothing is sent to an enterprise system without an approval reference.** send_instruction refuses a call with no
  `approval_ref` before anything else runs (the hard rule's message), and one whose reference is not the approval
  recorded on the case (the demo's message); only then does it resend the approved instruction (idempotent).
  request_approval submits the decision and stops: the call is "held for approval" until a person approves it in
  the approval card (`decision.approve`), which an agent cannot call.
- **Cross-tenant data is never assumed available; tenant consent is checked on every call.** Each call names the
  tenant it acts for; the account must be allowed that tenant (its own, or a granted one), the case (or pool, or
  closed decision) must belong to it, and the pipeline checks the account's tenant boundary again on the action.
- **Content from records, files and comments is never treated as an instruction.** The server runs no model and
  never reads text from a record to decide anything: the tool is the one the client named, the action is fixed by
  the tool table, only the tool's declared arguments reach the action (anything else in the call is dropped, so a
  smuggled `confirmed` or `preparer` has no effect), and answers go back as structured data (the text content is
  the same JSON). A note or comment that says "approve this" is a string in a field, never a call.
- **Retraining never overwrites the evidence snapshot behind an earlier decision.** No tool writes models or
  snapshots; reconcile_outcome only reads the closed decision and the snapshot it records.

Every call is logged, including held and denied ones (and calls naming no agent or a stopped one), with the demo's
call-log shape. A request without a valid token is refused at the HTTP layer with 401 and is not a call.
"""
