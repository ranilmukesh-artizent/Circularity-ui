"""Safety recall quarantine (plan 9, P9-3.7, story TF-04): a person releases a recalled tool after the fix.

    recall.release   commit   {case_id, note}   releaseQuarantine (Approver, Admin): records who released the tool and why
                                                 and values the case again

A tool whose serial an active `repair` recall names is quarantined by the gate GR-12 (`G-TOOL-REC`): release, redeploy and
resell are blocked (`fleet_evidence.recall_check`). `recall.release` records `case["recallRelease"] = {recall_id, by, at, note}`
and re-evaluates the case, so the gate passes and the quarantine item for Quality closes. It is refused with `conflict` when the
case has no quarantine, and for a `replace` or `refund` recall: "A replace or refund recall is never released to the fleet".

`recall.release` is in `FORBIDDEN_ACTIONS` (di.services.agents.forbidden): no agent releases a quarantine, however the call
arrives (golden rule 10, R21). Maker-checker does not apply: it releases a block, nobody "made" it; the journal keeps who and why.
No model step: the action reads a record and writes one.
"""

from typing import Any

from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import intake, process, store
from di.services.modeler.valuers import fleet_evidence

NEVER = "A replace or refund recall is never released to the fleet"
_NOTE = {
    "req": True,
    "t": "string",
    "min": 10,
    "minText": "Add a note of at least 10 characters: what was fixed, and who checked.",
}

ACTIONS.setdefault(
    "recall.release",
    ActionDef(
        id="recall.release", title="Release a recalled tool from quarantine", verb="release recalled tools from quarantine",
        desc="Release a tool whose repair recall is done, with a note that stays on the record. "
        "A replace or refund recall is never released.",
        risk="commit", perm="releaseQuarantine", scope="case", input={"case_id": {"req": True, "t": "string"}, "note": _NOTE},
    ),
)  # fmt: skip


def _quarantine(case: dict[str, Any] | None, case_id: str) -> tuple[dict[str, Any] | None, tuple[str, str] | None]:
    if case is None or case.get("template") != "tool_fleet":
        return None, ("not_found", f"No live tool fleet case {case_id}.")
    q = fleet_evidence.quarantine_of(case)
    if q is None or q["released"] is not None:
        return None, ("conflict", f"{case_id} is not quarantined by a safety recall.")
    if q["remedy"] != "repair":
        return None, ("conflict", NEVER)
    if case.get("stage") not in process.HELD_STAGES:
        return None, ("conflict", f"{case_id} is past approval; the recall is released on a case still to be decided.")
    return q, None


@guard("recall.release")
def release_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    return _quarantine(store.get(ctx.session, i["case_id"]), i["case_id"])[1]


@implement("recall.release")
def release(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"], for_update=True)
    q, refused = _quarantine(c, i["case_id"])
    if refused or c is None or q is None:
        raise ActionError(*(refused or ("not_found", f"No live case {i['case_id']}.")))
    c["recallRelease"] = {"recall_id": q["recall_id"], "by": ctx.actor.id, "at": ctx.now.isoformat(), "note": i["note"].strip()}
    intake.revalue(ctx.session, c)  # the gate passes now: the quarantine item closes, the blocked routes are valued again
    store.save(ctx.session, c)
    return {
        "case_id": c["id"], "released": True, "recall_id": q["recall_id"],
        "log": f"Released {c['id']} from quarantine (recall {q['recall_id']}): {i['note'].strip()}",
    }  # fmt: skip
