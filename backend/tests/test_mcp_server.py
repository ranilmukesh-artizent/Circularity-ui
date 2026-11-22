"""B16: the MCP server. An MCP client (the SDK's own) against the running api server at http://localhost:8000/mcp.

As in test_stream.py, these tests talk to the api in this container over real HTTP: the MCP transport runs in the
app's lifespan, which the in-process TestClient does not start. The worker is stopped for the test run. The starting
state is restored before and after the module, and before each parity scenario (each is a fresh copy of the demo).

- the ten tools are listed with descriptions, input schemas and approval rules; a request without a token is 401
- an agent reads evidence; send_instruction without an approval reference is refused with the hard rule's message;
  a tool outside the agent's scope, another tenant's case, a tenant without consent, an unknown or stopped agent
  are denied
- request_approval submits and is held for a person; the person's approval (POST /api/actions/decision.approve) lets
  send_instruction go with the approval reference; the journal shows the agent as preparer
- every call, allowed, held and denied, is in the call log (/api/screens/mcp/calls)
- parity: fixtures/golden/mcp.json (the demo's tool playground, frontend/scripts/golden/mcp_calls.mjs) replayed
  through the server: results, refusals, traces and log entries
"""

import re

import anyio
import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

import di.core.policy  # noqa: F401  (registers the "access_settings" collection the kill switch is kept in)
from di.core import golden, state
from tests import starting

API = "http://localhost:8000"
G = golden.load("mcp")["scenarios"]
REF = golden.load("tools")
TOOL_IDS = [t["id"] for t in REF["tools"]]
NO_APPROVAL_REF = REF["hard_rules"][2]
_tokens: dict[str, str] = {}


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def token(user: str) -> str:
    if user not in _tokens:
        r = httpx.post(f"{API}/api/auth/login", json={"username": user, "password": "x"})
        r.raise_for_status()
        _tokens[user] = r.json()["access_token"]
    return _tokens[user]


def headers(user: str, agent: str | None = None, tenant: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {token(user)}"}
    if agent:
        h["X-Agent"] = agent
    if tenant:
        h["X-Tenant"] = tenant
    return h


def with_client(h: dict, fn):
    """Run fn(client) with an MCP client connected as these headers."""

    async def main():
        async with httpx2.AsyncClient(headers=h) as hc, Client(streamable_http_client(f"{API}/mcp", http_client=hc)) as c:
            return await fn(c)

    return anyio.run(main)


def call(user: str, agent: str | None, tool: str, args: dict, tenant: str | None = None) -> dict:
    """One tool call; returns the structured answer (and checks the text content and isError agree with it)."""

    async def go(c):
        return await c.call_tool(tool, args)

    r = with_client(headers(user, agent, tenant), go)
    a = r.structured_content
    assert r.is_error is (not a["ok"])
    assert r.content and r.content[0].type == "text" and '"outcome"' in r.content[0].text
    return a


def action(user: str, action_id: str, body: dict) -> dict:
    return httpx.post(f"{API}/api/actions/{action_id}", json=body, headers=headers(user)).json()


def log(n: int) -> list[dict]:
    """The newest n calls of the call log, oldest first, as the MCP screen serves them."""
    r = httpx.get(f"{API}/api/screens/mcp/calls", params={"limit": n}, headers=headers("admin"))
    r.raise_for_status()
    return list(reversed(r.json()["calls"]))


def journal(case_id: str) -> list[dict]:
    r = httpx.get(f"{API}/api/journal", params={"case_id": case_id}, headers=headers("admin"))
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- the tools
def test_lists_the_ten_tools_with_their_schemas_and_approval_rules():
    async def go(c):
        return (await c.list_tools()).tools

    tools = with_client(headers("planner-a", "assembler"), go)
    assert [t.name for t in tools] == TOOL_IDS
    for t, ref in zip(tools, REF["tools"], strict=True):
        assert t.description == ref["desc"]
        assert t.input_schema["type"] == "object"
        assert set(t.input_schema["properties"]) == set(ref["input"])
        assert t.input_schema["required"] == [k for k, v in ref["input"].items() if v.get("req")]
        assert all(t.input_schema["properties"][k]["type"] == v["t"] for k, v in ref["input"].items())
        assert t.annotations.read_only_hint is (ref["rw"] == "read")
        assert t.meta["requiresHumanApproval"] is (ref["approval"] == "human approval required")
    assert {t.name for t in tools if t.meta["requiresHumanApproval"]} == {"request_approval", "send_instruction"}


def test_a_request_without_a_valid_token_is_401():
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    r = httpx.post(f"{API}/mcp", json=body)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert r.json() == {
        "ok": False,
        "error": {"code": "unauthenticated", "message": "Sign in first: send the account's bearer token."},
    }
    assert httpx.post(f"{API}/mcp", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401


# ---------------------------------------------------------------- reading, and what is refused
def test_an_agent_reads_evidence_for_its_tenant():
    a = call("planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1048"})
    assert a["ok"] is True and a["outcome"] == "ok" and a["agent"] == "assembler" and a["tenant"] == "Customer A"
    r = a["result"]
    assert r["case_id"] == "RT-1048" and r["tenant"] == "Customer A" and r["readiness"] == "10/10"
    assert len(r["evidence"]) == 10 and r["evidence"][0]["item"] == "Return record available"
    assert [s["n"] for s in a["trace"]][-2:] == ["Run tool", "Write audit record"]


def test_send_instruction_without_an_approval_reference_is_refused_by_the_hard_rule():
    before = journal("RT-1048")
    a = call("planner-a", "coordinator", "send_instruction", {"case_id": "RT-1048"})
    assert a["ok"] is False and a["outcome"] == "held for approval"
    assert a["error"]["code"] == "approval_required" and a["error"]["message"].startswith(NO_APPROVAL_REF)
    # a reference that is not the recorded approval is refused too, with the demo's message
    b = call("planner-a", "coordinator", "send_instruction", {"case_id": "RT-1048", "approval_ref": "APR-2026-10-0161"})
    assert b["error"]["code"] == "approval_required"
    assert (
        b["error"]["message"]
        == "No human approval APR-2026-10-0161 is recorded for RT-1048. Instructions cannot be sent without one."
    )
    assert journal("RT-1048") == before  # nothing ran


def test_a_tool_outside_the_agents_scope_is_denied():
    a = call("planner-a", "assembler", "request_missing_evidence", {"case_id": "RT-1051", "kind": "inspection"})
    assert a["ok"] is False and a["outcome"] == "denied · out of_scope"
    assert a["error"] == {
        "code": "out_of_scope",
        "message": "Evidence Assembler cannot call request_missing_evidence. Scopes: evidence:read.",
    }
    assert not [j for j in journal("RT-1051") if j["action"] == "evidence.request"]


def test_another_tenants_case_and_a_tenant_without_consent_are_denied():
    a = call("planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1001"})  # Customer B's case
    assert a["outcome"] == "denied · tenant boundary" and a["error"]["code"] == "tenant_boundary"
    assert "belongs to Customer B" in a["error"]["message"]
    # acting for a tenant the account has no consent for: refused on every call, even a call naming no case
    b = call("planner-a", "assembler", "get_model_validation", {"version": "v1.3"}, tenant="Customer B")
    assert b["error"]["code"] == "tenant_boundary" and "tenant consent is not on file" in b["error"]["message"]
    # an account that sees every tenant may act for any of them
    c = call("admin", "assembler", "get_case_evidence", {"case_id": "RT-1001"}, tenant="Customer B")
    assert c["ok"] is True


def test_the_account_behind_the_agent_keeps_its_own_permissions():
    # the Approver's account cannot submit decisions, so its coordinator cannot request an approval (the pipeline says so)
    a = call("approver", "coordinator", "request_approval", {"case_id": "RT-1049", "rationale": "Resale beats refurbishment"})
    assert a["outcome"] == "denied · out of_scope"
    assert a["error"] == {"code": "out_of_scope", "message": "The Approver view cannot submit decisions."}
    assert a["trace"][-1] == {"n": "Run tool", "ok": False, "detail": "decision.submit: out_of_scope"}
    assert action("planner-a", "case.get", {"case_id": "RT-1049"})["output"]["submitted"] is None


def test_an_unknown_agent_and_a_stopped_agent_are_denied():
    a = call("planner-a", None, "get_case_evidence", {"case_id": "RT-1048"})
    assert a["error"]["code"] == "out_of_scope" and "X-Agent" in a["error"]["message"]
    b = call("planner-a", "intruder", "get_case_evidence", {"case_id": "RT-1048"})
    assert b["error"]["code"] == "out_of_scope"
    from di.core.db import SessionLocal

    with SessionLocal() as s:  # the kill switch (Access → Agents); its action arrives with the Admin settings
        state.put(s, "access_settings", "agents_off", {"assembler": True})
        s.commit()
    try:
        c = call("planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1048"})
        assert c["error"] == {
            "code": "out_of_scope",
            "message": "Evidence Assembler is stopped by Admin, so it cannot prepare anything.",
        }
    finally:
        with SessionLocal() as s:
            state.put(s, "access_settings", "agents_off", {})
            s.commit()


# ---------------------------------------------------------------- the approval flow
def test_request_approval_is_held_until_a_person_approves_then_the_instruction_goes():
    # the agent submits (an extra "confirmed" argument is not a declared input and is dropped)
    a = call(
        "planner-a", "coordinator", "request_approval",
        {"case_id": "RT-1048", "rationale": "Redeploy to Site 3 as recommended", "confirmed": True},
    )  # fmt: skip
    assert a["ok"] is False and a["outcome"] == "held for approval" and a["error"]["code"] == "held"
    assert re.fullmatch(r"AQ-[0-9A-F]{6}", a["error"]["approval_request"])
    assert action("planner-a", "case.get", {"case_id": "RT-1048"})["output"]["submitted"] == "Planner · Customer A"
    # still nothing to send
    b = call("planner-a", "coordinator", "send_instruction", {"case_id": "RT-1048", "approval_ref": "APR-2026-10-3161"})
    assert b["error"]["code"] == "approval_required"
    # the person approves in the approval card
    ap = action(
        "approver", "decision.approve",
        {"case_id": "RT-1048", "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True},
    )  # fmt: skip
    assert ap["ok"] is True
    ref = ap["output"]["ref"]
    c = call("planner-a", "coordinator", "send_instruction", {"case_id": "RT-1048", "approval_ref": ref})
    assert c["ok"] is True and c["result"]["approval_ref"] == ref and c["result"]["deduplicated"] is True
    again = call("planner-a", "coordinator", "send_instruction", {"case_id": "RT-1048", "approval_ref": ref})
    assert again["ok"] is True and again["result"] == c["result"]  # a retry is idempotent
    # the journal: the agent prepared the submission and the resend; the person approved
    j = {e["action"]: e for e in journal("RT-1048")}
    assert j["decision.submit"]["preparer"] == "coordinator" and j["decision.submit"]["actor"] == "planner-a"
    assert j["decision.approve"]["preparer"] is None and j["decision.approve"]["actor"] == "approver"
    assert j["instruction.resend"]["preparer"] == "coordinator"


# ---------------------------------------------------------------- the call log
def test_every_call_allowed_held_and_denied_is_in_the_call_log():
    made = [
        call("planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1049"}),
        call("planner-a", "coordinator", "request_approval", {"case_id": "RT-1049", "rationale": "Resale beats refurbishment"}),
        call("planner-a", "assembler", "send_instruction", {"case_id": "RT-1049", "approval_ref": "APR-1"}),
        call("planner-a", "assembler", "get_case_evidence", {"case_id": "RT-1001"}),
        call("planner-b", "coordinator", "send_instruction", {"case_id": "RT-1001"}),
    ]
    entries = log(len(made))
    assert [(e["agent"], e["tool"], e["caseId"], e["tenant"], e["outcome"], e["account"]) for e in entries] == [
        ("Evidence Assembler", "get_case_evidence", "RT-1049", "Customer A", "ok", "planner-a"),
        ("Handoff Coordinator", "request_approval", "RT-1049", "Customer A", "held for approval", "planner-a"),
        ("Evidence Assembler", "send_instruction", "—", "Customer A", "denied · out of_scope", "planner-a"),
        ("Evidence Assembler", "get_case_evidence", "RT-1001", "Customer A", "denied · tenant boundary", "planner-a"),
        ("Handoff Coordinator", "send_instruction", "RT-1001", "Customer B", "held for approval", "planner-b"),
    ]
    assert [e["code"] for e in entries] == [None, "held", "out_of_scope", "tenant_boundary", "approval_required"]
    assert [e["lat"] for e in entries] == [a["ms"] for a in made]
    assert all(e["step"] == next(t["step"][0] for t in REF["tools"] if t["id"] == e["tool"]) for e in entries)
    r = httpx.get(f"{API}/api/screens/mcp/calls", params={"filter": "issues", "limit": 4}, headers=headers("admin")).json()
    assert [c["tool"] for c in r["calls"]] == ["send_instruction", "get_case_evidence", "send_instruction", "request_approval"]
    assert r["held"][0]["tool"] == "send_instruction" and r["held"][0]["caseId"] == "RT-1001"


# ---------------------------------------------------------------- parity with the demo's tool layer
# Intended differences from the demo, each with the reason:
# - send_instruction with no approval_ref: the demo answers with its schema error (Missing required field
#   "approval_ref"); the server names the hard rule (nothing is sent without an approval reference) before the
#   schema check. Compared as that refusal.
# - request_missing_evidence's request_ref: the demo's playground numbers its requests from its own counter (WO-94000 …);
#   the server's is the one evidence.request creates (WO-6…), which the case and the event log carry. Compared by
#   prefix.
# - the log entry's ts is the workspace clock (the demo's is its pinned as-of time) and lat is the call's measured
#   time (the demo's is a sum of random draws): compared as an ISO time and a number. A case_id that is not a string
#   is logged as "—" (the demo logs the raw value; the MCP screen keys its links on case ids).
HARD_RULE_REFUSAL = {("instructions", 0)}


def _expected(name: str, k: int, g: dict) -> dict:
    """The golden call as the server should answer it."""
    exp = {"ok": g["ok"], "outcome": g["outcome"], "trace": g["trace"]}
    exp["result" if g["ok"] else "error"] = g["result"] if g["ok"] else g["error"]
    if (name, k) in HARD_RULE_REFUSAL:
        exp["outcome"] = "held for approval"
        exp["error"] = {
            "code": "approval_required",
            "message": f"{NO_APPROVAL_REF} Approve the case in Product first, then pass its reference as approval_ref.",
        }
        exp["trace"] = [*g["trace"][:2], {"n": "Verify approval reference", "ok": False, "detail": "No approval reference"}]
    return exp


def _relative(a: dict, g: dict) -> dict:
    """The answer with the fields that cannot match made comparable (see above)."""
    a = {k: a[k] for k in ("ok", "outcome", "trace", "result", "error") if k in a}
    if g["tool"] == "request_missing_evidence" and a["ok"]:
        assert a["result"]["request_ref"].startswith("WO-") and g["result"]["request_ref"].startswith("WO-")
        a["result"] = {**a["result"], "request_ref": g["result"]["request_ref"]}
    return a


@pytest.mark.parametrize("name", list(G))
def test_parity_with_the_demos_tool_layer(name: str):
    starting.reset()
    calls = []
    for k, g in enumerate(G[name]):
        if "approve" in g:  # the person's approval between two tool calls
            r = action(g["as"], "decision.approve", g["input"])
            assert starting.strict({"ok": r["ok"], "output": r.get("output")}) == starting.strict(g["result"]), (name, k)
            continue
        a = call(g["account"], g["agent"], g["tool"], g["input"], tenant=g["tenant"])
        exp = _expected(name, k, g)
        assert starting.strict(_relative(a, g)) == starting.strict(exp), (name, k, g["tool"], g["input"])
        assert a["case_id"] == g["caseId"] or (a["case_id"] is None and g["caseId"] is None), (name, k)
        calls.append(g)
    for e, g in zip(log(len(calls)), calls, strict=True):
        want = dict(g["log"])
        want["caseId"] = want["caseId"] if isinstance(want["caseId"], str) else "—"
        if (name, G[name].index(g)) in HARD_RULE_REFUSAL:
            want["outcome"] = "held for approval"
        assert {k: e[k] for k in ("agent", "tool", "caseId", "tenant", "outcome", "step")} == {
            k: want[k] for k in ("agent", "tool", "caseId", "tenant", "outcome", "step")
        }, (name, g["tool"], g["input"])
        assert isinstance(e["lat"], int) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", e["ts"])
        assert e["account"] == g["account"]
