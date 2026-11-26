"""The workbench grade of a tool-fleet case (plan 9, P9-3.5, story TF-03): read from the canonical store, set on the case.

    workbench_evidence(s, serial) -> {"workbench_grade": Evidence | None}   the repair log's `condition` record of the serial
    apply(s, case) -> bool                                                   the valuer's grade set from it; True when it changed

The evidence type `workbench_grade` is the pack's `data.mappings` row: canonical model `condition`, key the serial, fields
`grade`, `test_result`, `inspection_ref`, `graded_at`. Its source is whichever source wrote the grade (the repair log,
`repairlog`). Whether the record counts as the workbench grade, and what the valuer then reads, is
`di.services.modeler.valuers.tool_inputs` (pure); this module only reads and writes the case's own fields:
`valuer` (grade, estGrade) and `grade` (what the case shows: the workbench grade, else the estimate).

`apply` also keeps `disagreement` on the case ({text, components}, P9-3.11: the workbench grade against the wear index,
`tool_life.disagreement`; the condition record's `damage_code` says the tool is damaged), or removes it. The exception item it
opens is `gate_hold.sync_item`.

Never does: grade anything, fit a model (only the active `rated_life` model is read), move a stage or write to the canonical
store. A late grade reaches an open case through the job `case.reevaluate` (canonical.store.apply enqueues it;
`replan.on_graded` runs it).
"""

from collections.abc import Mapping, MutableMapping
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.canonical import store as canonical
from di.services.cases import life_evidence
from di.services.modeler.evidence import Evidence, parse_time
from di.services.modeler.valuers import tool_inputs, tool_life
from di.services.models.rul import RulModel

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
    vc = tool_inputs.valuer_case(c["valuer"], ev, clock.now(), _rul_model(s, str(c.get("cls") or "")))
    shown = vc["grade"] or vc["estGrade"]
    vc["grade"] = shown  # no workbench grade: the snapshot keeps its estimate as grade, as opened
    changed = vc != c["valuer"] or c.get("grade") != shown
    c["valuer"], c["grade"] = vc, shown
    if vc.get("life") is not None:  # the computed life (P9-3.9): what the case shows and the decision records
        c["rul"], c["partRul"], c["life"] = vc["rul"], vc["partRul"], vc["life"]
    before = c.get("disagreement")
    _sync_disagreement(s, c, ev)
    return changed or before != c.get("disagreement")


def _sync_disagreement(s: Session, c: MutableMapping[str, Any], ev: Mapping[str, Evidence | None]) -> None:
    """`c["disagreement"]` is the telematics-against-grade disagreement of the case, or absent (an estimate never triggers it)."""
    c.pop("disagreement", None)
    if not isinstance(c.get("life"), dict):
        return
    grade = tool_inputs.grade_of(ev, str(c["valuer"].get("estGrade") or "C"))
    damage = bool(
        ((canonical.get(s, "condition", str(c.get("serial") or c.get("assetId"))) or {}).get("data") or {}).get("damage_code")
    )
    d = tool_life.disagreement(grade, tool_life.life_from_dict(c["life"]), damage)
    if d is not None:
        c["disagreement"] = {"text": d.text, "components": d.components}


def _rul_model(s: Session, cls: str) -> RulModel | None:
    """The promoted remaining-life model (kind `rated_life`) of the tool class, or None: the pack's table then rates the life
    (P9-3.10). A stored model, so the case's life is the same every time it is computed until a person promotes another."""
    row = s.execute(
        text("SELECT id, factors FROM model_version WHERE template = 'tool_fleet' AND kind = 'rated_life' AND status = 'active'")
    ).first()
    return RulModel.for_class(row.factors, cls, row.id) if row else None
