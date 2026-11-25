"""The workbench grade of a tool-fleet case (plan 9, P9-3.5, story TF-03): read from the canonical store, set on the case.

    workbench_evidence(s, serial) -> {"workbench_grade": Evidence | None}   the repair log's `condition` record of the serial
    apply(s, case) -> bool                                                   the valuer's grade set from it; True when it changed

The evidence type `workbench_grade` is the pack's `data.mappings` row: canonical model `condition`, key the serial, fields
`grade`, `test_result`, `inspection_ref`, `graded_at`. Its source is whichever source wrote the grade (the repair log,
`repairlog`). Whether the record counts as the workbench grade, and what the valuer then reads, is
`di.services.modeler.valuers.tool_inputs` (pure); this module only reads and writes the case's own fields:
`valuer` (grade, estGrade) and `grade` (what the case shows: the workbench grade, else the estimate).

Never does: grade anything, move a stage or write to the canonical store. A late grade reaches an open case through the
job `case.reevaluate` (canonical.store.apply enqueues it; `replan.on_graded` runs it).
"""

from collections.abc import MutableMapping
from typing import Any, Literal

from sqlalchemy.orm import Session

from di.core import clock
from di.services.canonical import store as canonical
from di.services.cases import life_evidence
from di.services.modeler.evidence import Evidence, parse_time
from di.services.modeler.valuers import tool_inputs

FIELDS = ("grade", "test_result", "inspection_ref", "graded_at")


def workbench_evidence(s: Session, serial: Any) -> dict[str, Evidence | None]:
    """The `condition` record of the serial as `workbench_grade` evidence; None when there is no record or no time."""
    rec = canonical.get(s, "condition", str(serial)) if serial else None
    data = (rec or {}).get("data") or {}
    at = parse_time(data.get("graded_at"))
    if rec is None or at is None or not data.get("grade"):
        return {tool_inputs.WORKBENCH: None}
    rows: list[dict[str, Any]] = rec["provenance"].get("grade") or []
    src = rows[0]["source_id"] if rows else ""
    value = {k: data.get(k) for k in FIELDS}
    result: Literal["pass", "fail"] = "pass" if data.get("test_result") == "pass" else "fail"
    return {tool_inputs.WORKBENCH: Evidence(tool_inputs.WORKBENCH, str(src), at, result, value)}


def apply(s: Session, c: MutableMapping[str, Any]) -> bool:
    """Set the case's valuer grade from the evidence on file (the workbench grade, else its own estimate) and the case's
    `grade` to what it shows. True when either changed. A case without a valuer snapshot is left as it is."""
    if not isinstance(c.get("valuer"), dict):
        return False
    ev = workbench_evidence(s, c.get("serial") or c.get("assetId")) | life_evidence.evidence(s, c)
    vc = tool_inputs.valuer_case(c["valuer"], ev, clock.now())
    shown = vc["grade"] or vc["estGrade"]
    vc["grade"] = shown  # no workbench grade: the snapshot keeps its estimate as grade, as opened
    changed = vc != c["valuer"] or c.get("grade") != shown
    c["valuer"], c["grade"] = vc, shown
    if vc.get("life") is not None:  # the computed life (P9-3.9): what the case shows and the decision records
        c["rul"], c["partRul"], c["life"] = vc["rul"], vc["partRul"], vc["life"]
    return changed
