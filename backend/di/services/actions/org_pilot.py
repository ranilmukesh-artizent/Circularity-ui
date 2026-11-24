"""Pilot mode per org unit, and the pilot report (plan 8, MVP-10.3): a read-only testbed that ends in a value report.

An org unit in pilot mode keeps deciding as usual, but no instruction for a case of its subtree reaches an enterprise
system: di.services.instructions.send holds it ("Pilot mode: not sent to <target>") and the simulated adapter
acknowledges it, so the run goes on. Pilot mode never sends.

    state collection org_settings   one item per org unit id: {id, pilot}; none at the start (no unit is a pilot)
    org.setPilot     commit  {org_unit_id, on}   perm manageOrgs; journaled by the pipeline
    org.pilotReport  read    {org_unit_id}       perm manageOrgs or approve.flows: over the cases of the unit's subtree
        {org_unit_id, cases_opened, decisions_submitted, decisions_approved, recommended_net_total,
         rules_applied_count, instructions_held, by_route: {route: count}}

`is_pilot(s, owner)`: the case owner, or any unit above it, is in pilot mode. `pilot_via(units, on, uid)`: the unit whose
setting puts `uid` in pilot mode (itself or the nearest unit above it), or None. `report(s, uid)` and `held(s, uid)`
(the held instructions: what would have been sent) also serve GET /api/screens/orgs/{unit}/pilot
(di.services.screens.orgs).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import orgs, policy, state
from di.repositories import orgs as repo
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, guard, implement
from di.services.cases import store

COLLECTION = "org_settings"
state.register(COLLECTION, list)
SUBMITTED = ("awaiting_approval", "approved", "executing", "closed")  # stages a decision was submitted in
APPROVED = ("approved", "executing", "closed")
REPORT_PERMS = ("manageOrgs", "approve.flows")
_STR = {"req": True, "t": "string"}

ACTIONS.setdefault(
    "org.setPilot",
    ActionDef(
        id="org.setPilot", title="Set pilot mode", verb="set pilot mode", risk="commit", perm="manageOrgs", scope="none",
        desc="Switch pilot mode for an org unit and everything below it: decisions run as usual, but no instruction "
        "is sent to an enterprise system (each is held and acknowledged by the simulated adapter).",
        input={"org_unit_id": _STR, "on": {"req": True, "t": "boolean"}},
    ),
)  # fmt: skip
ACTIONS.setdefault(
    "org.pilotReport",
    ActionDef(
        id="org.pilotReport", title="Pilot report", verb="read pilot reports", risk="read", perm=None, scope="none",
        desc="What an org unit's cases did: cases, decisions submitted and approved, the recommended net value, rules "
        "applied, instructions held and the recommended routes. Changes nothing.",
        input={"org_unit_id": _STR},
    ),
)  # fmt: skip


def pilot_units(s: Session) -> set[str]:
    return {x["id"] for x in state.items(s, COLLECTION) if x.get("pilot")}


def is_pilot(s: Session, owner: str) -> bool:
    """The case owner, or a unit above it, is in pilot mode."""
    on = pilot_units(s)
    return bool(on) and any(u in on for u in orgs.ancestors(repo.units(s), owner))


def pilot_via(units: dict[str, orgs.OrgUnit], on: set[str], uid: str) -> str | None:
    """The unit whose pilot setting covers `uid`: itself or the nearest unit above it in pilot mode; None if none."""
    return next((u for u in orgs.ancestors(units, uid) if u in on), None)


def _unit_problem(ctx: CallContext, uid: str) -> tuple[str, str] | None:
    if ctx.session.execute(text("SELECT 1 FROM org_unit WHERE id = :i"), {"i": uid}).first() is None:
        return "not_found", f"No org unit {uid}."
    return None


# ---------------------------------------------------------------- pilot mode
@guard("org.setPilot")
def set_pilot_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _unit_problem(ctx, i["org_unit_id"])


@implement("org.setPilot")
def set_pilot(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    uid, on = i["org_unit_id"], bool(i["on"])
    state.put(ctx.session, COLLECTION, uid, {"id": uid, "pilot": on})
    return {"org_unit_id": uid, "pilot": on}


# ---------------------------------------------------------------- the report
@guard("org.pilotReport")
def report_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    a = ctx.actor
    if not a.system and not any(policy.can(a.account, p, a.ctx) for p in REPORT_PERMS):
        return "out_of_scope", f"The {a.role} view cannot read pilot reports."
    if bad := _unit_problem(ctx, i["org_unit_id"]):
        return bad
    # audit F8: a tenant-scoped person reads only units within their tenants (an unscoped one sees every unit, the group too)
    scoped = not a.system and policy.policy(a.person).get("tenantScoped")
    if scoped and not policy.tenant_ok(a.person, i["org_unit_id"], a.ctx):
        return "tenant_boundary", f"{i['org_unit_id']} is outside your tenants. Request tenant access first."
    return None


@implement("org.pilotReport")
def pilot_report(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    return report(ctx.session, i["org_unit_id"])


def _cases(s: Session, uid: str) -> list[dict[str, Any]]:
    within = orgs.subtree(repo.units(s), uid)
    return [c for c in store.all_cases(s) if c["owner"] in within]


def held(s: Session, uid: str) -> list[dict[str, Any]]:
    """The instructions held for the cases of the unit's subtree (what would have been sent), oldest first:
    {id, case_id, step, kind, system, target (the system's vendor), note, sent_at}."""
    rows = s.execute(
        text(
            "SELECT i.id, i.case_id, i.step, i.kind, i.system, s.vendor AS target, i.detail->>'note' AS note, i.sent_at "
            "FROM instruction i LEFT JOIN source_system s ON s.id = i.system "
            "WHERE i.case_id = ANY(:c) AND i.detail->>'held' = 'true' ORDER BY i.id"
        ),
        {"c": [c["id"] for c in _cases(s, uid)]},
    ).mappings()
    return [dict(r) | {"target": r["target"] or r["system"]} for r in rows]


def report(s: Session, uid: str) -> dict[str, Any]:
    """org.pilotReport's answer for the unit's subtree."""
    cases = _cases(s, uid)
    recs = [c["recommendation"] for c in cases if c.get("recommendation")]
    by_route: dict[str, int] = {}
    for r in recs:
        by_route[r["id"]] = by_route.get(r["id"], 0) + 1
    held = s.execute(
        text("SELECT count(*) FROM instruction WHERE case_id = ANY(:c) AND detail->>'held' = 'true'"),
        {"c": [c["id"] for c in cases]},
    ).scalar_one()
    return {
        "org_unit_id": uid,
        "cases_opened": len(cases),
        "decisions_submitted": sum(1 for c in cases if c["stage"] in SUBMITTED),
        "decisions_approved": sum(1 for c in cases if c["stage"] in APPROVED),
        "recommended_net_total": round(sum(r["net"] for r in recs), 2),
        "rules_applied_count": sum(1 for c in cases if c.get("rulesApplied")),
        "instructions_held": held,
        "by_route": by_route,
    }
