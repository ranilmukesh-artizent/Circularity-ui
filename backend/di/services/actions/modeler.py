"""Flow lifecycle actions (plan 8, MVP-3.2; Domain spec D7, the prototype's touch() and Modeler buttons).

A flow (table decision_flow, di.repositories.flows) belongs to a template and an org unit. Someone who may manage
flows edits a draft and submits it; a different person who may approve flows approves it (maker-checker), which
starts a shadow run beside the published flow, then publishes it. The published graph a publish replaces is kept in
decision_flow_version for rollback. Decisions use the published graph only, from the next re-evaluation on.

    flow.saveDraft  act     {flow_id, graph}             touch() and store the draft; answers {checks}
    flow.fork       act     {template_key, org_unit_id}  the org's own flow, from its nearest ancestor's published one
    flow.submit     act     {flow_id}                    draft -> review (no blocking checks)
    flow.approve    commit  {flow_id}                    review -> shadow (not by a maker: anyone who saved or
                                                         submitted this draft, from the journal; audit F3b)
    flow.reject     commit  {flow_id, reason,    review or shadow -> draft; stores `returned` {reason, node_id, by, at};
                            node_id?}        flow.saveDraft keeps it, flow.submit clears it
    flow.publish    commit  {flow_id}                    shadow -> pub (not by the maker); old graph to history
    flow.discard    act     {flow_id}                    the draft back to the published graph
    flow.rollback   commit  {flow_id}                    the latest history entry becomes the published graph
    flow.get        read    {flow_id} | {template, org}  {flow, template, checks, compiled} (by org: the flow it uses)
    flow.simulate   read    {flow_id, graph?, params?}   the graph (or draft) against the published rules on the open
                                                         queue (di.services.actions.modeler_sim); manageFlows or approve.flows.
                                                         `params` {market, labor, lease, slots}: tool-fleet what-if levers
                                                         (P9-0.15), the candidate valued at BASEP | params; nothing is saved
    flow.exportDmn  read    {flow_id}                    {filename, content_type, xml}: the flow's rules, guardrails and the
                                                         org's decision tables as DMN 1.3 (di.services.modeler.export_dmn)
    flow.exportBpmn read    {flow_id}                    the same shape: the case process as BPMN 2.0 (export_bpmn); both
                                                         need the Modeler page, change nothing and are open to agents
    flow.propose    read    {flow_id, text}              a plain-language change as a checked proposal on the draft
                                                         (di.services.modeler.propose), simulated against the draft; saves
                                                         nothing. A person applies it with flow.saveDraft {graph, source:
                                                         "assistant", note: "Proposed by the assistant: <text>"}

Every write is journaled. The org scope is the flow's org unit: a tenant-scoped person (a Planner) reaches only the
flows of the units they may see (policy.tenant_ok); everyone else reaches every flow. Agents never approve, return,
publish or roll back a flow (di.services.agents.forbidden.FORBIDDEN_ACTIONS, and refused here when an agent prepared the call).
"""

import dataclasses
import json
import re
from typing import Any, cast

from sqlalchemy import text

from di.core import policy
from di.repositories import flows as repo
from di.repositories import market_tables, rollouts
from di.repositories.flows import FlowRow
from di.repositories.orgs import units
from di.services.actions.modeler_sim import lever_problem, sim_json, simulate_graph, simulate_rules
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, Risk, guard, implement, mark_destructive
from di.services.ask.modeler_read import model_rule
from di.services.modeler.compile import compile_flow
from di.services.modeler.export_bpmn import process_of, to_bpmn
from di.services.modeler.export_dmn import Table, decision_id, to_dmn
from di.services.modeler.flow import Flow
from di.services.modeler.pack import load_pack
from di.services.modeler.parse import parse_rule
from di.services.modeler.propose import STEP, Proposal, build_proposal, fill_parsed, refused_text
from di.services.modeler.tables import table_title
from di.services.modeler.templates import Template, load_template, template_keys
from di.services.modeler.validate import blocking, validate_flow

MAKER_CHECKER = "Maker-checker: you made these changes, so you cannot approve them."
LOCKED_STEPS = ("trigger", "gate", "decision", "approval")  # the steps validation and compiling stand on
_MANAGE, _APPROVE = "manageFlows", "approve.flows"
_ID = {"flow_id": {"req": True, "t": "number"}}
_STR = {"req": True, "t": "string"}


def _declare(
    action_id: str, title: str, verb: str, desc: str, risk: Risk, inp: dict[str, dict[str, Any]], perm: str | None
) -> None:
    ACTIONS.setdefault(
        action_id,
        ActionDef(id=action_id, title=title, desc=desc, risk=risk, perm=perm, scope="none", input=inp, verb=verb),
    )


_declare("flow.saveDraft", "Save a flow draft", "edit decision flows",
         "Save your changes to a decision flow as a draft and check it.", "act",
         {**_ID, "graph": {"req": True, "t": "object"}, "source": {"t": "string"}, "note": {"t": "string"}},
         _MANAGE)  # fmt: skip
_declare("flow.fork", "Give an org its own flow", "edit decision flows",
         "Start an org unit's own decision flow from the one it uses now.", "act",
         {"template_key": _STR, "org_unit_id": _STR}, _MANAGE)  # fmt: skip
_declare("flow.submit", "Submit a flow for approval", "submit decision flows",
         "Send a draft decision flow to a different person for approval.", "act", _ID, _MANAGE)  # fmt: skip
_declare("flow.approve", "Approve a flow", "approve decision flows",
         "Approve a submitted decision flow; it runs in shadow beside the published one.", "commit", _ID, _APPROVE)  # fmt: skip
_declare("flow.reject", "Return a flow to draft", "return decision flows",
         "Return a submitted decision flow to its maker with a reason.", "commit",
         {**_ID, "reason": {"req": True, "t": "string", "min": 15, "minText": "Add a reason of at least 15 characters."},
          "node_id": {"t": "string"}},
         _APPROVE)  # fmt: skip
_declare("flow.publish", "Publish a flow", "publish decision flows",
         "Publish an approved decision flow. Decisions use it from the next re-evaluation.", "commit", _ID, _APPROVE)  # fmt: skip
_declare("flow.discard", "Discard a flow draft", "edit decision flows",
         "Drop the draft and go back to the published decision flow.", "act", _ID, _MANAGE)  # fmt: skip
mark_destructive("flow.discard")  # an agent that prepares it is held for a person (P9-2.4)
_declare("flow.rollback", "Roll back a flow", "roll back decision flows",
         "Restore the decision flow published before the current one.", "commit", _ID, _APPROVE)  # fmt: skip
_declare("flow.get", "Read a flow", "read decision flows",
         "A decision flow with its template, checks and compiled rules. Changes nothing.", "read",
         {"flow_id": {"t": "number"}, "template": {"t": "string"}, "org": {"t": "string"}}, None)  # fmt: skip
_declare("flow.simulate", "Simulate a flow", "simulate decision flows",
         "Run a flow's draft (or the graph given) against its published rules on the open queue. Changes nothing.",
         "read", {**_ID, "graph": {"t": "object"}, "params": {"t": "object"}}, None)  # fmt: skip
_declare(
    "flow.exportDmn",
    "Export a flow as DMN",
    "export decision flows",
    "The flow's rules, guardrails and decision tables as a DMN 1.3 file. Lossy by design. Changes nothing.",
    "read",
    _ID,
    None,
)
_declare("flow.exportBpmn", "Export a flow as BPMN", "export decision flows",
         "The case process of a flow as a BPMN 2.0 file. Lossy by design. Changes nothing.", "read", _ID, None)  # fmt: skip
_declare("flow.propose", "Propose a flow change", "propose decision flow changes",
         "Turn a plain-language change into a checked, simulated proposal for the draft. Saves nothing.", "read",
         {**_ID, "text": {"req": True, "t": "string", "min": 3, "minText": "Describe the change in a few words."}},
         _MANAGE)  # fmt: skip


# ---------------------------------------------------------------- helpers
def _org_ok(ctx: CallContext, org: str) -> bool:
    acct = ctx.actor.person
    if not policy.policy(acct).get("tenantScoped"):
        return True
    return policy.tenant_ok(acct, org, ctx.actor.ctx)


def _boundary(org: str) -> tuple[str, str]:
    return "tenant_boundary", f"{org} is a tenant you cannot see. Request tenant access first."


def _flow(ctx: CallContext, i: dict[str, Any], for_update: bool = False) -> FlowRow:
    f = repo.get_flow(ctx.session, int(i["flow_id"]), for_update=for_update)
    if f is None:
        raise ActionError("not_found", f"No decision flow {i['flow_id']}.")
    return f


def _reach(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | FlowRow:
    """The flow, or the refusal: unknown flow, or outside the actor's orgs."""
    try:
        f = _flow(ctx, i)
    except ActionError as e:
        return e.code, e.message
    return f if _org_ok(ctx, f.org_unit_id) else _boundary(f.org_unit_id)


def _graph(f: FlowRow) -> Flow:
    """The graph being worked on: the draft, else the published one."""
    return cast(Flow, f.draft if f.draft is not None else f.published)


def _who(ctx: CallContext, account_id: str | None) -> str:
    a = policy.account(account_id or "", ctx.actor.ctx)
    return a.label if a else (account_id or "")


_JSON_COLS = ("draft", "published", "returned")


def _update(ctx: CallContext, f: FlowRow, **cols: Any) -> None:
    sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k in _JSON_COLS else f"{k} = :{k}" for k in cols)
    vals = {k: json.dumps(v) if k in _JSON_COLS and v is not None else v for k, v in cols.items()}
    ctx.session.execute(text(f"UPDATE decision_flow SET {sets}, updated_at = :now WHERE id = :id"),  # noqa: S608 - column names are this module's; values are bound
                        {**vals, "id": f.id, "now": ctx.now})  # fmt: skip


def _agent_refusal(ctx: CallContext) -> tuple[str, str] | None:
    if ctx.preparer:
        return "approval_required", "Decision flows are approved, returned, published or rolled back only by a person."
    return None


# a draft's history in the journal: these actions make someone a maker; these end the draft
_MAKES, _ENDS = ("flow.saveDraft", "flow.submit"), ("flow.publish", "flow.discard", "flow.rollback", "rollout.full")


def makers(ctx: CallContext, f: FlowRow) -> set[str]:
    """Everyone who saved or submitted the flow's current draft (audit F3b): the journaled saves and submits since its
    last publish, discard or rollback, and the recorded maker."""
    rows = ctx.session.execute(
        text(
            "SELECT action, actor FROM action_journal WHERE NOT undone AND action = ANY(:acts) "
            "AND input->>'flow_id' = :fid ORDER BY seq"
        ),
        {"acts": [*_MAKES, *_ENDS], "fid": str(f.id)},
    )
    out: set[str] = set()
    for action, actor in rows:
        if action in _ENDS:
            out.clear()
        else:
            out.add(actor)
    return out | ({f.maker} if f.maker else set())


def _maker_refusal(ctx: CallContext, f: FlowRow) -> tuple[str, str] | None:
    return ("conflict", MAKER_CHECKER) if ctx.actor.id in makers(ctx, f) else None


def _status(f: FlowRow, want: tuple[str, ...], msg: str) -> tuple[str, str] | None:
    return None if f.status in want else ("conflict", msg)


def checks_json(t: Template, g: Flow) -> list[dict[str, Any]]:
    return [{"level": c.level, "msg": c.msg, "node_id": c.node_id} for c in validate_flow(t, g)]


# ---------------------------------------------------------------- saveDraft
def _graph_problem(g: dict[str, Any]) -> str | None:
    nodes, edges = g.get("nodes"), g.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not all(isinstance(n, dict) for n in nodes):
        return "The graph needs a list of nodes and a list of edges."
    if not all(isinstance(e, dict) and {"a", "b"} <= e.keys() for e in edges):
        return "Every edge needs its two ends (a and b)."
    have = {n.get("t") for n in nodes}
    missing = [t for t in LOCKED_STEPS if t not in have]
    return f"The flow must keep its locked steps; missing: {', '.join(missing)}." if missing else None


@guard("flow.saveDraft")
def save_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    bad = _graph_problem(i["graph"])
    if not bad and rollouts.active_rollout(ctx.session, f.id):  # P9-7.3: the candidate of a running canary does not change
        return "conflict", f"{f.name} has a canary running: roll it back or publish it in full before editing the draft."
    return ("validation_error", bad) if bad else None


@implement("flow.saveDraft")
def save_draft(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    g: Flow = {"nodes": list(i["graph"]["nodes"]), "edges": list(i["graph"]["edges"])}
    if f.status != "draft":  # touch(): the first edit makes a draft of the next version, made by this person
        _update(ctx, f, status="draft", maker=ctx.actor.id, checker=None, dver=f.ver + 1, draft=g)
    else:
        _update(ctx, f, draft=g)
    return {"id": f.id, "checks": checks_json(load_template(f.template_key), g)}


# ---------------------------------------------------------------- fork
@guard("flow.fork")
def fork_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if i["template_key"] not in template_keys():
        return "validation_error", f"The template is one of {', '.join(template_keys())}."
    org = i["org_unit_id"]
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    if not _org_ok(ctx, org):
        return _boundary(org)
    base = repo.flow_for(ctx.session, i["template_key"], org)
    if base is None:
        return "not_found", f"No decision flow for {i['template_key']} above {org}."
    if base.org_unit_id == org:
        return "conflict", f"{org} already has its own {base.name} flow."
    return None


@implement("flow.fork")
def fork(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    base = repo.flow_for(ctx.session, i["template_key"], i["org_unit_id"])
    if base is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No decision flow for {i['template_key']}.")
    fid = ctx.session.execute(
        text(
            "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, published, updated_at) "
            "VALUES (:k, :o, :n, 'pub', 1, CAST(:g AS jsonb), :now) RETURNING id"
        ),
        {"k": base.template_key, "o": i["org_unit_id"], "n": base.name, "g": json.dumps(base.published), "now": ctx.now},
    ).scalar_one()
    return {"id": fid, "flow_id": fid, "from": base.org_unit_id}


# ---------------------------------------------------------------- submit, approve, reject
@guard("flow.submit")
def submit_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _status(f, ("draft",), f"{f.name} has no draft to submit."):
        return bad
    if blocking(validate_flow(load_template(f.template_key), _graph(f))):
        return "conflict", "Fix the blocking checks before submitting."
    return None


@implement("flow.submit")
def submit(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    _update(ctx, f, status="review", returned=None)
    return {"id": f.id, "status": "review", "log": f"Submitted {f.name} v{f.dver} for approval"}


@guard("flow.approve")
def approve_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _agent_refusal(ctx) or _status(f, ("review",), f"{f.name} is not waiting for approval."):
        return bad
    return _maker_refusal(ctx, f)


@implement("flow.approve")
def approve(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    _update(ctx, f, status="shadow", checker=ctx.actor.id)
    log = f"Approved {f.name} v{f.dver} (maker {_who(ctx, f.maker)}); shadow run started"
    return {"id": f.id, "status": "shadow", "log": log}


@guard("flow.reject")
def reject_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _agent_refusal(ctx) or _status(f, ("review", "shadow"), f"{f.name} is not waiting for approval."):
        return bad
    node = i.get("node_id")
    if node is not None and node not in {n.get("id") for n in _graph(f)["nodes"]}:
        return "validation_error", f"No step {node} in this draft."
    return None


@implement("flow.reject")
def reject(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    node = i.get("node_id")
    returned = {"reason": i["reason"], "node_id": node, "by": ctx.actor.id, "at": ctx.now.isoformat()}
    _update(ctx, f, status="draft", checker=None, returned=returned)
    out = {"id": f.id, "status": "draft", "log": f"Returned {f.name} v{f.dver} to draft", "reason": i["reason"]}
    return {**out, "node_id": node} if node is not None else out


# ---------------------------------------------------------------- publish, discard, rollback
@guard("flow.publish")
def publish_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _agent_refusal(ctx) or _status(f, ("shadow",), f"{f.name} must be approved before it is published."):
        return bad
    return _maker_refusal(ctx, f)


@implement("flow.publish")
def publish(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    ctx.session.execute(
        text(
            "INSERT INTO decision_flow_version (flow_id, ver, graph, published_by, published_at, note) "
            "VALUES (:f, :v, CAST(:g AS jsonb), :by, :at, :note) "
            "ON CONFLICT (flow_id, ver) DO UPDATE SET graph = EXCLUDED.graph, published_by = EXCLUDED.published_by, "
            "published_at = EXCLUDED.published_at, note = EXCLUDED.note"
        ),
        {"f": f.id, "v": f.ver, "g": json.dumps(f.published), "by": ctx.actor.id, "at": ctx.now,
         "note": f"Replaced by v{f.dver}"},
    )  # fmt: skip
    ver = f.dver or f.ver + 1
    _update(ctx, f, status="pub", ver=ver, dver=None, maker=None, checker=None, published=_graph(f), draft=None)
    return {"id": f.id, "status": "pub", "ver": ver, "log": f"Published {f.name} v{ver}"}


@guard("flow.discard")
def discard_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    return ("conflict", f"{f.name} has no draft to discard.") if f.status == "pub" else None


@implement("flow.discard")
def discard(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    _update(ctx, f, status="pub", dver=None, maker=None, checker=None, draft=None, returned=None)
    return {"id": f.id, "status": "pub", "log": f"Discarded draft changes to {f.name}"}


@guard("flow.rollback")
def rollback_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    if bad := _agent_refusal(ctx):
        return bad
    return None if repo.versions(ctx.session, f.id) else ("conflict", "No earlier version to roll back to.")


@implement("flow.rollback")
def rollback(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i, for_update=True)
    h = repo.versions(ctx.session, f.id)[0]
    ctx.session.execute(text("DELETE FROM decision_flow_version WHERE flow_id = :f AND ver = :v"), {"f": f.id, "v": h.ver})
    _update(ctx, f, status="pub", ver=h.ver, dver=None, maker=None, checker=None, published=h.graph, draft=None, returned=None)
    return {"id": f.id, "status": "pub", "ver": h.ver, "log": f"Rolled back {f.name} from v{f.ver} to v{h.ver}"}


# ---------------------------------------------------------------- read
def _by_org(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | FlowRow:
    """flow.get by {template, org} (MVP-5.5, the MCP and Ask tool): the flow the org uses, its own or inherited; the
    org (default `workspace`) must be one the actor may see."""
    key, org = i.get("template") or "industrial", i.get("org") or "workspace"
    if key not in template_keys():
        return "validation_error", f"The template is one of {', '.join(template_keys())}."
    if org not in units(ctx.session):
        return "not_found", f"No org unit {org}."
    if not _org_ok(ctx, org):
        return _boundary(org)
    f = repo.flow_for(ctx.session, key, org)
    return f if f is not None else ("not_found", f"No decision flow for {key} above {org}.")


def _get_target(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | FlowRow:
    return _reach(i, ctx) if i.get("flow_id") is not None else _by_org(i, ctx)


@guard("flow.get")
def get_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _get_target(i, ctx)
    return f if isinstance(f, tuple) else None


def flow_json(f: FlowRow) -> dict[str, Any]:
    d = dataclasses.asdict(f)
    d["updated_at"] = f.updated_at.isoformat()
    return d


@implement("flow.get")
def get(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _get_target(i, ctx)
    if isinstance(f, tuple):  # not reached: the guard refused it
        raise ActionError(*f)
    t, g = load_template(f.template_key), _graph(f)
    return {
        "flow": flow_json(f),
        "template": dataclasses.asdict(t),
        "checks": checks_json(t, g),
        "compiled": [dataclasses.asdict(r) for r in compile_flow(t, g)],
    }


# ---------------------------------------------------------------- simulate
def may_model(ctx: CallContext) -> bool:
    """A person who may edit or approve flows."""
    acct = ctx.actor.account
    return acct is not None and any(policy.can(acct, p, ctx.actor.ctx) for p in (_MANAGE, _APPROVE))


@guard("flow.simulate")
def simulate_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not may_model(ctx):
        return "out_of_scope", f"The {ctx.actor.role} view cannot simulate decision flows."
    f = _reach(i, ctx)
    if isinstance(f, tuple):
        return f
    bad = _graph_problem(i["graph"]) if i.get("graph") is not None else None
    bad = bad or (lever_problem(f, i["params"]) if i.get("params") is not None else None)
    return ("validation_error", bad) if bad else None


@implement("flow.simulate")
def simulate(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i)
    g = cast(Flow, i["graph"]) if i.get("graph") is not None else _graph(f)
    params = i.get("params")
    return sim_json(simulate_graph(ctx, f, g, params, with_nodes=True), params)


# ---------------------------------------------------------------- propose
@guard("flow.propose")
def propose_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    f = _reach(i, ctx)
    return f if isinstance(f, tuple) else None


def proposal_json(p: Proposal) -> dict[str, Any]:
    return {
        "kind": p.kind, "text": p.text, "graph": p.graph, "node_id": p.node_id, "rid": p.rid, "label": p.label,
        "guard": p.guard, "checks": [c._asdict() for c in p.checks], "sim": sim_json(p.sim) if p.sim else None,
        "msg": p.msg, "note": f"Proposed by the assistant: {p.text}",
    }  # fmt: skip


@implement("flow.propose")
def propose(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """The proposal for the text on the flow's draft (or published graph), simulated against it on the open queue."""
    f = _flow(ctx, i)
    t, draft, text = load_template(f.template_key), _graph(f), i["text"].strip()
    base = compile_flow(t, draft)
    fill = _model_fill(t, text)
    p = build_proposal(t, draft, text, ctx.actor.role, lambda cand: simulate_rules(ctx, f, cand, base), fill)
    used = bool(fill) and fill_parsed(parse_rule(t, text), fill) != parse_rule(t, text)
    return proposal_json(p) | {"read_by": "rules+model" if used else "rules"}


def _model_fill(t: Template, text: str) -> dict[str, Any]:
    """The optional model reading (MVP-5.3), asked only when the parser finds no path in a sentence that is neither a
    guardrail change nor a step: {} without a key or on any failure."""
    if refused_text(t, text) or STEP.search(text) or parse_rule(t, text).path:
        return {}
    return model_rule(text, t)


# ---------------------------------------------------------------- export (plan 9, P9-8.21)
def _export_refusal(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    if not policy.can_page(ctx.actor.account, "modeler"):
        return "out_of_scope", f"The {ctx.actor.role} view cannot export decision flows."
    f = _reach(i, ctx)
    return f if isinstance(f, tuple) else None


@guard("flow.exportDmn")
def export_dmn_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _export_refusal(i, ctx)


@guard("flow.exportBpmn")
def export_bpmn_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _export_refusal(i, ctx)


def _export(f: FlowRow, ext: str, xml: str) -> dict[str, Any]:
    org = re.sub(r"[^a-z0-9]+", "-", f.org_unit_id.lower()).strip("-")
    return {"filename": f"{f.template_key}-{org}-v{f.ver}.{ext}", "content_type": "application/xml", "xml": xml}


def _tables(ctx: CallContext, f: FlowRow) -> list[Table]:
    """The org's approved decision tables, the newest version of each name and market."""
    seen: set[tuple[str, str]] = set()
    out: list[Table] = []
    for r in market_tables.listed(ctx.session, f.template_key, None, None, f.org_unit_id):
        if r.kind == "decision_table" and r.status == "approved" and (r.name, r.market) not in seen:
            seen.add((r.name, r.market))
            out.append(Table(r.name, table_title(f.template_key, r.name), r.market, r.version, r.body))
    return out


@implement("flow.exportDmn")
def export_dmn(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i)
    t, g = load_template(f.template_key), _graph(f)
    return _export(f, "dmn", to_dmn(load_pack(f.template_key), g, compile_flow(t, g), _tables(ctx, f)))


@implement("flow.exportBpmn")
def export_bpmn(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    f = _flow(ctx, i)
    pack = load_pack(f.template_key)
    return _export(f, "bpmn", to_bpmn(pack, process_of(pack, _graph(f)), decision_id(pack)))
