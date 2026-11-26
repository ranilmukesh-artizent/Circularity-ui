"""The tools a language model may call when it answers in Ask: read-only, run as the signed-in person, logged.

    tool                  runs                                         from
    get_case_evidence     case.evidence                                B16 MCP tool (di.mcp.tools)
    list_eligible_routes  case.routes                                  B16 MCP tool
    predict_outcomes      case.routes                                  B16 MCP tool
    find_demand           demand.find                                  B16 MCP tool
    optimize_pool         pool.optimize                                B16 MCP tool
    get_model_validation  analytics.models                             B16 MCP tool
    get_decision_flow     flow.get {template, org}                     plan 8 MCP tool (MVP-5.5)
    list_cases            cases.list                                   read action
    get_case              case.get, then case.evidence                 read actions (the case with its evidence sources)
    get_case_run          case.trace                                   read action
    what_if               case.whatIf                                  read action
    explain_kpi           kpi.explain                                  read action
    get_inbox             inbox.get                                    read action
    device_question       device.question                              read action (worked device analytics question)
    list_workflows        workflow.list                                read action (Workflow Studio's list; P9-2.23)
    get_workflow          workflow.get                                 read action (blocks, version, trigger, last run)
    get_workflow_run      workflow.runGet                              read action (steps, log, held records, the error)

Read-only, by construction: the table holds only MCP tools whose `rw` is "read" and actions whose risk is "read"; both
are asserted at import, together with the MCP layer's list of actions no agent may reach (di.mcp.policy
FORBIDDEN_ACTIONS). There is no tool that submits, approves, requests, sends or changes anything, so no answer, and no
text a tool returns, can lead to a write: the most Ask can do is suggest the action for the person to press.

Same pipeline, same boundaries: each call goes through di.services.actions.pipeline.invoke as the signed-in account, with the
assistant ("ask") as preparer, so the permission, the tenant boundary, the warehouse lock and the agent gate apply
exactly as they do to POST /api/actions/{id} and to the MCP server. Only the declared arguments reach an action
(anything else the model sends is dropped), types are checked, and list sizes are capped.

Every call is logged in the MCP call log ("mcp_calls", the MCP & Tools screen) in the B16 shape, with the agent
"Ask Circularity", allowed or refused.

What goes back to the model is data: {"ok": true, "data": ...} or {"ok": false, "error": {code, message}}, compacted
to fit the free tier's token budget (long lists cut, long strings shortened; the cut is marked).
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.trace import StatusCode

from di import telemetry
from di.core import clock, policy
from di.mcp import calllog
from di.mcp.policy import outcome_of
from di.mcp.tools import ACTIONS_OF, RUN, TOOLS, Refused, ToolCall, schema
from di.services.actions import (
    device_learning,  # noqa: F401 - registers device.question before the table below reads it
    workflow_read,  # noqa: F401 - registers workflow.list, get, runs, runGet before the table below reads them
)
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.actions.registry import ACTIONS
from di.services.agents.forbidden import forbidden
from di.services.cases import store

AGENT_ID, AGENT_NAME = "ask", "Ask Circularity"
MCP_TOOLS = (
    "get_case_evidence",
    "list_eligible_routes",
    "predict_outcomes",
    "find_demand",
    "optimize_pool",
    "get_model_validation",
    "get_decision_flow",  # plan 8 MVP-5.5: the decision flow (flow.get), a read
)


def _p(t: str, desc: str, **kw) -> dict:
    return {"type": t, "description": desc, **kw}


CASE_ID = _p("string", "Case id, e.g. RT-1048")
WORKFLOW_ID = _p("string", "Workflow id, e.g. WF-116 (not a case)")
RUN_ID = _p("string", "Workflow run id, e.g. RUN-D1CFE (not a case)")
# an id of a workflow or a workflow run is never a case's: a case tool given one answers wrong_kind without running
WORKFLOW_KIND = re.compile(r"^(?:(WF)-\d+|RUN-[A-Z0-9]{5})$")
# read actions offered to the model: name -> (action, description, JSON schema properties, required)
ACTION_TOOLS: dict[str, tuple[str, str, dict, list[str]]] = {
    "list_cases": (
        "cases.list",
        "List the returned-asset cases the user can see, with stage, recommendation and missing evidence. Filters optional.",
        {
            "stage": _p("string", "awaiting_approval, approved, executing, reeval, closed or none"),
            "owner": _p("string", "Customer A, Customer B or Customer C"),
            "location": _p("string", "Warehouse 1, Warehouse 2 or Repair centre"),
            "missing": _p("boolean", "true: only cases missing evidence"),
            "q": _p("string", "text to search in id, asset id, product, owner, location"),
            "sort": _p("string", "priority, value or received"),
            "limit": _p("number", "at most 10"),
        },
        [],
    ),
    "get_case": (
        "case.get",
        "One case: product, asset, owner, location, stage, grade, recommendation, facts, and its evidence with source systems.",
        {"case_id": CASE_ID},
        ["case_id"],
    ),
    "get_case_run": ("case.trace", "Where a case is in its ten-stage run, and its next step.", {"case_id": CASE_ID}, ["case_id"]),
    "what_if": (
        "case.whatIf",
        "Re-rank a case's routes under changed assumptions (multipliers, 1 = unchanged). Changes nothing.",
        {
            "case_id": CASE_ID,
            "cost": _p("number", "prep and fees multiplier, e.g. 1.3"),
            "market": _p("number", "market price multiplier"),
            "purchase": _p("number", "new purchase price multiplier"),
            "service": _p("number", "service multiplier"),
            "demandOff": _p("boolean", "true: the confirmed demand is cancelled"),
        },
        ["case_id"],
    ),
    "explain_kpi": (
        "kpi.explain",
        "Explain a headline figure: its value, definition and top contributors.",
        {"kpi": _p("string", "assets, potential, risk, co2, recovery, avoided or variance")},
        ["kpi"],
    ),
    "list_workflows": (
        "workflow.list",
        "List the Workflow Studio workflows you can see, with status (published, draft, paused, failing) and last run. "
        "Filters optional.",
        {
            "status": _p("string", "published, draft, paused or failing"),
            "src": _p("string", "source system id, e.g. repair"),
            "q": _p("string", "text to search in name, id, owner"),
            "limit": _p("number", "at most 20"),
        },
        [],
    ),
    "get_workflow": (
        "workflow.get",
        "One workflow (WF-nnn): its blocks, version, status, trigger, last run and recent runs.",
        {"id": WORKFLOW_ID},
        ["id"],
    ),
    "get_workflow_run": (
        "workflow.runGet",
        "One workflow run (RUN-xxxxx): its steps with status and record counts, log lines, held records with the rule that "
        "held them, retries, the error and the page's suggested fix.",
        {"id": RUN_ID},
        ["id"],
    ),
    "get_inbox": ("inbox.get", "What needs the signed-in user now: approvals, evidence gaps, outcomes, notifications.", {}, []),
    "device_question": (
        "device.question",
        "A worked analytics question of the device pack, computed from the data: price_after_launch (why price realised dropped) "
        "or disputes_by_partner (who causes grading disputes). Gives the sentence, chart rows and examples; quote its numbers.",
        {
            "question_id": _p("string", "price_after_launch or disputes_by_partner"),
            "org_unit_id": _p("string", "optional org unit to narrow to"),
        },
        ["question_id"],
    ),
}
TOOL_NAMES = (*MCP_TOOLS, *ACTION_TOOLS)

# ---- read-only, asserted once
for _t in MCP_TOOLS:
    assert TOOLS[_t]["rw"] == "read", f"{_t} is not a read tool"  # noqa: S101 - import-time check: Ask reaches reads only
    assert all(ACTIONS[a].risk == "read" for a in ACTIONS_OF[_t]), f"{_t} reaches an action that is not a read"  # noqa: S101 - import-time check: Ask reaches reads only
for _n, (_a, *_rest) in ACTION_TOOLS.items():
    assert ACTIONS[_a].risk == "read", f"{_n} runs {_a}, which is not a read"  # noqa: S101 - import-time check: Ask reaches reads only
_ALL = [a for t in MCP_TOOLS for a in ACTIONS_OF[t]] + [a for a, *_ in ACTION_TOOLS.values()] + ["case.evidence"]
assert all(ACTIONS[a].risk == "read" for a in _ALL), "every action a tool runs is a read"  # noqa: S101 - import-time check: Ask reaches reads only
assert not [a for a in _ALL if forbidden(a)], "Ask may never reach an action an agent must not run"  # noqa: S101 - import-time check: Ask reaches reads only

PY_TYPE: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "object": dict,
    "array": list,
}
LIST_MAX, STR_MAX, RESULT_MAX = 8, 400, 4000


def specs() -> list[dict]:
    """The tools as JSON-schema function definitions (any provider's format starts from this)."""
    out = []
    for t in MCP_TOOLS:
        out.append({"name": t, "description": TOOLS[t]["desc"], "parameters": schema(TOOLS[t])})
    for name, (_a, desc, props, req) in ACTION_TOOLS.items():
        out.append({"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": req}})
    return out


def _declared(name: str) -> tuple[dict, list[str]]:
    if name in MCP_TOOLS:
        t = TOOLS[name]
        return {k: {"type": v["t"]} for k, v in t["input"].items()}, [k for k, v in t["input"].items() if v.get("req")]
    _a, _d, props, req = ACTION_TOOLS[name]
    return props, req


def shrink(v: Any, lists: int = LIST_MAX, strs: int = STR_MAX, depth: int = 0) -> Any:
    """Compact a tool result for the model: empty fields dropped, lists cut to `lists` items (the cut is said),
    strings to `strs` characters, nesting to 6 levels."""
    if isinstance(v, dict):
        if depth > 6:
            return "…"
        return {k: shrink(x, lists, strs, depth + 1) for k, x in v.items() if x is not None and x != [] and x != {} and x != ""}
    if isinstance(v, list):
        out = [shrink(x, lists, strs, depth + 1) for x in v[:lists]]
        if len(v) > lists:
            out.append(f"… {len(v) - lists} more not shown")
        return out
    if isinstance(v, str) and len(v) > strs:
        return v[:strs] + "…"
    if isinstance(v, float) and v == float("inf"):
        return None
    return v


def as_text(result: dict) -> str:
    """The tool result as the model reads it: compact JSON (always valid), shrunk step by step until it fits
    RESULT_MAX characters (about a thousand tokens)."""
    for lists, strs in ((LIST_MAX, STR_MAX), (5, 200), (3, 120), (2, 80)):
        s = json.dumps(shrink(result, lists, strs), ensure_ascii=False, separators=(",", ":"), default=str)
        if len(s) <= RESULT_MAX:
            break
    return s


@dataclass
class Used:
    """One tool call as Ask reports it."""

    name: str
    args: dict
    ok: bool
    code: str | None
    message: str | None
    data: Any
    ms: int


@dataclass
class Toolbox:
    """The tools for one question, bound to the signed-in account and a database session."""

    session: Any
    account: policy.Account
    pctx: policy.Context
    log: bool = True
    inject: Any = None  # tests: rewrite a tool's data before the model reads it (record text planted in a field)
    used: list[Used] = field(default_factory=list)
    conversation_id: str | None = None  # plan 5: on the chat spans (gen_ai.conversation.id)
    trace_context: Any = None  # plan 5: the OpenTelemetry context of the Ask span; tool and chat spans are its children

    @property
    def specs(self) -> list[dict]:
        return specs()

    def ctx(self) -> CallContext:
        return CallContext(actor=Actor(account=self.account, ctx=self.pctx), session=self.session, preparer=AGENT_ID)

    def call(self, name: str, arguments: Any) -> dict:
        """Run one tool; returns what the model reads ({ok, data} or {ok: false, error})."""
        return self.call_with_id(name, arguments, None)

    def call_with_id(self, name: str, arguments: Any, call_id: str | None) -> dict:
        """`call`, as the provider's tool call `call_id`: one `execute_tool {name}` span (OpenTelemetry GenAI), a child of
        the Ask span. Arguments and results are on the span only with DI_OTEL_CAPTURE_CONTENT; never otherwise."""
        attrs: dict[str, Any] = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name}
        if call_id:
            attrs["gen_ai.tool.call.id"] = call_id
        with telemetry.span(f"execute_tool {name}", attributes=attrs, context=self.trace_context) as sp:
            res = self._call(name, arguments)
            if sp is not None:
                if not res["ok"]:
                    sp.set_attribute("error.type", str(res["error"]["code"]))
                    sp.set_status(StatusCode.ERROR)
                if telemetry.capture_content():
                    sp.set_attribute("gen_ai.tool.call.arguments", telemetry.clip(json.dumps(arguments, default=str)))
                    sp.set_attribute("gen_ai.tool.call.result", telemetry.clip(as_text(res)))
            return res

    def _call(self, name: str, arguments: Any) -> dict:
        t0 = time.monotonic()
        args = arguments
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                args = None
        if not isinstance(args, dict):
            res = self._done(name, {}, t0, error=("validation_error", "Arguments must be a JSON object."))
        elif name not in TOOL_NAMES:
            res = self._done(name, args, t0, error=("not_found", f"No tool {name}. Tools: {', '.join(TOOL_NAMES)}."))
        else:
            res = self._run(name, args, t0)
        return res

    def _run(self, name: str, args: dict, t0: float) -> dict:
        props, req = _declared(name)
        clean = {k: args[k] for k in props if k in args and args[k] is not None}
        for k in req:
            if clean.get(k) in (None, ""):
                return self._done(name, clean, t0, error=("validation_error", f'Missing required field "{k}".'))
        for k, v in clean.items():
            want = PY_TYPE.get(props[k]["type"])
            if want and (not isinstance(v, want) or (props[k]["type"] == "number" and isinstance(v, bool))):
                return self._done(name, clean, t0, error=("validation_error", f'"{k}" must be a {props[k]["type"]}.'))
        if isinstance(clean.get("case_id"), str) and (m := WORKFLOW_KIND.match(clean["case_id"].strip())):
            what, use = ("a workflow", "get_workflow") if m[1] else ("a workflow run", "get_workflow_run")
            msg = f"{clean['case_id']} is {what}, not a case. Use {use} with this id."
            return self._done(name, clean, t0, error=("wrong_kind", msg))
        ctx = self.ctx()
        try:
            if name in MCP_TOOLS:
                cid = clean.get("case_id") if "case_id" in clean else clean.get("pool_id")
                case = store.get(self.session, cid) if isinstance(cid, str) and cid else None
                if isinstance(clean.get("case_id"), str) and re.match(r"RT-", clean["case_id"]) and case is None:
                    return self._done(name, clean, t0, error=("case_not_found", f"No live case {clean['case_id']}."))
                tc = ToolCall(tool=TOOLS[name], args=clean, case=case, tenant=None, ctx=ctx, step=lambda *_: True)
                data = RUN[name](tc)
            else:
                action = ACTION_TOOLS[name][0]
                if name == "list_cases":
                    clean["limit"] = min(int(clean.get("limit") or 10), 10)
                r = invoke(action, clean, ctx)
                if not r["ok"]:
                    return self._done(name, clean, t0, error=(r["error"]["code"], r["error"]["message"]))
                data = r["output"]
                if name == "get_case":  # with its evidence and the systems it comes from (case.evidence, same pipeline)
                    ev = invoke("case.evidence", {"case_id": clean["case_id"]}, ctx)
                    if ev["ok"]:
                        keep = ("label", "state", "system", "source", "record", "fresh", "note")
                        data = {**data, "evidence": [{k: e.get(k) for k in keep if e.get(k)} for e in ev["output"]["items"]]}
        except Refused as e:
            return self._done(name, clean, t0, error=(e.code, e.message))
        if self.inject:
            data = self.inject(name, data)
        return self._done(name, clean, t0, data=data)

    def _done(self, name: str, args: dict, t0: float, data: Any = None, error: tuple[str, str] | None = None) -> dict:
        ms = round((time.monotonic() - t0) * 1000)
        code, message = error if error else (None, None)
        self.used.append(Used(name, args, error is None, code, message, data, ms))
        if self.log:
            log_call(self.session, self.account, name, args, ms, code)
        if error:
            return {"ok": False, "error": {"code": code, "message": message}}
        return {"ok": True, "data": data}


def log_call(session: Any, account: policy.Account, tool: str, args: dict, ms: int, code: str | None) -> None:
    """One call-log entry in B16's shape (di.mcp.policy._log), with the agent "Ask Circularity"; committed at once so
    the MCP & Tools screen shows it while the answer is still streaming."""
    cid = args.get("case_id") or args.get("pool_id")
    t = TOOLS.get(tool)
    calllog.record(
        session,
        {
            "ts": calllog.iso_ms(clock.now()),
            "agent": AGENT_NAME,
            "tool": tool,
            "caseId": cid if isinstance(cid, str) and cid else "—",
            "tenant": account.tenant or "—",
            "lat": ms,
            "outcome": "ok" if code is None else outcome_of(code),
            "step": t["step"][0] if t else None,
            "account": account.id,
            "code": code,
        },
    )
    session.commit()
