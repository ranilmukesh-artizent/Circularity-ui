"""The job `queue.plan {pack, org_unit_id}` (plan 9, P9-2.8; registry entries I-5 and I-7): the fan-in of the Disposition
stage's queue wait.

    plan(s, pack, org_unit_id) -> [run ids woken]

Every case of the pack in the org that reaches Disposition waits `queue` and enqueues this job with the dedupe key
`queue.plan:<pack>:<org_unit_id>`, so one run of it plans them all (no join inside the runtime). It values the org's open
cases again with the queue as it is now (`cases.replan.on_opened`, the planner of I-5), writes each case's `queuePlan`
(`route`, `plan`: the planned route's id and name; `holds`, `contested`, `lost`, `kinds` from `replan.queue_plan`; and
`reason`: why this return lost an order, else why it takes its route), then `runtime.wake_queue`. The woken run's next
step submits the case as planned.
Never does: approve or move a case to another stage, or plan a pack that has no queue planner.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.agents import runtime
from di.services.cases import replan, store
from di.services.modeler.pack import load_pack

__all__ = ["plan"]


def _reason(qp: dict[str, Any], rec: dict[str, Any] | None) -> str:
    if qp["lost"]:
        x = qp["lost"][0]
        return f"{x['order']} goes to {x['to']}, where it adds more across the queue."
    why = str((rec or {}).get("why") or "")
    if qp["holds"]:
        return f"Holds {qp['holds']}. {why}".strip()
    return why or "No order is free for this return."


def plan(s: Session, pack: str, org_unit_id: str) -> list[str]:
    """Plan the pack's open queue of the org, record each case's place in it and wake the runs waiting for it."""
    if load_pack(pack).valuer.kind != "tool_fleet":  # the one pack kind with a queue planner today (engine.queue.planner_for)
        raise ValueError(f"the pack {pack} has no queue planner")
    replan.on_opened(s, org_unit_id)
    q = text("SELECT id FROM case_record WHERE owner = :o AND stage = ANY(:st) AND data ->> 'template' = :p ORDER BY id")
    for cid in list(s.execute(q, {"o": org_unit_id, "st": list(replan.REPLANNED), "p": pack}).scalars()):
        c = store.get(s, cid, for_update=True)
        if c is None:
            continue
        qp = replan.queue_plan(s, c) or {"holds": None, "contested": [], "lost": [], "kinds": {}}
        rec = c.get("recommendation")
        c["queuePlan"] = qp | {"route": (rec or {}).get("id"), "plan": (rec or {}).get("plan"), "reason": _reason(qp, rec)}
        store.save(s, c)
    return runtime.wake_queue(s, pack, org_unit_id)
