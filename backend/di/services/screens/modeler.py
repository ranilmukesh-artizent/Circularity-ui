"""The Modeler page (plan 8, MVP-4.2): one decision flow, its template, checks, compiled rules, history and log.

    GET /api/screens/modeler?template=<key>&org=<id>
        templates  [{key, name}] the template packs
        org        the org unit shown (default: `workspace` if the account may see it, else its first unit)
        orgs       the org unit ids the account may see (a tenant-scoped Planner: its customers' subtrees)
        flow       {id, name, org_unit_id, status, ver, dver, maker, checker, graph (the draft, else the published
                   graph), published}: the flow the org uses, its own or inherited from the nearest ancestor
        template   {key, name, pre, paths, guardrails, dims, actors} of the pack
        band       [x, y, w, h, label]: the fixed band of core prediction and agents drawn behind them (tool_fleet,
                   device; the PO golden flows), else null
        checks     the validation of `graph` ({level, msg, node_id})
        compiled   the business rules `graph` compiles to
        versions   the graphs earlier publishes replaced, newest first ({ver, published_by, published_at, note, graph})
        shadow     the shadow-run stats ({n, agree, disagree, dv}) while the flow is in shadow, else null
        log        the journal rows of the flow's actions, newest first ({at, actor, role, action, note})
        can        {edit, approve, fork}: what the account may do (edit: manageFlows on the flow's own org; fork: give
                   the shown org its own flow; approve: approve.flows). The actions check again.

Access: the `modeler` page (Admin, Planner, Approver, Executive; read-only for the Executive). An org outside the
account's units is refused with `tenant_boundary`.

Facade (frontend/src/api/modeler.ts): useModeler(template, org) reads this; the writes and simulateFlow are the flow.*
actions (di.services.actions.modeler).
"""

import dataclasses
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import golden, policy
from di.core.auth import Principal
from di.repositories import flows as repo
from di.repositories.flows import FlowRow
from di.repositories.orgs import units
from di.services.actions.modeler import checks_json
from di.services.modeler.compile import compile_flow
from di.services.modeler.flow import PO_FLOW, Flow
from di.services.modeler.templates import TEMPLATE_KEYS, Template, load_template

LOG_SQL = (
    "SELECT at, actor, role, action, input FROM action_journal WHERE NOT undone AND ("
    "(action LIKE 'flow.%' AND input->>'flow_id' = :fid) OR "
    "(action = 'flow.fork' AND input->>'template_key' = :k AND input->>'org_unit_id' = :o)) ORDER BY seq DESC"
)


def _org_ok(p: Principal, org: str) -> bool:
    return not policy.policy(p.account).get("tenantScoped") or p.tenant_ok(org)


def _template(t: Template) -> dict[str, Any]:
    d = dataclasses.asdict(t)
    return {k: d[k] for k in ("key", "name", "pre", "paths", "guardrails", "dims", "actors")}


def _flow(f: FlowRow) -> dict[str, Any]:
    graph = f.draft if f.draft is not None else f.published
    keys = ("id", "name", "org_unit_id", "status", "ver", "dver", "maker", "checker", "published")
    return {**{k: getattr(f, k) for k in keys}, "graph": graph}


def _log(s: Session, p: Principal, f: FlowRow) -> list[dict[str, Any]]:
    rows = s.execute(text(LOG_SQL), {"fid": str(f.id), "k": f.template_key, "o": f.org_unit_id}).mappings()
    out = []
    for r in rows:
        who = policy.account(r["actor"], p.ctx)
        i = r["input"] or {}
        out.append({"at": r["at"].isoformat(), "actor": who.label if who else r["actor"], "role": r["role"],
                    "action": r["action"], "note": i.get("note") or i.get("reason")})  # fmt: skip
    return out


def _can(p: Principal, f: FlowRow, org: str) -> dict[str, bool]:
    a = p.account
    manage = policy.can(a, "manageFlows", p.ctx)
    return {
        "edit": manage and f.org_unit_id == org and _org_ok(p, f.org_unit_id),
        "approve": policy.can(a, "approve.flows", p.ctx) and _org_ok(p, f.org_unit_id),
        "fork": manage and f.org_unit_id != org,
    }


def page(p: Principal, s: Session, template: str | None = None, org: str | None = None) -> dict[str, Any]:
    p.require_page("modeler")
    key = template or "industrial"
    if key not in TEMPLATE_KEYS:
        raise HTTPException(404, {"code": "not_found", "message": f"No template {key}."})
    all_units = units(s)
    orgs = [u for u in all_units if _org_ok(p, u)]
    org = org or ("workspace" if "workspace" in orgs else (orgs[0] if orgs else "workspace"))
    if org not in all_units:
        raise HTTPException(404, {"code": "not_found", "message": f"No org unit {org}."})
    if org not in orgs:
        msg = f"{org} is a tenant you cannot see. Request tenant access first."
        raise HTTPException(403, {"code": "tenant_boundary", "message": msg})
    f = repo.flow_for(s, key, org)
    if f is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No decision flow for {key} above {org}."})
    t = load_template(key)
    graph = cast(Flow, f.draft if f.draft is not None else f.published)
    versions = [dataclasses.asdict(v) | {"published_at": v.published_at.isoformat() if v.published_at else None}
                for v in repo.versions(s, f.id)]  # fmt: skip
    return {
        "templates": [{"key": k, "name": load_template(k).name} for k in TEMPLATE_KEYS],
        "org": org,
        "orgs": orgs,
        "flow": _flow(f),
        "template": _template(t),
        "band": golden.load("po/flows")[PO_FLOW[key]]["band"] if key in PO_FLOW else None,
        "checks": checks_json(t, graph),
        "compiled": [dataclasses.asdict(r) for r in compile_flow(t, graph)],
        "versions": versions,
        "shadow": repo.shadow_stats(s, f.id) if f.status == "shadow" else None,
        "log": _log(s, p, f),
        "can": _can(p, f, org),
    }
