"""Agent registry actions (plan 8, MVP-11.3): Admin registers and edits the agents that may call Circularity.

The demo has a fixed list of nine agents, so these are declared here, beside the catalog's actions. They need
`manageAgents` (Admin, di.core.policy.EXTRA_PERMS), are commits and are journaled. Agents never run them
(di.mcp.policy.FORBIDDEN_ACTIONS covers "agent.").

    agent.register  commit  {id, name, kind?, org_scope?, tools?, autonomy?}   a new agent (kind external, autonomy
                                                                                propose unless given)
    agent.update    commit  {id, name?, org_scope?, tools?, autonomy?, enabled?}   change what is sent

agent.setEnabled (di.services.actions.access, the demo's kill switch) writes the row too, through `set_enabled`.
`tools` are MCP tool ids (di.mcp.tools.TOOLS) or action ids; `org_scope` are org unit ids (empty: every org).
"""

import re
from typing import Any

from sqlalchemy import text

from di.core import policy, state
from di.repositories.constants import TOOLS_BY_ID
from di.services.actions.decisions import rb_log
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.agents import registry

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
KINDS = ("internal", "external")
AUTONOMY = ("read", "propose", "act")
_PERM = "manageAgents"
_OPT = {"req": False}
_FIELDS = {
    "name": {**_OPT, "t": "string"},
    "org_scope": {**_OPT, "t": "array"},
    "tools": {**_OPT, "t": "array"},
    "autonomy": {**_OPT, "t": "string"},
}


def _declare(action_id: str, title: str, verb: str, desc: str, inp: dict[str, dict[str, Any]]) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk="commit", perm=_PERM, scope="none", input=inp, verb=verb),
    )


_declare(
    "agent.register", "Register an agent", "register agents",
    "Add an agent that may call Circularity, with the tools it may use, the orgs it may see and how far it may go.",
    {"id": {"req": True, "t": "string"}, **_FIELDS, "name": {"req": True, "t": "string"}, "kind": {**_OPT, "t": "string"}},
)  # fmt: skip
_declare(
    "agent.update", "Change an agent", "change agents",
    "Change an agent's name, tools, org scope or autonomy, or stop and start it.",
    {"id": {"req": True, "t": "string"}, **_FIELDS, "enabled": {**_OPT, "t": "boolean"}},
)  # fmt: skip


def _fields_problem(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i.get("autonomy") is not None and i["autonomy"] not in AUTONOMY:
        return "validation_error", "Autonomy is read, propose or act."
    from di.mcp.tools import MODELER_TOOLS  # plan 8 MVP-5.5: the MCP table's tools beyond the demo's ten

    known = set(TOOLS_BY_ID) | set(MODELER_TOOLS) | set(ACTIONS)
    if bad := [t for t in i.get("tools") or [] if t not in known]:
        return "validation_error", f"Unknown tools: {', '.join(map(str, bad))}."
    units = policy.org_units(ctx.actor.ctx)
    if bad := [u for u in i.get("org_scope") or [] if u not in units]:
        return "validation_error", f"Unknown org units: {', '.join(map(str, bad))}."
    return None


@guard("agent.register")
def register_guard(i: dict[str, Any], ctx: CallContext):
    if not ID_RE.match(i["id"]):
        return "validation_error", "An agent id is 2-64 lower-case letters, digits, dots, dashes or underscores."
    if i.get("kind") is not None and i["kind"] not in KINDS:
        return "validation_error", "Kind is internal or external."
    if registry.get(ctx.session, i["id"]) is not None:
        return "duplicate", f"Agent {i['id']} is already registered"
    return _fields_problem(i, ctx)


@implement("agent.register")
def register(i: dict[str, Any], ctx: CallContext):
    ctx.session.execute(
        text(
            "INSERT INTO agent_identity (id, name, kind, org_scope, tools, autonomy, created_by) "
            "VALUES (:id, :name, :kind, :scope, :tools, :auto, :by)"
        ),
        {
            "id": i["id"], "name": i["name"], "kind": i.get("kind") or "external", "scope": list(i.get("org_scope") or []),
            "tools": list(i.get("tools") or []), "auto": i.get("autonomy") or "propose", "by": ctx.actor.id,
        },
    )  # fmt: skip
    rb_log(ctx, "agent.registered", f"{i['name']} ({i['id']})", f"agent.register:{i['id']}")
    return {"id": i["id"]}


@guard("agent.update")
def update_guard(i: dict[str, Any], ctx: CallContext):
    if registry.get(ctx.session, i["id"]) is None:
        return "not_found", "Unknown agent."
    return _fields_problem(i, ctx)


def set_enabled(ctx: CallContext, agent_id: str, on: bool) -> None:
    """The kill switch: the registry row and the "agents_off" setting the Access page reads."""
    ctx.session.execute(text("UPDATE agent_identity SET enabled = :on WHERE id = :i"), {"on": on, "i": agent_id})
    off = state.get(ctx.session, "access_settings", "agents_off", for_update=True) or {}
    if on:
        off.pop(agent_id, None)
    else:
        off[agent_id] = True
    state.put(ctx.session, "access_settings", "agents_off", off)


@implement("agent.update")
def update(i: dict[str, Any], ctx: CallContext):
    cols = {k: i[k] for k in ("name", "org_scope", "tools", "autonomy") if i.get(k) is not None}
    for k, v in cols.items():  # one fixed column at a time
        ctx.session.execute(text(f"UPDATE agent_identity SET {k} = :v WHERE id = :i"), {"v": v, "i": i["id"]})  # noqa: S608 - k is one of the four column names above
    if i.get("enabled") is not None:
        set_enabled(ctx, i["id"], bool(i["enabled"]))
    a = registry.get(ctx.session, i["id"])
    changed = [*cols, *(["enabled"] if i.get("enabled") is not None else [])]
    rb_log(ctx, "agent.updated", f"{a.name if a else i['id']} · {', '.join(changed) or 'no change'}", "agent.update")
    return a.as_dict() if a else {"id": i["id"]}
