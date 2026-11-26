"""Agent registry actions (plan 8, MVP-11.3): Admin registers and edits the agents that may call Circularity.

The demo has a fixed list of nine agents, so these are declared here, beside the catalog's actions. They need
`manageAgents` (Admin, di.core.policy.EXTRA_PERMS), are commits and are journaled. Agents never run them
(di.services.agents.forbidden.FORBIDDEN_ACTIONS covers "agent.").

    agent.register  commit  {id, name, kind?, org_scope?, tools?, autonomy?}   a new agent (kind external, autonomy
                                                                                propose unless given)
    agent.update    commit  {id, name?, org_scope?, tools?, autonomy?, enabled?}   change what is sent
    agent.startRun  act     {agent, case_id, playbook?}   start a playbook run on a case (case_autopilot, the default, or
                                                          stage_chain, P9-2.1); the agent acts as the person who
                                                          started it (MVP-12.4)

agent.setEnabled (di.services.actions.access, the demo's kill switch) writes the row too, through `set_enabled`.
`tools` are MCP tool ids (di.mcp.tools.TOOLS) or action ids; `org_scope` are org unit ids (empty: every org). An action
no agent may run (di.services.agents.catalog.agent_allowed: FORBIDDEN_ACTIONS and system actions) is refused as a tool.
    agent.issueCredential commit {agent_id}  a client id and secret (the secret once); agent.revokeCredential commit
    {client_id}; agent.credentials read {agent_id} (P9-13.9; di.services.agent_credentials, POST /oauth/token)
    agent.registerClient commit {name, redirect_uris, agent_id, scopes}  a pre-registered OAuth client for an outside MCP
    client; agent.revokeClient commit {client_id}; agent.clients read {} (P9-13.10; di.services.oauth)
    agent.runTrace  read   {run_id? | case_id?}   P9-2.6 (I-12): one run (the latest for a case) with its stage records, calls,
                                                  spans as a tree, journal rows, proposals and the agent's pause history
                                                  (`di.repositories.run_trace`). Needs the agents page, or for a case the
                                                  case scope (a case outside the person's tenants: `tenant_boundary`).
The Agents page registers one with its Register agent dialog (frontend/src/pages/agents/RegisterAgentDialog.tsx).
"""

import re
from typing import Any

from sqlalchemy import text

from di.core import policy, state
from di.repositories import run_trace
from di.repositories.constants import TOOLS_BY_ID
from di.services import agent_credentials
from di.services.actions.decisions import rb_log
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.actions.scope import case_scope
from di.services.agents import registry, runtime

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


ACTIONS.setdefault(
    "agent.startRun",
    ActionDef(
        id="agent.startRun", title="Start an agent run", verb="start agent runs", risk="act", perm="runAgent", scope="case",
        desc="Start an agent's playbook on a case. The agent acts as you; what it holds waits for a person. "
        "A Planner or Approver runs the case autopilot: it only prepares.",
        input={"agent": {"req": True, "t": "string"}, "case_id": {"req": True, "t": "string"},
               "playbook": {**_OPT, "t": "string"}},
    ),
)  # fmt: skip

# P9-13.9: client credentials of an agent. A person (Admin) issues and revokes; the secret is returned once.
ACTIONS.setdefault(
    "agent.issueCredential",
    ActionDef(
        id="agent.issueCredential", title="Issue an agent credential", verb="issue agent credentials", risk="commit", perm=_PERM,
        scope="none", desc="Create a client id and secret for an agent. The secret is shown once; the agent acts as you.",
        input={"agent_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "agent.revokeCredential",
    ActionDef(
        id="agent.revokeCredential", title="Revoke an agent credential", verb="revoke agent credentials", risk="commit",
        perm=_PERM, scope="none", desc="Stop a credential: its tokens are refused at the next request.",
        input={"client_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "agent.credentials",
    ActionDef(
        id="agent.credentials", title="List an agent's credentials", verb="list agent credentials", risk="read", perm=_PERM,
        scope="none", desc="An agent's credentials: client id, owner, created, last used, revoked. Never the secret.",
        input={"agent_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip


@guard("agent.issueCredential")
def issue_credential_guard(i: dict[str, Any], ctx: CallContext):
    return None if registry.get(ctx.session, i["agent_id"]) else ("not_found", "Unknown agent.")


@implement("agent.issueCredential")
def issue_credential(i: dict[str, Any], ctx: CallContext):
    out = agent_credentials.issue(ctx.session, i["agent_id"], ctx.actor.id)
    rb_log(ctx, "agent.credential.issued", f"{i['agent_id']} · {out['client_id']}", "agent.issueCredential")  # never the secret
    return out


@guard("agent.revokeCredential")
def revoke_credential_guard(i: dict[str, Any], ctx: CallContext):
    row = ctx.session.execute(text("SELECT 1 FROM agent_credential WHERE client_id = :c"), {"c": i["client_id"]}).first()
    return None if row else ("not_found", "Unknown credential.")


@implement("agent.revokeCredential")
def revoke_credential(i: dict[str, Any], ctx: CallContext):
    agent_credentials.revoke(ctx.session, i["client_id"])
    rb_log(ctx, "agent.credential.revoked", i["client_id"], "agent.revokeCredential")
    return {"client_id": i["client_id"], "revoked": True}


@guard("agent.credentials")
def credentials_guard(i: dict[str, Any], ctx: CallContext):
    return None if registry.get(ctx.session, i["agent_id"]) else ("not_found", "Unknown agent.")


@implement("agent.credentials")
def credentials(i: dict[str, Any], ctx: CallContext):
    return {"agent_id": i["agent_id"], "credentials": agent_credentials.listing(ctx.session, i["agent_id"])}


# P9-13.10: pre-registered OAuth clients for outside MCP clients (authorization code with PKCE). Admin only.
ACTIONS.setdefault(
    "agent.registerClient",
    ActionDef(
        id="agent.registerClient", title="Register an outside MCP client", verb="register outside MCP clients", risk="commit",
        perm=_PERM, scope="none", desc="Let an outside MCP client ask people for consent to act as an agent.",
        input={"name": {"req": True, "t": "string"}, "redirect_uris": {"req": True, "t": "array"},
               "agent_id": {"req": True, "t": "string"}, "scopes": {"req": True, "t": "array"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "agent.revokeClient",
    ActionDef(
        id="agent.revokeClient", title="Revoke an outside MCP client", verb="revoke outside MCP clients", risk="commit",
        perm=_PERM, scope="none", desc="Stop a client: its tokens are refused at the next request.",
        input={"client_id": {"req": True, "t": "string"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "agent.clients",
    ActionDef(
        id="agent.clients", title="List outside MCP clients", verb="list outside MCP clients", risk="read", perm=_PERM,
        scope="none", desc="Registered outside MCP clients: name, agent, scopes, redirect URIs, revoked.", input={},
    ),
)  # fmt: skip


@guard("agent.registerClient")
def register_client_guard(i: dict[str, Any], ctx: CallContext):
    from di.services import oauth

    uris, scopes = i["redirect_uris"], i["scopes"]
    if registry.get(ctx.session, i["agent_id"]) is None:
        return "not_found", "Unknown agent."
    if not uris or not all(
        isinstance(u, str) and u.startswith(("https://", "http://localhost", "http://127.0.0.1")) for u in uris
    ):
        return "validation_error", "Redirect URIs are exact https URLs (http only on localhost)."
    if not scopes or not all(x in oauth.SCOPES for x in scopes):
        return "validation_error", f"Scopes are among {', '.join(oauth.SCOPES)}."
    return None


@implement("agent.registerClient")
def register_client(i: dict[str, Any], ctx: CallContext):
    from di.services import oauth

    cid = oauth.register_client(ctx.session, i["name"], i["redirect_uris"], i["agent_id"], i["scopes"], ctx.actor.id)
    rb_log(ctx, "agent.client.registered", f"{i['name']} · {cid} · {i['agent_id']}", "agent.registerClient")
    return {"client_id": cid}


@guard("agent.revokeClient")
def revoke_client_guard(i: dict[str, Any], ctx: CallContext):
    row = ctx.session.execute(text("SELECT 1 FROM oauth_client WHERE client_id = :c"), {"c": i["client_id"]}).first()
    return None if row else ("not_found", "Unknown client.")


@implement("agent.revokeClient")
def revoke_client(i: dict[str, Any], ctx: CallContext):
    from di.services import oauth

    oauth.revoke_client(ctx.session, i["client_id"])
    rb_log(ctx, "agent.client.revoked", i["client_id"], "agent.revokeClient")
    return {"client_id": i["client_id"], "revoked": True}


@implement("agent.clients")
def clients(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - the action signature
    from di.services import oauth

    return {"clients": oauth.clients(ctx.session)}


def _fields_problem(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i.get("autonomy") is not None and i["autonomy"] not in AUTONOMY:
        return "validation_error", "Autonomy is read, propose or act."
    from di.mcp.tools import MODELER_TOOLS  # plan 8 MVP-5.5: the MCP table's tools beyond the demo's ten
    from di.services.agents import catalog  # imports di.mcp.policy, which imports the pipeline

    known = set(TOOLS_BY_ID) | set(MODELER_TOOLS) | set(ACTIONS)
    if bad := [t for t in i.get("tools") or [] if t not in known]:
        return "validation_error", f"Unknown tools: {', '.join(map(str, bad))}."
    # plan 8 UI gaps: an action no agent may run (FORBIDDEN_ACTIONS, system actions) is never one of its tools
    if bad := [t for t in i.get("tools") or [] if t in ACTIONS and not catalog.agent_allowed(ACTIONS[t])]:
        return "validation_error", f"No agent may use: {', '.join(bad)}."
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


def _manager(ctx: CallContext) -> bool:
    """The caller manages agents (Admin): other roles that run an agent (Planner, Approver) only have it prepare."""
    a = ctx.actor.account
    return a is not None and policy.can(a, "manageAgents", ctx.actor.ctx)


@guard("agent.startRun")
def start_run_guard(i: dict[str, Any], ctx: CallContext):
    if registry.get(ctx.session, i["agent"]) is None:
        return "not_found", "Unknown agent."
    if (i.get("playbook") or runtime.autopilot.NAME) not in runtime.PLAYBOOKS:
        return "validation_error", f"The playbook is one of {', '.join(runtime.PLAYBOOKS)}."
    if not _manager(ctx):  # a Planner or Approver: propose only, the case autopilot of an enabled agent
        agent = registry.get(ctx.session, i["agent"])
        if (i.get("playbook") or runtime.autopilot.NAME) != runtime.autopilot.NAME or agent is None or not agent.enabled:
            return "out_of_scope", "You run the case autopilot of an enabled agent. Other playbooks are for an Admin."
    return None


@implement("agent.startRun")
def start_run(i: dict[str, Any], ctx: CallContext):
    """plan 8 MVP-12.4: the runtime's way in (runtime.start); the worker's agent.step job runs it, as the person."""
    playbook = i.get("playbook") or runtime.autopilot.NAME
    run_id = runtime.start(ctx.session, i["agent"], playbook, i["case_id"], account=ctx.actor.id, propose_only=not _manager(ctx))
    rb_log(ctx, "agent.run.started", f"{i['agent']} · {playbook} · {i['case_id']}", "agent.startRun")
    return {"run_id": run_id, "agent": i["agent"], "playbook": playbook, "case_id": i["case_id"]}


ACTIONS.setdefault(
    "agent.runTrace",
    ActionDef(
        id="agent.runTrace", title="Read an agent run", verb="read agent runs", risk="read", perm=None, scope="none",
        desc="One agent run: its stages, calls, spans, journal rows, proposals and the agent's pause history. Changes nothing.",
        input={"run_id": {**_OPT, "t": "string"}, "case_id": {**_OPT, "t": "string"}},
    ),
)  # fmt: skip
EMPTY_TRACE: dict[str, Any] = {"run": None, "stages": [], "calls": [], "spans": [], "journal": [], "proposals": [], "pauses": []}


@guard("agent.runTrace")
def run_trace_guard(i: dict[str, Any], ctx: CallContext):
    run_id, case_id = i.get("run_id"), i.get("case_id")
    if not run_id and not case_id:
        return "validation_error", "Name a run (run_id) or a case (case_id)."
    if ctx.actor.system:
        return None
    if run_id:
        row = ctx.session.execute(text("SELECT case_id FROM agent_run WHERE id = :i"), {"i": run_id}).first()
        if row is None:
            return "not_found", f"No agent run {run_id}."
        if case_id and row[0] != case_id:
            return "validation_error", f"{run_id} is not a run on {case_id}."
        case_id = row[0]
    acct = ctx.actor.account
    if case_id:
        where = case_scope(str(case_id))
        if where is None:
            return "not_found", f"No live case {case_id}."
        owner, location = where
        if acct is None or not policy.tenant_ok(acct, owner, ctx.actor.ctx) or not policy.location_ok(acct, location):
            return "tenant_boundary", f"{case_id} belongs to {owner}, a tenant you cannot see. Request tenant access first."
        return None
    if not policy.can_page(acct, "agents"):
        return "out_of_scope", f"The {ctx.actor.role} view cannot read agent runs."
    return None


@implement("agent.runTrace")
def read_run_trace(i: dict[str, Any], ctx: CallContext):
    run_id = i.get("run_id") or run_trace.latest_run_for_case(ctx.session, str(i["case_id"]))
    return (run_id and run_trace.run_trace(ctx.session, run_id)) or EMPTY_TRACE
