# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `reconcile` (plan 9, P9-2.21; registry entry I-7; journey stage 10): predicted against actual, line by line.

Owns: the stage's output once the outcome is confirmed, all of it computed here (a model only explains it, R16, through the
stage reasoner):
    lines        `[{item, predicted, actual, delta}]`, one per cost line of the chosen route (else the recommendation) and
                 per confirmed line, `delta` = actual - predicted; a line the outcome does not report has `actual` and `delta`
                 null, a reported line the valuation did not predict has `predicted` and `delta` null
    open_items   the labels of the lines with no actual: carried forward
    net          `{predicted, actual, delta}`
    learning_id  `LR-<case id>`: the learning record is this stage's record (`agent_stage_record`), which sits beside the
                 confirmed outcome that the outcome dataset (`di.repositories.outcomes`) and the calibrations learn from
A case with no confirmed outcome is skipped ("no outcome to reconcile"), with an empty output.
Never does: call an action, confirm an outcome or invent a figure. Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next
from di.services.agents.stage_context import StageId
from di.services.agents.stages.outcome import confirmed

ID: StageId = "reconcile"
ACTIONS: tuple[str, ...] = ()


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if confirmed(case) is None:
        return Done("No outcome to reconcile.", skipped=True)
    return Done("Predicted and actual are compared.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call, nothing to keep."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    return 1.0 if confirmed(case) is not None else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _delta(predicted: float | None, actual: float | None) -> float | None:
    return None if predicted is None or actual is None else round(actual - predicted, 2)


def lines_of(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The predicted terms of the route that was executed against the confirmed lines, by label, in route order."""
    out = confirmed(case)
    if out is None:
        return []
    route = case.get("chosen") or case.get("recommendation") or {}
    terms = [t for t in route.get("terms") or [] if isinstance(t, Mapping) and "label" in t]
    predicted = {str(t["label"]): _num(t.get("amt")) for t in terms}
    reported = [ln for ln in out.get("lines") or [] if isinstance(ln, Mapping) and "label" in ln]
    actual = {str(ln["label"]): _num(ln.get("act")) for ln in reported}
    items = [*predicted, *(k for k in actual if k not in predicted)]
    return [
        {"item": k, "predicted": predicted.get(k), "actual": actual.get(k), "delta": _delta(predicted.get(k), actual.get(k))}
        for k in items
    ]  # fmt: skip


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    out = confirmed(case)
    if out is None:
        return {}
    lines = lines_of(case)
    route = case.get("chosen") or case.get("recommendation") or {}
    predicted, actual = _num(route.get("net")), _num(out.get("net"))
    return {
        "lines": lines,
        "open_items": [ln["item"] for ln in lines if ln["actual"] is None],
        "net": {"predicted": predicted, "actual": actual, "delta": _delta(predicted, actual)},
        "learning_id": f"LR-{case['id']}",
    }  # fmt: skip


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []
