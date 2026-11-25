"""The tool-fleet valuer's case from the evidence on file (plan 9, P9-3.5, story TF-03). Pure.

    grade_of(evidence, est_grade, now=None) -> GradeView        the grade a case shows and where it came from
    valuer_case(base, evidence) -> dict                         the `tool_fleet` valuer case with that grade set

The evidence is a mapping of evidence type to the newest record on file, or None (`workbench_grade`, from the repair log's
`condition` record of the serial, di.services.cases.regrade). Later tasks extend `valuer_case` (life, demand).

- **Workbench grade.** A `workbench_grade` record whose `grade` is set and whose `test_result` is not null. The valuer
  then reads `grade` as it always did.
- **Estimate.** Anything else, including a grade still in progress (no test result): `grade` is left None and `estGrade`
  keeps the valuer's own estimate, which `tool_fleet._grade()` already falls back to. The panel labels it an estimate.

Never does: compute a grade (A 1.5), read the database, the clock (the modeler is pure) or write anything. The caller
passes `now`; without it `age_hours` is None. Implements no registry entry; the evidence type is the pack's `data.mappings` row.
"""

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from di.services.modeler.evidence import Evidence

WORKBENCH = "workbench_grade"


@dataclass(frozen=True)
class GradeView:
    grade: str
    source: Literal["workbench", "estimate"]
    ref: str | None
    at: str | None
    age_hours: float | None


def _workbench(evidence: Mapping[str, Evidence | None]) -> Evidence | None:
    """The workbench grade record when it counts: a grade and a test result."""
    e = evidence.get(WORKBENCH)
    if e is None or not e.value.get("grade") or e.value.get("test_result") is None:
        return None
    return e


def grade_of(evidence: Mapping[str, Evidence | None], est_grade: str, now: datetime | None = None) -> GradeView:
    """The workbench grade with its reference and age, else the estimate."""
    e = _workbench(evidence)
    if e is None:
        return GradeView(est_grade, "estimate", None, None, None)
    age = None if now is None else round(max((now - e.at).total_seconds() / 3600, 0.0), 1)
    ref = e.value.get("inspection_ref")
    return GradeView(str(e.value["grade"]), "workbench", str(ref) if ref else None, e.at.isoformat(), age)


def valuer_case(base: Mapping[str, Any], evidence: Mapping[str, Evidence | None]) -> dict[str, Any]:
    """`base` (the valuer case as opened) with `grade` the workbench grade, or None with `estGrade` the estimate."""
    c = copy.deepcopy(dict(base))
    est = str(c.get("estGrade") or c.get("grade") or "C")
    g = grade_of(evidence, est)
    c["estGrade"] = est
    c["grade"] = g.grade if g.source == "workbench" else None
    return c
