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
        queue      the open queue the flow decides, under its published rules ({id, label, best, net}): the live cases
                   the account may see; for tool_fleet and device also the template's sample queue (MVP-6.3)
        packs      the pack versions (plan 9, P9-1.6; the pack.* actions of di.services.actions.packs): {keys [{key, name,
                   file_version (the pack file's, null for an imported key), versions [{id, version, status (draft, review,
                   pub, retired), org_unit_id, maker, checker, note, impact {changed, total, dv} | null, parts {ok, total},
                   created_at, published_at}], newest first}], templates [{key, name}] (every template a case can be opened
                   with: the three packs and the published imported ones), can {import, approve}}; the versions the account
                   may see (a tenant-scoped Planner: the ones for every org and for its own units)
        can        {edit, approve, fork}: what the account may do (edit: manageFlows on the flow's own org; fork: give
                   the shown org its own flow; approve: approve.flows). The actions check again.
        overlay    the shown org's customer overlay of the pack (plan 9, P9-1.3): {pack_key, org_unit_id, pack_version,
                   status ("none" before the first save, else draft, review or pub), ver, base_version,
                   draft_base_version, stale (the pack is newer than the base of what is shown), maker, checker, ops (the
                   draft, else the published ones), published, conflicts, notes, guardrails [{id, text, locked,
                   stage_label, approvers, param {field, value, stricter, min, max} | null}], stages [{key, label}],
                   routes [{id, name}], in_force {org_unit_id, ver} | null (the published overlay the org's cases use,
                   its own or inherited), can {edit, approve}}

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
from di.repositories import packs as pack_repo
from di.repositories.context import call_ctx
from di.repositories.flows import FlowRow
from di.repositories.orgs import units
from di.repositories.overlays import get as get_overlay
from di.repositories.overlays import nearest_published
from di.services.actions.modeler import checks_json
from di.services.actions.modeler_sim import queue_rows
from di.services.modeler.compile import compile_flow
from di.services.modeler.flow import PO_FLOW, Flow
from di.services.modeler.pack import load_pack, pack_keys
from di.services.modeler.stages import STAGE_KEYS, STAGE_LABELS
from di.services.modeler.templates import Template, load_template, template_keys

LOG_SQL = (
    "SELECT at, actor, role, action, input FROM action_journal WHERE NOT undone AND ("
    "(action LIKE 'flow.%' AND input->>'flow_id' = :fid) OR "
    "(action = 'flow.fork' AND input->>'template_key' = :k AND input->>'org_unit_id' = :o)) ORDER BY seq DESC"
)


def _org_ok(p: Principal, org: str) -> bool:
    return not policy.policy(p.account).get("tenantScoped") or p.tenant_ok(org)


def _template(t: Template) -> dict[str, Any]:
    d = dataclasses.asdict(t)
    out = {k: d[k] for k in ("key", "name", "pre", "paths", "guardrails", "dims", "actors")}
    out["guardrails"] = [
        {k: g[k] for k in ("id", "text", "owner", "type", "stage", "locked")} | {"stage_label": STAGE_LABELS[g["stage"]]}
        for g in d["guardrails"]
    ]
    return out


def _flow(f: FlowRow) -> dict[str, Any]:
    graph = f.draft if f.draft is not None else f.published
    keys = ("id", "name", "org_unit_id", "status", "ver", "dver", "maker", "checker", "published", "returned")
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


def _overlay(p: Principal, s: Session, key: str, org: str) -> dict[str, Any]:
    """The org's customer overlay of the template's pack, with what the Customer layer panel needs to edit it."""
    pack, row = pack_repo.active_pack(s, key, org), get_overlay(s, key, org)
    live = nearest_published(s, key, org)
    shown_base = pack.version
    if row:
        shown_base = (row.draft_base_version if row.draft is not None else None) or row.base_version
    ok_org = _org_ok(p, org)
    return {
        "pack_key": key, "org_unit_id": org, "pack_version": pack.version, "status": row.status if row else "none",
        "ver": row.ver if row else 0, "base_version": row.base_version if row else None,
        "draft_base_version": row.draft_base_version if row else None, "stale": shown_base != pack.version,
        "maker": row.maker if row else None, "checker": row.checker if row else None,
        "ops": (row.draft if row.draft is not None else row.published) if row else [],
        "published": row.published if row else [], "conflicts": row.conflicts if row else [], "notes": row.notes if row else [],
        "guardrails": [
            {"id": g.id, "text": g.text, "locked": g.locked, "stage_label": STAGE_LABELS[g.stage], "approvers": g.approvers,
             "param": g.param.model_dump() if g.param else None}
            for g in pack.guardrails
        ],
        "params": [{"path": k, **v.model_dump()} for k, v in pack.customer_layer.params.items()],  # P9-3.20
        "stages": [{"key": k, "label": STAGE_LABELS[k]} for k in STAGE_KEYS],
        "routes": [{"id": r.id, "name": r.name} for r in pack.routes],
        "in_force": {"org_unit_id": live.org_unit_id, "ver": live.ver} if live else None,
        "can": {"edit": policy.can(p.account, "manageFlows", p.ctx) and ok_org,
                "approve": policy.can(p.account, "approve.flows", p.ctx) and ok_org},
    }  # fmt: skip


def _packs(p: Principal, s: Session) -> dict[str, Any]:
    """The pack versions the account may see, and the templates a case can be opened with."""
    keys = sorted(set(pack_keys()) | set(pack_repo.stored_keys(s)))
    published = pack_repo.published_keys(s)
    out, names = [], {k: load_template(k).name for k in template_keys()}
    for k in keys:
        versions = [v for v in pack_repo.versions(s, k) if v["org_unit_id"] is None or _org_ok(p, v["org_unit_id"])]
        newest = pack_repo.rows(s, k)
        name = names.get(k) or (newest[0].doc.get("name") if newest else k)
        out.append({"key": k, "name": name, "file_version": load_pack(k).version if k in pack_keys() else None,
                    "versions": versions})  # fmt: skip
        if k in published and k not in names:
            names[k] = str(name)
    return {
        "keys": out,
        "templates": [{"key": k, "name": n} for k, n in names.items()],
        "can": {"import": policy.can(p.account, "managePacks", p.ctx), "approve": policy.can(p.account, "approve.packs", p.ctx)},
    }


def page(p: Principal, s: Session, template: str | None = None, org: str | None = None) -> dict[str, Any]:
    p.require_page("modeler")
    key = template or "industrial"
    if key not in template_keys():
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
        "templates": [{"key": k, "name": load_template(k).name} for k in template_keys()],
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
        "queue": queue_rows(call_ctx(p, s), f),
        "can": _can(p, f, org),
        "overlay": _overlay(p, s, key, org),
        "packs": _packs(p, s),
    }
