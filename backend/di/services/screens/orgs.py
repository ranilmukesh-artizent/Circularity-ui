"""Organisation (plan 8 UI gaps): the org units for the Access page's Organisation section and the Connect dialog's
org field, pilot mode per unit, and the pilot report.

    GET /api/screens/orgs                  any signed-in account
        {units: [{id, parent_id, kind, name, depth, pilot?, pilot_via?}], can: {manage, report}}
        units: the org tree depth first, only the units the account may see (a tenant-scoped role: its tenants'
        subtrees); `pilot` (the unit is in pilot mode, by its own setting or one above it) and `pilot_via` (the unit
        whose setting it is) only for an account that may manage orgs (manageOrgs) or read pilot reports
        (approve.flows), as org.setPilot and org.pilotReport allow.
    GET /api/screens/orgs/{unit}/pilot     manageOrgs or approve.flows (403 otherwise; 404 for no such unit)
        org.pilotReport's answer | {pilot, pilot_via, held: [{id, case_id, step, kind, system, target, note, sent_at}]}
        held: the instructions pilot mode kept from the enterprise systems, i.e. what would have been sent.

The writes are actions: org.update (rename), org.setPilot, org.importPack (di.services.actions.orgs, org_pilot, org_pack);
the pack's export and import preview are the read actions org.exportPack and org.previewPack.

Facade (frontend/src/api/orgs.ts) -> here:

| export | where |
|---|---|
| useOrgUnits, useOrgCan | GET /api/screens/orgs (`units`, `can`) |
| usePilotReport | GET /api/screens/orgs/{unit}/pilot |
| useOrgTree | GET /api/screens/access -> `orgs` (di.services.screens.access) |
"""

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from di.core import policy
from di.core.auth import Principal
from di.repositories.orgs import tree, units
from di.services.actions import org_pilot

REPORT_PERMS = org_pilot.REPORT_PERMS


def _can(p: Principal) -> dict[str, bool]:
    return {"manage": p.can("manageOrgs"), "report": any(p.can(x) for x in REPORT_PERMS)}


def _visible(p: Principal, uid: str) -> bool:
    """Every unit for an unscoped role; for a tenant-scoped one the units in its tenants' subtrees."""
    return not policy.policy(p.account).get("tenantScoped") or p.tenant_ok(uid)


def page(p: Principal, s: Session) -> dict[str, Any]:
    can = _can(p)
    us = units(s)
    on = org_pilot.pilot_units(s) if can["manage"] or can["report"] else set()
    out: list[dict[str, Any]] = []

    def walk(nodes: list[dict[str, Any]], depth: int) -> None:
        for n in nodes:
            if _visible(p, n["id"]):
                row = {k: n[k] for k in ("id", "parent_id", "kind", "name")} | {"depth": depth}
                if can["manage"] or can["report"]:
                    via = org_pilot.pilot_via(us, on, n["id"])
                    row |= {"pilot": via is not None, "pilot_via": via}
                out.append(row)
            walk(n["children"], depth + 1)

    walk(tree(s), 0)
    return {"units": out, "can": can}


def pilot(p: Principal, s: Session, uid: str) -> dict[str, Any]:
    if not _can(p)["report"]:
        raise HTTPException(403, {"code": "out_of_scope", "message": f"The {p.account.role} view cannot read pilot reports."})
    us = units(s)
    if uid not in us:
        raise HTTPException(404, {"code": "not_found", "message": f"No org unit {uid}."})
    if not _visible(p, uid):
        raise HTTPException(
            403, {"code": "tenant_boundary", "message": f"{uid} is an org unit you cannot see. Request tenant access first."}
        )
    via = org_pilot.pilot_via(us, org_pilot.pilot_units(s), uid)
    return org_pilot.report(s, uid) | {"pilot": via is not None, "pilot_via": via, "held": org_pilot.held(s, uid)}
