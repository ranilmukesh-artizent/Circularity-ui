# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `follow_through` (plan 9, P9-2.1; registry entry I-7): send again an instruction to a system that failed.

Owns: the step list (`instruction.resend` only when an instruction failed; the runtime puts that fact in the run state
as `failed_instruction`), the stage's output and its confidence, 1.0.
Never does: send a first instruction (approval does) or acknowledge one (only the enterprise system does). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip
from di.services.agents.stage_context import StageId

ID: StageId = "follow_through"
ACTIONS = ("instruction.resend",)


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if n == 0:
        return (
            Call("instruction.resend", {"case_id": case["id"]}) if st.get("failed_instruction") else Skip("no failed instruction")
        )
    return Done("The instructions are followed up.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    if n == 0:
        st["resent"] = True


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    return 1.0


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    return {"resent": bool(st.get("resent"))}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return []
