"""Reporting evidence at close (plan 9, P9-13.5, story X-16; registry entries I-3 and I-20).

The logic is `di.services.execution.reporting` (pure). This module owns the database side:

    reporting_missing(s, c)        what the case lacks before it may close (the pack's `close.reporting`, the org's `csrd_scope`)
    hold_for_evidence(ctx, c, ...) the last acknowledgement arrived without it: the case stays `executing`, the last step is
                                   `waiting_evidence`, one `reporting_evidence` item is open for the sustainability lead (I-20)
    case.attachReporting           commit  {case_id, mass_kg, material, treatment_code, source_ref}: a person attaches what the
                                   facility reported; when nothing is missing any more the case moves to `closed`

`case.attachReporting` is HELD_FOR_PERSON (an agent may prepare it, a person attaches evidence). The treatment code must match
`^[RD]\\d{1,2}$`. The org flag `csrd_scope` is the state collection `csrd_scope` (item id = org unit id, `{"csrd_scope": true}`).
No model step (R16): it checks data. A case of a pack without `close.reporting` (the industrial pack) closes as before.
Compliance text: pending review by Kinective's Legal team.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import state
from di.repositories.packs import active_pack
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import lifecycle, process, store
from di.services.execution import reporting

TYPE = "reporting_evidence"
WAITING = "waiting_evidence"
COLLECTION = "csrd_scope"
state.register(COLLECTION, lambda: [])

ACTIONS.setdefault(
    "case.attachReporting",
    ActionDef(
        id="case.attachReporting", title="Attach reporting evidence", verb="attach reporting evidence",
        desc="Attach the mass, material and treatment code the treatment facility reported for a case that waits for them. "
             "When nothing is missing any more the case closes.",
        risk="act", perm="assess", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "mass_kg": {"req": True, "t": "number"},
            "material": {"req": True, "t": "string"},
            "treatment_code": {"req": True, "t": "string"},
            "source_ref": {"req": True, "t": "string"},
        },
    ),
)  # fmt: skip


def org_of(s: Session, c: dict[str, Any]) -> dict[str, Any]:
    return state.get(s, COLLECTION, str(c.get("owner") or "")) or {}


def reporting_missing(s: Session, c: dict[str, Any]) -> list[reporting.Missing]:
    """What a case still lacks to close; nothing for a case without a pack (a case not opened from one has no gate)."""
    if not c.get("template"):
        return []
    try:
        pack = active_pack(s, c["template"], c.get("owner"))
    except KeyError:
        return []
    return reporting.close_check(c, pack, org_of(s, c)) if pack.close.reporting else []


def hold_for_evidence(ctx: CallContext, c: dict[str, Any], step: dict[str, Any], missing: list[reporting.Missing]) -> None:
    """Keep the case `executing` with the last step waiting, and open one item (never a second while one is open)."""
    s = ctx.session
    step["state"] = WAITING
    step["waiting"] = reporting.waiting_text(missing)
    store.save(s, c)
    if not s.execute(
        text("SELECT 1 FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"), {"c": c["id"], "t": TYPE}
    ).first():
        process.open_item(
            s, kind="exception", case_id=c["id"], org_unit_id=c.get("owner"), type=TYPE,
            title=f"Reporting evidence missing on {c['id']}", cause=step["waiting"],
            action="Attach what the facility reported (case.attachReporting) or wait for its sync",
            owner_role=process.role_of_owner("Sustainability lead"), due_hours=process.sla_hours(s, c["id"], "exception"),
            by="system",
        )  # fmt: skip


def _waiting(c: dict[str, Any] | None) -> dict[str, Any] | None:
    steps = ((c or {}).get("exec") or {}).get("steps") or []
    return steps[-1] if steps and steps[-1].get("state") == WAITING else None


@guard("case.attachReporting")
def attach_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = store.get(ctx.session, i["case_id"])
    if c is None:
        return "not_found", f"No case {i['case_id']}."
    if not reporting.CODE_PATTERN.match(str(i["treatment_code"]).strip()):
        return "validation_error", "The treatment code is an R or D code such as R4 or D10."
    if not isinstance(i["mass_kg"], int | float) or i["mass_kg"] <= 0:
        return "validation_error", "The mass is a positive number of kilograms."
    if not str(i["material"]).strip() or not str(i["source_ref"]).strip():
        return "validation_error", "Name the material and the facility's reference."
    if _waiting(c) is None:
        return "conflict", f"{i['case_id']} is not waiting for reporting evidence."
    return None


@implement("case.attachReporting", idem=lambda i, ctx: f"{i['case_id']}:reporting:{i['source_ref']}")  # noqa: ARG005 - the key is the input
def attach(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    s = ctx.session
    c = store.get(s, i["case_id"], for_update=True)
    step = _waiting(c)
    if c is None or step is None:
        raise ActionError("conflict", f"{i['case_id']} is not waiting for reporting evidence.")
    at, ref = ctx.now.isoformat(), str(i["source_ref"]).strip()
    c["evidenceRecords"] = [
        {"type": "case_material_report", "source": ref, "at": at, "result": "pass",
         "value": {"mass_kg": i["mass_kg"], "material": str(i["material"]).strip()}},
        {"type": "treatment_code", "source": ref, "at": at, "result": "pass",
         "value": {"code": str(i["treatment_code"]).strip()}},
        *(c.get("evidenceRecords") or []),
    ]  # fmt: skip
    missing = reporting_missing(s, c)
    if missing:
        step["waiting"] = reporting.waiting_text(missing)
        store.save(s, c)
        return {"case_id": c["id"], "closed": False, "missing": [m.text for m in missing]}
    step["state"] = "done"
    step.pop("waiting", None)
    lifecycle.move(s, c, "closed", f"Reporting evidence received ({ref})", ctx.actor.id)
    q = "SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"
    for (item,) in s.execute(text(q), {"c": c["id"], "t": TYPE}).all():
        process.close_item(s, item, f"Reporting evidence received ({ref})", ctx.actor.id)
    log = f"{c['id']} closed: reporting evidence received ({ref})"
    return {"case_id": c["id"], "closed": True, "source_ref": ref, "log": log}
