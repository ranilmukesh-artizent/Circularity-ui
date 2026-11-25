# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `intake` (plan 9, P9-2.1 and P9-2.11; registry entries I-7 and I-1): read the case's evidence, ask for what is
missing, and hold a case whose fraud score reaches the pack's threshold.

Owns: the intake step list, the stage's output and its confidence (ready items over all items, 1.0 when there are none):
    0 case.evidence     read; notes whether an item is not ready
    1 evidence.request  only when an item is not ready
    2 fraud.hold        only when the triage (`st["fraud"]`, set by the runtime from di.services.actions.fraud.triage_case) says
                        held and the case has no fraud record yet; the stage then waits for a person
    3 wait or done      `Wait("fraud")` (status `held`) while the case's fraud record is `held`; `fraud.release` wakes the run
Never does: write anything itself (the runtime runs the calls), release or reject (only a person does, FORBIDDEN_ACTIONS),
approve or decide. Pure. R20: the fraud hold is an intake gate, before valuation.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip, Wait
from di.services.agents.stage_context import StageId

ID: StageId = "intake"
ACTIONS = ("case.evidence", "evidence.request", "fraud.hold")
HOLD_FIELDS = ("score", "signals", "rule_version", "threshold")


def _on_hold(case: Mapping[str, Any]) -> bool:
    f = case.get("fraud")
    return isinstance(f, Mapping) and f.get("status") == "held"


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    cid = {"case_id": case["id"]}
    if n == 0:
        return Call("case.evidence", cid)
    if n == 1:
        return Call("evidence.request", cid) if st.get("missing") else Skip("no evidence missing")
    if n == 2:
        fraud = st.get("fraud")
        if not fraud or not fraud.get("held") or case.get("fraud"):
            return Skip("no fraud hold")
        return Call("fraud.hold", cid | {k: fraud[k] for k in HOLD_FIELDS})
    return Wait("fraud") if _on_hold(case) else Done("The evidence is read.")


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
    out: dict[str, Any] = {
        "items": len(items),
        "ready": sum(1 for e in items if e.get("state") == "ready"),
        "missing": [str(e.get("label") or e.get("k")) for e in items if e.get("state") != "ready"],
    }
    if st.get("fraud"):  # the pack has fraud rules: what the triage said, held or not
        out["fraud"] = {k: st["fraud"][k] for k in ("score", "threshold", "rule_version", "held")}
    return out


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    fired = [
        {"fact": f"Fraud signal {sig['id']}", "source": sig.get("source"), "at": sig.get("at")}
        for sig in (st.get("fraud") or {}).get("signals") or []
    ]
    return [*(st.get("evidence_sources") or []), *fired]
