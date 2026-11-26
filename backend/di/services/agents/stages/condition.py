# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `condition` (plan 9, P9-2.1; registry entry I-7): the condition and remaining life the case's evidence gives.

Owns: the stage's output `{grade, grade_source, estimate, rul}` from the `grade` and `rul` evidence records (I-3) and its
confidence: 1.0 for a read grade, the estimate's own probability when only an estimate exists (a `grade` record whose
value has `estimate: true` and a `probability`), 0.0 when there is neither.
Never does: call an action, read the clock or fill a missing grade. Pure.

Used cars (plan 9, P9-9.7, stories UC-09 and UC-05): `read_grade` makes the `grade` evidence record of a car from the
inspection read through the pack's grade mapping (`grades.map_from`, the score 1-5 to A-D). An inspection that is missing,
`scheduled` or has a score the mapping does not know gives an estimate instead (`estimate: true`, the grade from the
mileage, source labelled `estimate`) with the probability `ESTIMATE_CAP` (0.70), below the pack's 0.75, so the stage
confidence holds the decision with the reason `confidence`. `cases.intake` writes the record; this module only builds it.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next
from di.services.agents.stage_context import StageId
from di.services.modeler.evidence import Evidence, evidence_of

ID: StageId = "condition"
ACTIONS: tuple[str, ...] = ()

ESTIMATE_CAP = 0.70  # how far an estimated grade is trusted: below the pack's 0.75 threshold
ESTIMATE_SOURCE = "estimate"  # the label of an estimated grade's source
# the estimate's mileage bands (a rule of thumb until a model exists): up to the miles, the grade; beyond them D
ESTIMATE_BANDS = ((30000, "B"), (60000, "C"))


def _number(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def estimate_grade(mileage: Any) -> str:
    """The grade a car is estimated at without an inspection, from its mileage (C when the mileage is not known)."""
    miles = _number(mileage)
    if miles is None:
        return "C"
    return next((g for limit, g in ESTIMATE_BANDS if miles <= limit), "D")


def read_grade(map_from: Mapping[str, str], inspection: Mapping[str, Any] | None, mileage: Any, now: datetime) -> dict[str, Any]:
    """The `grade` evidence record of a car. `inspection` is `{status, score, at, source}` as the inspection source gave it
    (None: no inspection). A `complete` inspection with a score the pack's mapping knows is read: the mapped grade, the
    inspection's source and time. Anything else is an estimate from the mileage at `now`, labelled so."""
    score = _number((inspection or {}).get("score"))
    grade = map_from.get(str(int(round(score)))) if score is not None else None
    if inspection and inspection.get("status") == "complete" and grade:
        return {
            "type": "grade", "source": str(inspection.get("source") or ""), "at": inspection.get("at") or now.isoformat(),
            "result": "pass", "value": {"grade": grade, "estimate": False, "score": score},
        }  # fmt: skip
    return {
        "type": "grade", "source": ESTIMATE_SOURCE, "at": now.isoformat(), "result": "pass",
        "value": {"grade": estimate_grade(mileage), "estimate": True, "probability": ESTIMATE_CAP},
    }  # fmt: skip


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    return Done("The condition is read.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call, nothing to keep."""


def _grade(case: Mapping[str, Any]) -> tuple[Evidence | None, bool]:
    e = evidence_of(case, "grade")
    return e, bool(e is not None and e.value.get("estimate"))


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    e, estimate = _grade(case)
    if e is None:
        return 0.0
    if not estimate:
        return 1.0
    p = e.value.get("probability")
    return float(p) if isinstance(p, int | float) and not isinstance(p, bool) else 0.0


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    e, estimate = _grade(case)
    rul = evidence_of(case, "rul")
    return {
        "grade": e.value.get("grade") if e else None,
        "grade_source": e.source if e else None,
        "estimate": estimate,
        "rul": dict(rul.value) if rul else None,
    }


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    found = (("Grade", evidence_of(case, "grade")), ("Remaining life", evidence_of(case, "rul")))
    return [{"fact": name, "source": e.source, "at": e.at.isoformat()} for name, e in found if e is not None]
