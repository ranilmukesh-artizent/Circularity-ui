"""One tool call, checked in the demo's order (index.html, `runTool`), run, and logged.

    1 Authenticate agent token   the account (bearer token) and the agent (X-Agent, in the agent registry: plan 8
                                 MVP-11.3) are known, the agent is not stopped by its kill switch (the demo's
                                 afAgentAllowed), the tenant is in the agent's org scope, and the account may act for
                                 the tenant it names (tenant consent; the server's addition, checked on every call)
    2 Check agent scope          the tool is one of the agent's tools (AGENTS)
      (hard rule)                send_instruction with no approval reference stops here
    3 Validate input schema      required fields and types (the demo's messages)
    4 Resolve case               an RT- case id that does not exist
    5 Enforce tenant boundary    the case belongs to the tenant the call is for
    6 Run tool                   the tool's action(s) through the pipeline, as the account, prepared by the agent
    7 Write audit record         the call log (every call, also the refused ones, is logged)

The answer is the demo's: {ok, outcome, case_id, result | error, trace}; `outcome` is the call log's: "ok", "held for
approval" (approval_required, held), "denied · …" (out_of_scope, tenant_boundary) or "error · <code>". The demo
writes the denied ones with `code.replace('_', ' ')`, which replaces the first underscore only ("denied · out
of_scope"); the server keeps that, so its log reads like the demo's.

The action pipeline adds its own checks on top (permission, tenant boundary and warehouse lock of the account, the
agent gate, state guards, idempotency): a refusal there is the tool's refusal, with the pipeline's code and message.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from di.core import clock, policy, state
from di.core.auth import principal
from di.mcp import calllog
from di.mcp.tools import ACTIONS_OF, AGENTS, NO_APPROVAL_REF, RUN, TOOLS, Refused, ToolCall, cross_tenant
from di.services.actions.pipeline import Actor, CallContext
from di.services.agents import registry as agent_registry
from di.services.cases import store

# Actions no tool may ever run (hard rules: no approving, overriding or declining a decision, no access, publishing or
# connection changes, no confirming outcomes on a person's behalf). Checked once, against the whole tool table.
FORBIDDEN_ACTIONS = (
    "decision.approve", "decision.override", "decision.decline", "outcome.confirm", "adapter.acknowledge",
    "access.", "agent.", "workflow.publish", "workflow.setStatus", "workflow.delete", "source.", "mcp.",
    "org.create", "org.update", "org.move",  # plan 8 MVP-1.3: the org tree decides who sees what (access)
    "org.setPilot",  # plan 8 MVP-10.3: whether a pilot org's instructions are sent (outbound sending)
    "org.importPack",  # plan 8 MVP-10.2: sets up another org's sources, workflows and flows
    "proposal.",  # plan 8 MVP-11.4: only a person accepts or rejects an agent's proposal
    "flow.approve", "flow.publish", "flow.reject", "flow.rollback",  # plan 8 MVP-3.2: a person decides the policy
    "model.promote",  # plan 8 MVP-12.2: a person decides which model values new cases
)  # fmt: skip
_REACHED = [a for acts in ACTIONS_OF.values() for a in acts if a.startswith(FORBIDDEN_ACTIONS)]
if _REACHED:
    raise RuntimeError(f"tools reach actions no agent may run: {_REACHED}")

PY_TYPE: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "object": dict,
    "array": list,
}


@dataclass
class Caller:
    """Who is calling: the account behind the bearer token, the agent it names, the tenant it acts for."""

    token: str | None
    agent_id: str | None
    tenant: str | None


@dataclass
class Call:
    """The state of one call: its trace and, at the end, its answer."""

    tool_id: str
    agent: dict | None = None
    tenant: str | None = None
    account: str | None = None  # the account id behind the token
    case_id: Any = None  # the case the arguments name, once they are read (the demo logs "—" before that)
    trace: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)

    def step(self, n: str, ok: bool, detail: str) -> bool:
        self.trace.append({"n": n, "ok": ok, "detail": detail})
        return ok

    @property
    def ms(self) -> int:
        return round((time.monotonic() - self.started) * 1000)

    def answer(self, ok: bool, outcome: str, body: dict) -> dict:
        return {
            "ok": ok,
            "outcome": outcome,
            "case_id": self.case_id,
            **body,
            "trace": self.trace,
            "ms": self.ms,
            "tool": self.tool_id,
            "agent": self.agent["id"] if self.agent else None,
            "tenant": self.tenant,
        }

    def fail(self, code: str, message: str, extra: dict | None = None) -> dict:
        return self.answer(False, outcome_of(code), {"error": {"code": code, "message": message, **(extra or {})}})


def agent_of(row: agent_registry.Agent | None) -> dict | None:
    """The agent as the checks read it: a registered agent, with the tools its registry row allows (MVP-11.3). The
    demo's nine keep their scopes text; another agent's scopes are its tools."""
    if row is None:
        return None
    base = AGENTS.get(row.id) or {"id": row.id, "scopes": row.tools}
    return {**base, "id": row.id, "name": row.name, "tools": row.tools}


def outcome_of(code: str) -> str:
    """The call log's outcome for a refusal (the demo's runTool `fail`)."""
    if code in ("approval_required", "held"):
        return "held for approval"
    if code in ("out_of_scope", "tenant_boundary"):
        return "denied · " + code.replace("_", " ", 1)
    return "error · " + code


def _type_error(value: Any, t: str) -> bool:
    want = PY_TYPE.get(t)
    if want is None:
        return False
    return not isinstance(value, want) or (t == "number" and isinstance(value, bool))


def _account(s: Session, token: str | None) -> tuple[policy.Account, policy.Context] | None:
    """The account behind a bearer token, as /api endpoints resolve it (di.core.auth.principal), or None."""
    if not token:
        return None
    try:
        p = principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), s)
    except HTTPException:
        return None
    return p.account, p.ctx


def account_of(token: str | None) -> policy.Account | None:
    """For the HTTP gate: the token's account, or None."""
    from di.core.db import SessionLocal

    with SessionLocal() as s:
        a = _account(s, token)
        return a[0] if a else None


def call_tool(s: Session, who: Caller, tool_id: str, arguments: dict | None) -> dict:
    """Check, run and log one tool call; returns the answer. Commits the action's effects and the log entry."""
    call = Call(tool_id)
    try:
        answer = _run(s, who, call, tool_id, arguments if isinstance(arguments, dict) else {})
    except Exception:  # an unexpected failure is still a call: roll back what it did, log it, and re-raise
        s.rollback()
        _log(s, call, who, tool_id, call.fail("internal_error", "The tool failed on the server."))
        s.commit()
        raise
    _log(s, call, who, tool_id, answer)
    s.commit()
    return answer


def _run(s: Session, who: Caller, call: Call, tool_id: str, args: dict) -> dict:
    tool = TOOLS.get(tool_id)
    if tool is None:
        return call.fail("not_found", f"No tool {tool_id}. Tools: {', '.join(TOOLS)}.")
    acct = _account(s, who.token)
    if acct is None:  # the HTTP gate lets no such request through; kept for direct callers
        call.step("Authenticate agent token", False, "No valid account token")
        return call.fail("out_of_scope", "Sign in first.")
    account, pctx = acct
    call.account = account.id
    # 1 authenticate: the agent (registered), its kill switch, the tenant it acts for
    row = agent_registry.get(s, who.agent_id) if who.agent_id else None
    ag = agent_of(row)
    call.agent = ag
    call.tenant = who.tenant or account.tenant
    if ag is None or row is None:
        call.step("Authenticate agent token", False, f"Unknown agent {who.agent_id}" if who.agent_id else "No agent named")
        return call.fail("out_of_scope", f"Name the agent you act as in the X-Agent header: one of {', '.join(AGENTS)}.")
    if not row.enabled or (state.get(s, "access_settings", "agents_off") or {}).get(ag["id"]):
        call.step("Authenticate agent token", False, f"{ag['name']} is stopped")
        return call.fail("out_of_scope", f"{ag['name']} is stopped by Admin, so it cannot prepare anything.")
    if call.tenant is not None and not agent_registry.in_scope(row, call.tenant, policy.org_units(pctx)):
        call.step("Authenticate agent token", False, f"{call.tenant} is outside the org scope of {ag['name']}")
        return call.fail("tenant_boundary", f"{ag['name']} is not scoped for {call.tenant}.")
    if call.tenant is not None and not policy.tenant_ok(account, call.tenant, pctx):
        call.step("Authenticate agent token", False, f"No consent on file for {account.label} to act for {call.tenant}")
        return call.fail(
            "tenant_boundary",
            f"{account.label} cannot act on behalf of {call.tenant}: tenant consent is not on file. Request tenant access first.",
        )
    call.step("Authenticate agent token", True, ag["name"] + " · service identity")
    # 2 scope
    if tool_id not in ag["tools"]:
        call.step("Check agent scope", False, f"{ag['name']} is not scoped for {tool_id}")
        return call.fail("out_of_scope", f"{ag['name']} cannot call {tool_id}. Scopes: {', '.join(ag['scopes'])}.")
    call.step("Check agent scope", True, ", ".join(ag["scopes"]))
    call.case_id = args.get("case_id")
    # hard rule: nothing is sent to an enterprise system without an approval reference
    if tool_id == "send_instruction" and args.get("approval_ref") in (None, ""):
        call.step("Verify approval reference", False, "No approval reference")
        return call.fail(
            "approval_required", f"{NO_APPROVAL_REF} Approve the case in Product first, then pass its reference as approval_ref."
        )
    # 3 validate (only the declared fields go further: anything else in the call is dropped)
    for k, v in tool["input"].items():
        if v.get("req") and args.get(k) in (None, ""):
            call.step("Validate input schema", False, f'Missing "{k}"')
            return call.fail("validation_error", f'Missing required field "{k}".')
        if k in args and _type_error(args[k], v["t"]):
            call.step("Validate input schema", False, f"{k} must be {v['t']}")
            return call.fail("validation_error", f'"{k}" must be a {v["t"]}.')
    call.step("Validate input schema", True, f"{len(args)} fields")
    clean = {k: args[k] for k in tool["input"] if k in args}
    # 4 resolve the case (and, for a pool, the pool's case)
    cid = clean.get("case_id") if "case_id" in clean else clean.get("pool_id")
    case = store.get(s, cid) if isinstance(cid, str) and cid else None
    if isinstance(clean.get("case_id"), str) and clean["case_id"].startswith("RT-") and case is None:
        call.step("Resolve case", False, "Unknown case")
        return call.fail("case_not_found", f"No live case {clean['case_id']}.")
    # 5 tenant boundary: the case belongs to the tenant the call is for
    if "case_id" in clean and case is not None and call.tenant and case["owner"] != call.tenant:
        call.step("Enforce tenant boundary", False, f"{case['owner']} data requested on behalf of {call.tenant}")
        return call.fail("tenant_boundary", cross_tenant(case["id"], case["owner"], call.tenant))
    scope = call.tenant or ", ".join(policy.allowed_tenants(account, pctx))
    call.step("Enforce tenant boundary", True, scope + " · own data only")
    # 6 run, as the account, prepared by the agent (never confirmed: the agent cannot press a person's final button)
    ctx = CallContext(actor=Actor(account=account, ctx=pctx), session=s, preparer=ag["id"])
    t = ToolCall(tool=tool, args=clean, case=case, tenant=call.tenant, ctx=ctx, step=call.step)
    try:
        result = RUN[tool_id](t)
    except Refused as e:
        if e.step is not None:
            call.step("Run tool", False, e.step)
        return call.fail(e.code, e.message, e.extra)
    call.step("Run tool", True, "write sent within scope" if tool["rw"] == "write" else "read-only")
    call.step("Write audit record", True, "call logged with agent, tenant and case")
    return call.answer(True, "ok", {"result": result})


def _log(s: Session, call: Call, who: Caller, tool_id: str, answer: dict) -> None:
    """The demo's call-log entry (ACT.pgRun), plus who called and the refusal code."""
    tool = TOOLS.get(tool_id)
    case = call.case_id if isinstance(call.case_id, str) and call.case_id else "—"
    calllog.record(
        s,
        {
            "ts": calllog.iso_ms(clock.now()),
            "agent": call.agent["name"] if call.agent else (who.agent_id or "—")[:64],
            "tool": tool_id,
            "caseId": case,
            "tenant": call.tenant or "—",
            "lat": answer["ms"],
            "outcome": answer["outcome"],
            "step": tool["step"][0] if tool else None,
            "account": call.account,
            "code": None if answer["ok"] else answer["error"]["code"],
        },
    )


def text_of(answer: dict) -> str:
    """The answer as text, for clients that read text content: the same JSON (data, never instructions)."""
    return json.dumps(answer, ensure_ascii=False, default=str)
