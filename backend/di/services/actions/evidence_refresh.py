"""Re-run one piece of evidence of a case at its source (plan 9, P9-9.9, story UC-08).

    evidence.refresh  act  {case_id, evidence_type}  perm openCases, scope case
        -> {case_id, evidence_type, checked_at}

The pack's data part says which source answers an evidence type (`mappings` of kind `evidence`: `recall_check` is the recall
database `uc_recall`). The action calls that adapter's module function `lookup(client, vin, org_unit_id)` (only an adapter that
has one; any other type or source answers `not_supported`), writes the facts it returns to the canonical store with the
adapter's source and values the case again through the one decider (`intake.revalue`, so `decide_case`): the stale-check gate
then reads the new date. A case that was held and now clears is released as `gate_hold.recheck` releases it.

An agent may prepare it (`agent_mode` yes): it reads a registry and re-evaluates, and it never clears, waives or approves a
gate: a gate clears only on new evidence, and what releases a hold stays a person's (`forbidden.py`). It never changes an
approved decision: a case past approval answers `decided`. The lookup is the adapter's own read-only call; nothing is written
to the source. Rules the evidence feeds are legal text; Kinective's Legal team reviews them before they are relied on.
"""

import sys
from typing import Any

from di.connectors.connection import client_for
from di.connectors.registry import ADAPTERS
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.canonical import store as canonical
from di.services.cases import intake, lifecycle, process, store
from di.services.modeler.evidence import label_of

_STR = {"req": True, "t": "string"}
ACTIONS.setdefault(
    "evidence.refresh",
    ActionDef(
        id="evidence.refresh", title="Re-check evidence", verb="re-check evidence",
        desc="Run a case's evidence check again at its source system (a recall check on the car's VIN) and value the case "
        "again with the new result. Changes no approved decision and clears no gate by itself.",
        risk="act", perm="openCases", scope="case", input={"case_id": _STR, "evidence_type": _STR},
    ),
)  # fmt: skip


def _source_of(case_id: str, evidence_type: str, ctx: CallContext) -> str | None:
    """The source the case's pack names for the evidence type, when its adapter has a `lookup`."""
    pack = process.pack_of(ctx.session, case_id)
    for m in pack.data.mappings:
        if m.get("kind") == "evidence" and m.get("evidence_type") == evidence_type and m.get("source") in ADAPTERS:
            return str(m["source"]) if hasattr(sys.modules[type(ADAPTERS[m["source"]]).__module__], "lookup") else None
    return None


@guard("evidence.refresh")
def refresh_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = store.get(ctx.session, i["case_id"])
    if c is None:
        return "not_found", f"No case {i['case_id']}."
    if c.get("stage") not in process.HELD_STAGES:
        return "decided", f"{c['id']} is past approval; its evidence is not re-checked and the decision does not change."
    if _source_of(c["id"], i["evidence_type"], ctx) is None:
        return "not_supported", f"{label_of(i['evidence_type'])} cannot be re-checked at a source."
    return None


@implement("evidence.refresh")
def refresh(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"], for_update=True)
    source = _source_of(i["case_id"], i["evidence_type"], ctx)
    if c is None or source is None:
        raise ActionError("not_supported", f"{label_of(i['evidence_type'])} cannot be re-checked at a source.")
    adapter = ADAPTERS[source]
    vin = str((c.get("vehicle") or {}).get("vin") or "")
    if not vin:
        raise ActionError("not_supported", f"{c['id']} has no VIN to look up.")
    lookup = sys.modules[type(adapter).__module__].lookup
    facts = lookup(client_for(ctx.session, source, adapter), vin, c.get("owner"))
    canonical.apply(ctx.session, source, facts)
    checked = next((str(f.value) for f in facts if f.field.endswith("_checked_at") and f.value), ctx.now.isoformat())
    was_held = isinstance(c.get("gateHold"), dict)
    intake.revalue(ctx.session, c)
    if was_held and c.get("gateHold") is None:
        lifecycle.move(
            ctx.session, c, "awaiting_approval" if c.get("recommendation") else "none",
            f"Released: {label_of(i['evidence_type'])} re-checked", ctx.actor.id,
        )  # fmt: skip
    else:
        store.save(ctx.session, c)
    return {"case_id": c["id"], "evidence_type": i["evidence_type"], "checked_at": checked}
