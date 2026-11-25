# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `intake` (plan 9, P9-2.1; registry entry I-7): read the case's evidence and ask for what is missing.

Owns: the intake step list (`case.evidence` read, then `evidence.request` only when an item is not ready), the stage's
output and its confidence (ready items over all items, 1.0 when there are none).
Never does: write anything itself (the runtime runs the calls), approve or decide. Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip
from di.services.agents.stage_context import StageId

ID: StageId = "intake"
ACTIONS = ("case.evidence", "evidence.request")


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    cid = {"case_id": case["id"]}
    if n == 0:
        return Call("case.evidence", cid)
    if n == 1:
        return Call("evidence.request", cid) if st.get("missing") else Skip("no evidence missing")
    return Done("The evidence is read.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """What `case.evidence` says: whether anything is missing, and the sources of the items that are ready."""
    if n != 0:
        return
    items = output.get("items") or []
    st["missing"] = any(e.get("state") != "ready" for e in items)
    st["evidence_sources"] = [
        {"fact": e.get("label"), "source": e.get("system") or e.get("source"), "at": e.get("fetched")}
        for e in items
        if e.get("state") == "ready"
    ]


def _items(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [e for e in case.get("evidence") or [] if isinstance(e, Mapping)]


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    items = _items(case)
    return sum(1 for e in items if e.get("state") == "ready") / len(items) if items else 1.0


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    items = _items(case)
    return {
        "items": len(items),
        "ready": sum(1 for e in items if e.get("state") == "ready"),
        "missing": [str(e.get("label") or e.get("k")) for e in items if e.get("state") != "ready"],
    }


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(st.get("evidence_sources") or [])
