"""Lifecycle action (plan 9, P9-2.20; registry entries I-1 and I-20): the transit stage's one write.

    transit.flagDelay   act   {case_id, eta}   a returned asset's shipment is past its ETA with no goods receipt: opens one
                                                "Transit delayed" exception item for the Planner (`process.open_item`)

The item is deduped per case: while one is open for the case the action returns it and opens no second. It only adds an item
for a person; nothing is deleted, approved or released (R16, golden rule 10). Owns: the action and `TYPE`.
Never does: close the item (a person does, `work.resolve`), read the shipment (the stage did) or touch the case.
"""

from typing import Any

from sqlalchemy import text

from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, implement
from di.services.cases import process, store

TYPE = "transit_delayed"
TITLE = "Transit delayed"
OPEN = text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open' ORDER BY id LIMIT 1")

ACTIONS.setdefault(
    "transit.flagDelay",
    ActionDef(
        id="transit.flagDelay", title="Flag a delayed shipment", verb="flag delayed shipments",
        desc="Open one exception item for the Planner when a returned asset's shipment is past its ETA with no goods receipt.",
        risk="act", perm=None, scope="case",
        input={"case_id": {"req": True, "t": "string"}, "eta": {"req": True, "t": "string"}},
    ),
)  # fmt: skip


@implement("transit.flagDelay")
def flag_delay(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"])
    if c is None:
        raise ActionError("not_found", f"No live case {i['case_id']}.")
    existing = ctx.session.execute(OPEN, {"c": c["id"], "t": TYPE}).scalar()
    if existing is not None:
        return {"case_id": c["id"], "item": int(existing), "opened": False, "log": f"{c['id']} already has a transit item"}
    item = process.open_item(
        ctx.session, kind="exception", case_id=c["id"], org_unit_id=c["owner"], type=TYPE, title=TITLE,
        cause=f"The shipment was due {i['eta']} and no goods receipt is on file.", action="Chase the carrier or find the goods",
        owner_role="Planner", due_hours=process.sla_hours(ctx.session, c["id"], TYPE), by=ctx.preparer or ctx.actor.id,
    )  # fmt: skip
    return {"case_id": c["id"], "item": item, "opened": True, "log": f"Flagged {c['id']}: transit delayed"}
