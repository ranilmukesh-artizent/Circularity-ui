"""Purchase requisition reduction (plan 9, P9-10.16, story TN-19; registry entries I-6, I-10).

    requisition.reduce   act     {case_id, req_id, qty, reason}   cut an open purchase requisition by `qty` in the spares planning
                                                                  system, because the case's reuse route fills the need

Permission `manageRequisitions` (Admin, Planner); the case's tenant boundary applies (scope `case`). The follow-through agent
prepares it when a redeploy or spare route fills a need a requisition covers; it is in HELD_FOR_PERSON, so the hold policy turns
the agent's call into a proposal and a person accepts it (`proposal.accept`), which runs the write as that person. The write is
`POST /requisitions/{req_id}/reduce {qty, reason}` to `tn_spares`, idempotent on the case, requisition and quantity (a repeat
answers the first reply and cuts nothing more).
Never does: close a requisition by itself, choose the quantity, or run for an agent.
"""

from typing import Any

from di.connectors.http import SourceError
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.instructions import writers

ACTIONS.setdefault(
    "requisition.reduce",
    ActionDef(
        id="requisition.reduce", title="Reduce purchase requisition", verb="reduce purchase requisitions",
        desc="Reduce an open purchase requisition in the spares planning system because the case's unit fills the need. "
             "An agent's call is held for a person.",
        risk="act", perm="manageRequisitions", scope="case",
        input={
            "case_id": {"req": True, "t": "string"}, "req_id": {"req": True, "t": "string"},
            "qty": {"req": True, "t": "number"}, "reason": {"req": True, "t": "string"},
        },
        dup_text="This requisition was reduced already",
    ),
)  # fmt: skip


@guard("requisition.reduce")
def reduce_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001 - every guard takes (input, context)
    qty = i.get("qty")
    if not isinstance(qty, int | float) or isinstance(qty, bool) or qty < 1 or int(qty) != qty:
        return "validation_error", "qty must be a whole number, 1 or more."
    if not str(i.get("reason") or "").strip():
        return "validation_error", "A reason is required."
    return None


@implement("requisition.reduce", idem=lambda i, ctx: f"{i['case_id']}:{i['req_id']}:{int(i['qty'])}")  # noqa: ARG005
def reduce(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    qty, key = int(i["qty"]), f"{i['case_id']}:{i['req_id']}:{int(i['qty'])}"
    cl = writers.client(ctx.session, "tn_spares")
    try:
        doc = cl.request(
            "POST",
            f"/requisitions/{i['req_id']}/reduce",
            json={"qty": qty, "reason": i["reason"]},
            headers={"Idempotency-Key": key},
        ).json()
    except SourceError as e:
        raise ActionError("validation_error" if e.kind == "client" else "conflict", str(e)) from e
    finally:
        cl.close()
    return {"case_id": i["case_id"], "req_id": i["req_id"], "reduced_by": qty, "remaining": doc.get("quantity"),
            "status": doc.get("status")}  # fmt: skip
