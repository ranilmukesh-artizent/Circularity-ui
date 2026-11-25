"""The tool fleet case panel's read (plan 9, P9-3.5, story TF-03; later tasks add gates, life, paths, plan, approval).

GET /api/screens/toolfleet/{case_id}
    {case_id, pack_version, flow, grade, gates, life, paths, plan, approval, followThrough}. `grade` is the grade the
    case is valued on and where it came from: `{grade, source: "workbench" | "estimate", ref, at, age_hours}` (the repair
    log's graded record with its test result, else the valuer's own estimate; `tool_inputs.grade_of`). The other fields
    are empty until the tasks that fill them (`gates` [], `life` null, `paths` [], `plan` null, `approval` null,
    `followThrough` null).

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
from di.services.modeler.valuers import tool_inputs


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
        "gates": [],
        "life": None,
        "paths": [],
        "plan": None,
        "approval": None,
        "followThrough": None,
    }
