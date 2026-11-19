"""Access actions (B12): access.requestTenant, access.decideRequest, access.setDelegation, the identity actions
(syncDirectory, mapIdentity, removeUser, setRoleSource, setOutOfOffice, clearOutOfOffice) and mcp.propose.

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

from sqlalchemy import text

from di import policy, state
from di.actions.decisions import NOW, rb_log
from di.actions.registry import ACTIONS, guard, implement
from di.reads.common import REQ_SCOPE, REQ_SEQ_START, can, requests

# The demo's DELEG: the kinds of request Admin may let the Approver decide (key, label).
DELEG = {"decisions": "Decisions and overrides", "mcp": "MCP server proposals", "tenantAccess": "Tenant access"}

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


def _key(action: str, i: dict, ctx) -> str:
    """The key the demo's rbLog hashes (ctx.key): the idempotency key when the action has one."""
    a = ACTIONS[action]
    return f"{action}:{a.idem(i, ctx)}" if a.idem else action


def _by(ctx) -> str:
    return ctx.actor.account.label


def _new_request(ctx, r: dict) -> dict:
    s = ctx.session
    n = state.next_number(s, "requests", "REQ-", REQ_SEQ_START)
    r = {"id": f"REQ-{n}", "status": "pending", "by": _by(ctx), "byId": ctx.actor.id, "at": NOW, **r}
    return state.add(s, "requests", r["id"], r)


def _request(ctx, req_id: str, for_update: bool = False) -> dict | None:
    return state.get(ctx.session, "requests", req_id, for_update=for_update)


def _can_decide(ctx, r: dict) -> bool:
    """The demo's canDecide: a pending request of a kind this account may decide."""
    return r["status"] == "pending" and can(ctx, "approve." + REQ_SCOPE[r["kind"]])


# ---------------------------------------------------------------- tenant access and MCP proposals
@guard("access.requestTenant")
def request_tenant_guard(i, ctx):
    if i["tenant"] not in policy.tenants():
        return "not_found", "Unknown tenant."
    mine = (r for r in requests(ctx.session) if r["kind"] == "tenant" and r["status"] == "pending" and r["byId"] == ctx.actor.id)
    if any(r["tenant"] == i["tenant"] for r in mine):
        return "duplicate", f"A request for {i['tenant']} is already waiting"
    return None


@implement("access.requestTenant")
def request_tenant(i, ctx):
    r = _new_request(ctx, {"kind": "tenant", "tenant": i["tenant"], "reason": i["reason"]})
    rb_log(ctx, "access.requested", f"{r['by']} → {i['tenant']} · {i['reason']}", _key("access.requestTenant", i, ctx))
    return {"id": r["id"]}


@guard("mcp.propose")
def propose_guard(i, ctx):
    if not i["tools"]:
        return "validation_error", "List at least one tool."
    name = i["name"].lower()
    if any(
        r["kind"] == "mcp" and r["status"] == "pending" and r["server"]["name"].lower() == name for r in requests(ctx.session)
    ):
        return "duplicate", "A proposal with this name is already waiting"
    return None


@implement("mcp.propose")
def propose(i, ctx):
    server = {k: i[k] for k in ("name", "owner", "purpose", "access", "data")} | {"tools": list(i["tools"])}
    r = _new_request(ctx, {"kind": "mcp", "server": server})
    rb_log(ctx, "mcp.proposal.submitted", f"{server['name']} · {server['access']}", _key("mcp.propose", i, ctx))
    return {"id": r["id"]}


@guard("access.decideRequest")
def decide_guard(i, ctx):
    r = _request(ctx, i["id"])
    if r is None:
        return "not_found", f"No request {i['id']}."
    if not _can_decide(ctx, r):
        return "out_of_scope", "This request is not yours to decide."
    if i["decision"] == "decline" and len((i.get("note") or "").strip()) < 5:
        return "validation_error", "Add a short reason so the requester knows what to change."
    return None


@implement("access.decideRequest", idem=lambda i, ctx: f"req:{i['id']}")
def decide_request(i, ctx):
    r, note = _request(ctx, i["id"], for_update=True), (i.get("note") or "").strip()
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
def delegation_guard(i, ctx):
    return None if i["k"] in DELEG else ("not_found", "Unknown delegation.")


@implement("access.setDelegation")
def set_delegation(i, ctx):
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
def _idp(ctx, for_update: bool = False) -> dict:
    return state.get(ctx.session, "access_settings", "idp", for_update=for_update)


def _idp_users(ctx) -> list[dict]:
    return state.items(ctx.session, "idp_users")


@implement("access.syncDirectory")
def sync_directory(i, ctx):
    idp = _idp(ctx, for_update=True) | {"lastSync": NOW}
    state.put(ctx.session, "access_settings", "idp", idp)
    n = len(_idp_users(ctx))
    rb_log(ctx, "directory.synced", f"Directory sync: {n} users, {len(policy.IDP_GROUPS)} mappings", "access.syncDirectory")
    return {"users": n}


@guard("access.mapIdentity")
def map_guard(i, ctx):
    a = policy.account(i["acct"], ctx.actor.ctx)
    if a is None:
        return "not_found", "Unknown account."
    if a.role == "Admin":
        return "conflict", "The Admin mapping cannot be changed here."
    if i["field"] == "role" and i.get("value") not in policy.idp_roles():
        return "validation_error", "Unknown role."
    return None


@implement("access.mapIdentity")
def map_identity(i, ctx):
    """Changes the account itself: its role, tenant, site or warehouse and label, which every rule and read uses from
    the next request on (the signed-in account is looked up by id on each request; see di.auth.principal)."""
    a = policy.map_identity(policy.account(i["acct"], ctx.actor.ctx), i["field"], i.get("value"))
    state.put(ctx.session, "accounts", a.id, dict(a.__dict__))
    where = a.warehouse or a.site
    note = f"{policy.IDP_GROUPS.get(a.id)} → {a.role}" + (f" · {where}" if where else "")
    rb_log(ctx, "identity.mapping.changed", note, "access.mapIdentity")
    return {"acct": a.id, "label": a.label}


@guard("access.removeUser")
def remove_user_guard(i, ctx):
    return None if state.get(ctx.session, "idp_users", i["id"]) else ("not_found", "No such user.")


@implement("access.removeUser", idem=lambda i, ctx: f"idp-rm:{i['id']}")
def remove_user(i, ctx):
    u = state.get(ctx.session, "idp_users", i["id"])
    state.delete(ctx.session, "idp_users", i["id"])
    note = f"{u['email']} removed in the directory; access removed at the provisioning sync"
    rb_log(ctx, "user.deprovisioned", note, _key("access.removeUser", i, ctx))
    return {"email": u["email"]}


@implement("access.setRoleSource")
def set_role_source(i, ctx):
    src = "groups" if i["src"] == "groups" else "approles"
    state.put(ctx.session, "access_settings", "idp", _idp(ctx, for_update=True) | {"src": src})
    rb_log(ctx, "identity.role_source", i["src"], "access.setRoleSource")
    return {"src": src}


@guard("access.setOutOfOffice")
def ooo_guard(i, ctx):
    u = state.get(ctx.session, "idp_users", i["to"])
    if u is None or policy.idp_role_of(u, ctx.actor.ctx) != "Approver":
        return "validation_error", "Pick a delegate who already holds the Approver role."
    if i["until"] < i["from"]:  # ISO dates compare as text, as in the demo
        return "validation_error", "The end date must be on or after the start date."
    return None


@implement("access.setOutOfOffice")
def set_out_of_office(i, ctx):
    u = state.get(ctx.session, "idp_users", i["to"])
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
def clear_out_of_office(i, ctx):
    idp = _idp(ctx, for_update=True)
    k = _splice_index(i["index"], len(idp["ooo"]))
    d = idp["ooo"].pop(k) if k < len(idp["ooo"]) else None
    if d:
        state.put(ctx.session, "access_settings", "idp", idp)
        rb_log(ctx, "delegation.out_of_office.removed", d["email"], "access.clearOutOfOffice")
    return {"removed": d is not None}
