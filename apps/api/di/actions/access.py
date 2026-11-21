"""Access actions (B12): access.requestTenant, access.decideRequest, access.setDelegation, the identity actions
(syncDirectory, mapIdentity, removeUser, setRoleSource, setOutOfOffice, clearOutOfOffice), mcp.propose, and Admin's
agent-first settings (access.setAutonomy, setLimit, setSelfApprove, setRunLimits, agent.setEnabled; B17).

Ports of the demo's handlers (index.html, `/* ---- access: requests, delegations, identity ---- */`). The pipeline has
already validated the input and checked the permission; the guards here are the demo's state checks, in its order.

Where the state lives:
- requests (S.reqs): the workspace collection "requests" (di.reads.common), newest first;
- delegations (S.deleg) and tenant grants (S.grants): the delegation and tenant_grant tables (B7);
- the accounts as mapped (ACCOUNTS), the directory users (S.idp.users) and the directory settings (S.idp.src,
  lastSync, ooo): the collections "accounts", "idp_users" and "access_settings" (di.policy);
- MCP servers Circularity consumes (CLIENT_SERVERS): the collection "mcp_servers", which an approved proposal joins.
Every change is logged to the event log as the demo's rbLog does.
"""

import math
from typing import Any

from sqlalchemy import text

from di import golden, policy, state
from di.actions.decisions import NOW, rb_log
from di.actions.pipeline import CallContext
from di.actions.registry import ACTIONS, ActionError, guard, implement
from di.reads import constants as C
from di.reads.common import REQ_SCOPE, REQ_SEQ_START, can, money, requests

# The demo's DELEG (di.reads.constants, shared with the Access screen): the kinds of request Admin may let the
# Approver decide, here by key -> label.
DELEG = {d["k"]: d["label"] for d in C.DELEG}

# The demo's CLIENT_SERVERS at the start: the enterprise MCP servers Circularity consumes, plus the one approved from
# REQ-302 (the demo adds it at load).
STARTING_MCP_SERVERS: list[dict] = [
    {"id": "erp-mcp", "name": "ERP MCP server", "owner": "LedgerOne", "status": "connected",
     "tools": ["inventory.get", "purchase_plan.get", "cost.get", "reservation.create"], "used": "Steps 1, 6"},
    {"id": "eam-mcp", "name": "EAM MCP server", "owner": "AssetCore", "status": "connected",
     "tools": ["asset.get", "work_order.create", "work_order.status", "failure.list"], "used": "Steps 1, 6–9"},
    {"id": "crm-mcp", "name": "CRM MCP server", "owner": "LeaseDesk", "status": "connected",
     "tools": ["opportunity.list", "contract.get", "sale_task.create"], "used": "Steps 1, 6"},
    {"id": "mkt-mcp", "name": "Market data MCP server", "owner": "DealerBridge", "status": "token expired",
     "tools": ["comparables.search", "offers.list"], "used": "Step 3"},
    {"id": "plm-mcp", "name": "PLM MCP server", "owner": "BOMGraph", "status": "not available", "tools": ["—"],
     "used": "No MCP server; adapter polls the REST API"},
    {"id": "prop-REQ-302", "name": "Supplier catalogue MCP server", "owner": "PartsHub", "status": "approved",
     "tools": ["part.search", "part.price"], "used": "Approved from REQ-302 · not yet connected"},
]  # fmt: skip
state.register("mcp_servers", lambda: [(s["id"], s) for s in STARTING_MCP_SERVERS])


def _key(action: str, i: dict, ctx: CallContext) -> str:
    """The key the demo's rbLog hashes (ctx.key): the idempotency key when the action has one."""
    a = ACTIONS[action]
    return f"{action}:{a.idem(i, ctx)}" if a.idem else action


def _by(ctx: CallContext) -> str:
    return ctx.actor.person.label


def _new_request(ctx: CallContext, r: dict) -> dict:
    s = ctx.session
    n = state.next_number(s, "requests", "REQ-", REQ_SEQ_START)
    r = {"id": f"REQ-{n}", "status": "pending", "by": _by(ctx), "byId": ctx.actor.id, "at": NOW, **r}
    return state.add(s, "requests", r["id"], r)


def _request(ctx: CallContext, req_id: str, for_update: bool = False) -> dict | None:
    return state.get(ctx.session, "requests", req_id, for_update=for_update)


def _can_decide(ctx: CallContext, r: dict) -> bool:
    """The demo's canDecide: a pending request of a kind this account may decide."""
    return r["status"] == "pending" and can(ctx, "approve." + REQ_SCOPE[r["kind"]])


# ---------------------------------------------------------------- tenant access and MCP proposals
@guard("access.requestTenant")
def request_tenant_guard(i: dict[str, Any], ctx: CallContext):
    if i["tenant"] not in policy.tenants():
        return "not_found", "Unknown tenant."
    mine = (r for r in requests(ctx.session) if r["kind"] == "tenant" and r["status"] == "pending" and r["byId"] == ctx.actor.id)
    if any(r["tenant"] == i["tenant"] for r in mine):
        return "duplicate", f"A request for {i['tenant']} is already waiting"
    return None


@implement("access.requestTenant")
def request_tenant(i: dict[str, Any], ctx: CallContext):
    r = _new_request(ctx, {"kind": "tenant", "tenant": i["tenant"], "reason": i["reason"]})
    rb_log(ctx, "access.requested", f"{r['by']} → {i['tenant']} · {i['reason']}", _key("access.requestTenant", i, ctx))
    return {"id": r["id"]}


@guard("mcp.propose")
def propose_guard(i: dict[str, Any], ctx: CallContext):
    if not i["tools"]:
        return "validation_error", "List at least one tool."
    name = i["name"].lower()
    if any(
        r["kind"] == "mcp" and r["status"] == "pending" and r["server"]["name"].lower() == name for r in requests(ctx.session)
    ):
        return "duplicate", "A proposal with this name is already waiting"
    return None


@implement("mcp.propose")
def propose(i: dict[str, Any], ctx: CallContext):
    server = {k: i[k] for k in ("name", "owner", "purpose", "access", "data")} | {"tools": list(i["tools"])}
    r = _new_request(ctx, {"kind": "mcp", "server": server})
    rb_log(ctx, "mcp.proposal.submitted", f"{server['name']} · {server['access']}", _key("mcp.propose", i, ctx))
    return {"id": r["id"]}


@guard("access.decideRequest")
def decide_guard(i: dict[str, Any], ctx: CallContext):
    r = _request(ctx, i["id"])
    if r is None:
        return "not_found", f"No request {i['id']}."
    if not _can_decide(ctx, r):
        return "out_of_scope", "This request is not yours to decide."
    if i["decision"] == "decline" and len((i.get("note") or "").strip()) < 5:
        return "validation_error", "Add a short reason so the requester knows what to change."
    return None


@implement("access.decideRequest", idem=lambda i, ctx: f"req:{i['id']}")  # noqa: ARG005 - idem keys take (input, ctx)
def decide_request(i: dict[str, Any], ctx: CallContext):
    r, note = state.need(ctx.session, "requests", i["id"], for_update=True), (i.get("note") or "").strip()
    r |= {"status": "approved" if i["decision"] == "approve" else "declined", "decidedBy": _by(ctx), "decidedAt": NOW}
    r["note"] = note
    state.put(ctx.session, "requests", r["id"], r)
    approved = r["status"] == "approved"
    if r["kind"] == "tenant" and approved:
        ctx.session.execute(
            text(
                "INSERT INTO tenant_grant (account_id, tenant, granted_by) VALUES (:a, :t, :by) "
                "ON CONFLICT (account_id, tenant) DO NOTHING"
            ),
            {"a": r["byId"], "t": r["tenant"], "by": ctx.actor.id},
        )
    if r["kind"] == "mcp" and approved:
        v = r["server"]
        sid = "prop-" + r["id"]
        state.put(
            ctx.session,
            "mcp_servers",
            sid,
            {"id": sid, "name": v["name"], "owner": v["owner"], "status": "approved", "tools": list(v["tools"]),
             "used": f"Approved from {r['id']} · not yet connected"},
        )  # fmt: skip
    if r["kind"] == "tenant":
        type_, what = "access." + ("granted" if approved else "declined"), f"{r['by']} → {r['tenant']}"
    else:
        type_, what = "mcp.proposal." + r["status"], r["server"]["name"]
    rb_log(ctx, type_, what + (f" · {note}" if note else ""), _key("access.decideRequest", i, ctx))
    return {"id": r["id"], "status": r["status"]}


# ---------------------------------------------------------------- the Approver's delegations
@guard("access.setDelegation")
def delegation_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - guards take (input, ctx)
    return None if i["k"] in DELEG else ("not_found", "Unknown delegation.")


@implement("access.setDelegation")
def set_delegation(i: dict[str, Any], ctx: CallContext):
    on = bool(i["on"])
    ctx.session.execute(
        text("UPDATE delegation SET enabled = :e, updated_by = :by, updated_at = now() WHERE scope = :s"),
        {"e": on, "by": ctx.actor.id, "s": i["k"]},
    )
    label = DELEG[i["k"]].lower().replace("mcp", "MCP", 1)  # the demo's dlab
    note = "Approver " + ("may now decide " if on else "may no longer decide ") + label
    rb_log(ctx, "delegation.changed", note, _key("access.setDelegation", i, ctx))
    return {"k": i["k"], "on": on}


# ---------------------------------------------------------------- identity: directory, role mapping, out of office
def _idp(ctx: CallContext, for_update: bool = False) -> dict:
    return state.need(ctx.session, "access_settings", "idp", for_update=for_update)


def _idp_users(ctx: CallContext) -> list[dict]:
    return state.items(ctx.session, "idp_users")


@implement("access.syncDirectory")
def sync_directory(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - handlers take (input, ctx)
    idp = _idp(ctx, for_update=True) | {"lastSync": NOW}
    state.put(ctx.session, "access_settings", "idp", idp)
    n = len(_idp_users(ctx))
    rb_log(ctx, "directory.synced", f"Directory sync: {n} users, {len(policy.IDP_GROUPS)} mappings", "access.syncDirectory")
    return {"users": n}


@guard("access.mapIdentity")
def map_guard(i: dict[str, Any], ctx: CallContext):
    a = policy.account(i["acct"], ctx.actor.ctx)
    if a is None:
        return "not_found", "Unknown account."
    if a.role == "Admin":
        return "conflict", "The Admin mapping cannot be changed here."
    if i["field"] == "role" and i.get("value") not in policy.idp_roles():
        return "validation_error", "Unknown role."
    return None


@implement("access.mapIdentity")
def map_identity(i: dict[str, Any], ctx: CallContext):
    """Changes the account itself: its role, tenant, site or warehouse and label, which every rule and read uses from
    the next request on (the signed-in account is looked up by id on each request; see di.auth.principal)."""
    found = policy.account(i["acct"], ctx.actor.ctx)
    if found is None:  # not reached: map_guard refused an unknown account
        raise ActionError("not_found", "Unknown account.")
    a = policy.map_identity(found, i["field"], i.get("value"))
    state.put(ctx.session, "accounts", a.id, dict(a.__dict__))
    where = a.warehouse or a.site
    note = f"{policy.IDP_GROUPS.get(a.id)} → {a.role}" + (f" · {where}" if where else "")
    rb_log(ctx, "identity.mapping.changed", note, "access.mapIdentity")
    return {"acct": a.id, "label": a.label}


@guard("access.removeUser")
def remove_user_guard(i: dict[str, Any], ctx: CallContext):
    return None if state.get(ctx.session, "idp_users", i["id"]) else ("not_found", "No such user.")


@implement("access.removeUser", idem=lambda i, ctx: f"idp-rm:{i['id']}")  # noqa: ARG005 - idem keys take (input, ctx)
def remove_user(i: dict[str, Any], ctx: CallContext):
    u = state.need(ctx.session, "idp_users", i["id"])
    state.delete(ctx.session, "idp_users", i["id"])
    note = f"{u['email']} removed in the directory; access removed at the provisioning sync"
    rb_log(ctx, "user.deprovisioned", note, _key("access.removeUser", i, ctx))
    return {"email": u["email"]}


@implement("access.setRoleSource")
def set_role_source(i: dict[str, Any], ctx: CallContext):
    src = "groups" if i["src"] == "groups" else "approles"
    state.put(ctx.session, "access_settings", "idp", _idp(ctx, for_update=True) | {"src": src})
    rb_log(ctx, "identity.role_source", i["src"], "access.setRoleSource")
    return {"src": src}


@guard("access.setOutOfOffice")
def ooo_guard(i: dict[str, Any], ctx: CallContext):
    u = state.get(ctx.session, "idp_users", i["to"])
    if u is None or policy.idp_role_of(u, ctx.actor.ctx) != "Approver":
        return "validation_error", "Pick a delegate who already holds the Approver role."
    if i["until"] < i["from"]:  # ISO dates compare as text, as in the demo
        return "validation_error", "The end date must be on or after the start date."
    return None


@implement("access.setOutOfOffice")
def set_out_of_office(i: dict[str, Any], ctx: CallContext):
    u = state.need(ctx.session, "idp_users", i["to"])
    idp = _idp(ctx, for_update=True)
    idp["ooo"].append({"email": u["email"], "from": i["from"], "until": i["until"]})
    state.put(ctx.session, "access_settings", "idp", idp)
    note = f"Approver → {u['email']} · {i['from']} to {i['until']}"
    rb_log(ctx, "delegation.out_of_office", note, "access.setOutOfOffice")
    return {"email": u["email"]}


def _splice_index(index: float, n: int) -> int:
    """Array.prototype.splice's start: truncated toward zero, counted from the end when negative."""
    k = math.trunc(index)
    return max(n + k, 0) if k < 0 else k


@implement("access.clearOutOfOffice")
def clear_out_of_office(i: dict[str, Any], ctx: CallContext):
    idp = _idp(ctx, for_update=True)
    k = _splice_index(i["index"], len(idp["ooo"]))
    d = idp["ooo"].pop(k) if k < len(idp["ooo"]) else None
    if d:
        state.put(ctx.session, "access_settings", "idp", idp)
        rb_log(ctx, "delegation.out_of_office.removed", d["email"], "access.clearOutOfOffice")
    return {"removed": d is not None}


# ---------------------------------------------------------------- agent-first settings (AF.cfg)
# Admin's settings in Access: the approval limits and self-approval (item "approval", which di.auth.load_context
# reads into every rule: decision.approve and decision.override check them), autonomy per role and action type
# ("autonomy"), stopped agents ("agents_off", which the MCP server refuses) and run limits ("run_limits"). All in the
# collection "access_settings"; di.screens.access reads them back.
# The autonomy levels and action types are di.reads.constants' (shared with the Access screen), here keyed by `k`.
LEVELS = {x["k"]: x["label"] for x in C.LEVELS}
LEVEL_RANK = C.LEVEL_RANK  # the demo's AF_LV_RANK
AUTO_TYPES = {t["k"]: t for t in C.AUTO_TYPES}
AGENT_NAMES = {a["id"]: a["name"] for a in golden.load("tools")["agents"]}


def _settings(ctx: CallContext, item: str, default):
    return state.get(ctx.session, "access_settings", item, for_update=True) or default


@guard("access.setAutonomy")
def autonomy_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - guards take (input, ctx)
    t = AUTO_TYPES.get(i["type"])
    if i["role"] not in policy.roles():
        return "not_found", "Unknown role."
    if t is None:
        return "not_found", "Unknown action type."
    if i["level"] not in LEVEL_RANK:
        return "validation_error", "Unknown level."
    if LEVEL_RANK[i["level"]] > LEVEL_RANK[t["max"]]:
        return "conflict", f"{t['t']} is capped at {LEVELS[t['max']]} by its risk tier."
    return None


@implement("access.setAutonomy")
def set_autonomy(i: dict[str, Any], ctx: CallContext):
    auto = _settings(ctx, "autonomy", {})
    auto.setdefault(i["role"], {})[i["type"]] = i["level"]
    state.put(ctx.session, "access_settings", "autonomy", auto)
    note = f"{i['role']} · {AUTO_TYPES[i['type']]['t']} → {LEVELS[i['level']]}"
    rb_log(ctx, "agent.autonomy.changed", note, "access.setAutonomy")
    return {"role": i["role"], "type": i["type"], "level": i["level"]}


@guard("access.setLimit")
def limit_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - guards take (input, ctx)
    if i["role"] not in policy.roles():
        return "not_found", "Unknown role."
    if i.get("amount") is not None and i["amount"] < 0:
        return "validation_error", "A limit cannot be negative."
    return None


@implement("access.setLimit")
def set_limit(i: dict[str, Any], ctx: CallContext):
    amount = i.get("amount")
    approval = _settings(ctx, "approval", {"limits": dict(policy.STARTING_LIMITS), "self": False})
    approval.setdefault("limits", dict(policy.STARTING_LIMITS))[i["role"]] = amount  # None: the demo's Infinity
    state.put(ctx.session, "access_settings", "approval", approval)
    rb_log(ctx, "approval.limit.changed", f"{i['role']} → {'unlimited' if amount is None else money(amount)}", "access.setLimit")
    return {"role": i["role"], "limit": amount}


@implement("access.setSelfApprove")
def set_self_approve(i: dict[str, Any], ctx: CallContext):
    on = bool(i["on"])
    approval = _settings(ctx, "approval", {"limits": dict(policy.STARTING_LIMITS), "self": False}) | {"self": on}
    state.put(ctx.session, "access_settings", "approval", approval)
    note = "Self-approval allowed within the limit" if on else "Self-approval not allowed"
    rb_log(ctx, "approval.self.changed", note, "access.setSelfApprove")
    return {"on": on}


@guard("agent.setEnabled")
def agent_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - guards take (input, ctx)
    return None if i["id"] in AGENT_NAMES else ("not_found", "Unknown agent.")


@implement("agent.setEnabled")
def set_agent_enabled(i: dict[str, Any], ctx: CallContext):
    on = bool(i["on"])
    off = _settings(ctx, "agents_off", {})
    if on:
        off.pop(i["id"], None)
    else:
        off[i["id"]] = True
    state.put(ctx.session, "access_settings", "agents_off", off)
    rb_log(ctx, "agent." + ("started" if on else "stopped"), AGENT_NAMES[i["id"]], "agent.setEnabled")
    return {"id": i["id"], "on": on}


@guard("access.setRunLimits")
def run_limits_guard(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - guards take (input, ctx)
    if i["actions"] < 1 or i["bulk"] < 1 or i["actions"] > 500 or i["bulk"] > 1000:
        return "validation_error", "Use 1–500 actions and 1–1,000 items."
    return None


@implement("access.setRunLimits")
def set_run_limits(i: dict[str, Any], ctx: CallContext):
    lim = {"actions": i["actions"], "bulk": i["bulk"]}
    state.put(ctx.session, "access_settings", "run_limits", lim)
    note = f"{i['actions']} actions per run · {i['bulk']} items per bulk plan"
    rb_log(ctx, "agent.limits.changed", note, "access.setRunLimits")
    return lim
