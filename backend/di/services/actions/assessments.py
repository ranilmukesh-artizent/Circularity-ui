"""The regulatory assessment of planned medical device work (plan 9, P9-12.9, story NS-MED-01).

    assessment.record   act   {case_id, planned_work, result, rationale}   recordAssessment (Admin, Engineer)

A person (clinical engineering) states what the planned refurbishment of a medical capital device is in regulatory terms:
`servicing`, `remanufacturing` or `full_refurbishment`, with the planned work and the rationale. The action stores it as the
compliance evidence `servicing_assessment` of the case's asset (value `{assessment, planned_work, rationale, by}`, the person in
`operator`, the time as `at`; one record per asset, a later one replaces it) and values the case again, so the gate G-MED-1
(`gate_checks.medical.check_regulatory_assessment`) reads it at once: with no assessment, or with remanufacturing or full
refurbishment where the pack lists no manufacturer-status market, `refurbish_resell` stays blocked.

`assessment.record` is in FORBIDDEN_ACTIONS (R7): an agent never records an assessment, whatever the headers say; the
assessment is a person's regulatory judgement. The pipeline refuses another tenant's case. Only a `medical_capital` case takes
it. No model step (R16): the action writes one record. The wording of the gate needs review by Kinective's Legal team before it
is relied on.
"""

from typing import Any

from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key
from di.services.canonical.store import Fact
from di.services.cases import store

TEMPLATE = "medical_capital"
EVIDENCE = "servicing_assessment"
RESULTS = ("servicing", "remanufacturing", "full_refurbishment")

ACTIONS.setdefault(
    "assessment.record",
    ActionDef(
        id="assessment.record", title="Record the regulatory assessment", verb="record assessment",
        desc="Record whether the planned work on a medical device is servicing, remanufacturing or full refurbishment, with the "
        "planned work and the rationale. Only a person records it; an agent never does.",
        risk="act", perm="recordAssessment", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "planned_work": {"req": True, "t": "string"},
            "result": {"req": True, "t": "string"},
            "rationale": {"req": True, "t": "string"},
        },
    ),
)  # fmt: skip


@guard("assessment.record")
def record_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = store.get(ctx.session, i["case_id"])
    if c is None or c.get("template") != TEMPLATE:
        return "not_found", f"No medical capital case {i['case_id']}."
    if i["result"] not in RESULTS:
        return "validation_error", f"Unknown result {i['result']}. Use one of {', '.join(RESULTS)}."
    if not str(i["planned_work"]).strip() or not str(i["rationale"]).strip():
        return "validation_error", "Describe the planned work and give the rationale."
    return None


@implement(
    "assessment.record", idem=lambda i, ctx: f"{i['case_id']}:{i['result']}:{ctx.now.isoformat()}"
)  # a new record each time
def record(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    from di.services.cases import intake  # intake imports the actions layer

    s = ctx.session
    c = store.get(s, i["case_id"], for_update=True)
    if c is None:
        raise ActionError("not_found", f"No medical capital case {i['case_id']}.")
    key = str(c["assetId"])
    row = {
        "asset_key": key, "type": EVIDENCE, "result": "pass", "ref": f"ASM-{c['id']}", "at": ctx.now.isoformat(),
        "operator": ctx.actor.id,
        "value": {"assessment": i["result"], "planned_work": i["planned_work"].strip(), "rationale": i["rationale"].strip(),
                  "by": ctx.actor.id},
    }  # fmt: skip
    canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, EVIDENCE), f, v) for f, v in row.items()])
    intake.revalue(s, c)  # the gate reads the record now
    store.save(s, c)
    return {
        "case_id": c["id"], "result": i["result"],
        "log": f"Assessment recorded for {c['id']}: {i['result']} ({i['planned_work'].strip()})",
    }  # fmt: skip
