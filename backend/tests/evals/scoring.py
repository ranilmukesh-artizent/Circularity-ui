"""Scoring an evaluation report (plan 9, P9-2.15; the F section 8c gates).

    pass_rate(report, kind=None) -> float     percent of the cases (of one `metadata["kind"]`) whose every assertion held;
                                              a case whose task raised counts as failed
    failed(report) -> [str]                   one line per failed case: its name and the evaluators' reasons
    score(reports) -> float                   percent of all cases of all reports that passed (`live.py` writes it to the router)

pydantic-evals 2.73: `Dataset.evaluate_sync(task, ...)` returns an `EvaluationReport` whose `cases` are `ReportCase`s (`name`,
`metadata`, `assertions`: evaluator name -> `EvaluationResult` with `value` and `reason`) and whose `failures` are the cases
whose task raised. Owns: reading a report. Never does: run a task or an evaluator.
"""

from collections.abc import Sequence
from typing import Any

from pydantic_evals.reporting import EvaluationReport


def _kind(metadata: Any) -> str | None:
    return metadata.get("kind") if isinstance(metadata, dict) else None


def _held(case: Any) -> bool:
    return bool(case.assertions) and all(r.value is True for r in case.assertions.values())


def counts(report: EvaluationReport[Any, Any, Any], kind: str | None = None) -> tuple[int, int]:
    """(cases that passed, cases in all) of the kind; a failure of the task is a case that did not pass."""
    cases = [c for c in report.cases if kind is None or _kind(c.metadata) == kind]
    lost = [f for f in report.failures if kind is None or _kind(f.metadata) == kind]
    return sum(_held(c) for c in cases), len(cases) + len(lost)


def pass_rate(report: EvaluationReport[Any, Any, Any], kind: str | None = None) -> float:
    ok, total = counts(report, kind)
    return 100.0 * ok / total if total else 0.0


def failed(report: EvaluationReport[Any, Any, Any]) -> list[str]:
    lines = [
        f"{c.name}: " + "; ".join(f"{k}: {r.reason}" for k, r in c.assertions.items() if r.value is not True)
        for c in report.cases
        if not _held(c)
    ]
    return lines + [f"{f.name}: the task raised {f.error_message}" for f in report.failures]


def score(reports: Sequence[EvaluationReport[Any, Any, Any]]) -> float:
    ok = total = 0
    for r in reports:
        a, b = counts(r)
        ok, total = ok + a, total + b
    return 100.0 * ok / total if total else 0.0
