"""The tool fleet case panel's read (plan 9, P9-3.5, story TF-03; later tasks add gates, life, paths, plan, approval).

GET /api/screens/toolfleet/{case_id}
    {case_id, pack_version, flow, grade, gates, life, paths, plan, approval, followThrough}. `grade` is the grade the
    case is valued on and where it came from: `{grade, source: "workbench" | "estimate", ref, at, age_hours}` (the repair
    log's graded record with its test result, else the valuer's own estimate; `tool_inputs.grade_of`). The other fields
    are empty until the tasks that fill them (`life` null, `paths` [], `plan` null, `approval` null, `followThrough`
    null). `gates` (P9-3.6) is one row for each gate that applies to the case, as its gate step left it: `{id, name,
    passed, reason, guardrail, owner, kind, stage, stageLabel, hold, locked}`; a failed GR-07 (G-CON-2) says the term it
    failed on ("Theft recovered: claim CLM-7781 is open").
    `quarantine` (P9-3.7) is the recall quarantine of the tool, `{recall_id, remedy, blocked, affected_parts, released}`
    (`released`: `{by, at, note}` once Quality released a repair recall), or null when no active recall names its serial.

Refuses as `screens.case.case_page` does: 403 out_of_scope without the case pages, 404 not_found for an unknown case (or a
case of another template), 403 tenant_boundary outside the account's tenants or warehouse.

Facade (frontend/src/api/toolFleet.ts) -> this API
| export | served by |
|---|---|
| toolFleetView | GET /{case_id} |

Never writes. Every write goes through the action pipeline.
"""

import dataclasses
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from di.core import clock
from di.core.auth import Principal
from di.repositories.context import load_case
from di.repositories.packs import active_pack
from di.services.cases import regrade
from di.services.modeler.valuers import fleet_evidence, tool_inputs

GATE_KEYS = ("id", "name", "passed", "reason", "guardrail", "owner", "kind", "stage", "stageLabel", "hold", "locked")


def _gate(row: dict[str, Any]) -> dict[str, Any]:
    """The part of a case's gate row the panel shows."""
    return {k: row.get(k) for k in GATE_KEYS}


def view(s: Session, principal: Principal, case_id: str) -> dict[str, Any]:
    """The panel's read for one tool-fleet case (module docstring)."""
    c = load_case(principal, s, case_id, "product", "case")
    if c.get("template") != "tool_fleet":
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} is not a tool fleet case."})
    valuer = c.get("valuer") or {}
    est = str(valuer.get("estGrade") or c.get("grade") or "C")
    grade = tool_inputs.grade_of(regrade.workbench_evidence(s, c.get("serial") or c["assetId"]), est, now=clock.now())
    return {
        "case_id": case_id,
        "pack_version": active_pack(s, "tool_fleet", c["owner"]).version,
        "flow": c.get("flow") or "returns",
        "grade": dataclasses.asdict(grade),
        "gates": [_gate(g) for g in c.get("gates") or []],
        "quarantine": fleet_evidence.quarantine_of(c),
        "life": None,
        "paths": [],
        "plan": None,
        "approval": None,
        "followThrough": None,
    }
