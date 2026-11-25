# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `analytics` (plan 9, P9-2.1; registry entry I-7): after close, what was predicted against what happened.

Owns: the stage (it runs only when the case is closed, and calls nothing), its output `{predicted_net, actual_net}` once
an outcome is confirmed, and its confidence, 1.0.
Never does: confirm an outcome (`outcome.confirm` is a person's) or learn from it (P9-2.9). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Done, Next
from di.services.agents.stage_context import StageId

ID: StageId = "analytics"
ACTIONS: tuple[str, ...] = ()


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if case.get("stage") != "closed":
        return Done("The case is not closed.", skipped=True)
    return Done("The outcome is compared.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call, nothing to keep."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    return 1.0


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    outcome = case.get("outcome")
    if not outcome:
        return {}
    chosen = case.get("chosen") or case.get("recommendation") or {}
    return {"predicted_net": chosen.get("net"), "actual_net": outcome.get("net")}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []
