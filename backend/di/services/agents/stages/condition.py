# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `condition` (plan 9, P9-2.1; registry entry I-7): the condition and remaining life the case's evidence gives.

Owns: the stage's output `{grade, grade_source, estimate, rul}` from the `grade` and `rul` evidence records (I-3) and its
confidence: 1.0 for a read grade, the estimate's own probability when only an estimate exists (a `grade` record whose
value has `estimate: true` and a `probability`), 0.0 when there is neither.
Never does: call an action, read the clock or fill a missing grade. Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next
from di.services.agents.stage_context import StageId
from di.services.modeler.evidence import Evidence, evidence_of

ID: StageId = "condition"
ACTIONS: tuple[str, ...] = ()


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
