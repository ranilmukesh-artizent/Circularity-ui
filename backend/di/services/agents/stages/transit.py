# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `transit` (plan 9, P9-2.20; registry entry I-7; journey stage 3, "Pickup and transit"): the pickup date, the ETA, the
freight cost and the carrier, from the shipment record, until the goods are received.

Owns: the step list, the stage's output `{pickup_on, eta, freight_cost, carrier, delayed}` and its confidence (fields found
over the four read ones):
    0 transit.flagDelay  only when the ETA is before the workspace clock (`st["now"]`, put there by the runtime) and there is no
                         goods receipt: one "Transit delayed" exception item for the Planner (the action dedupes per case)
    1 wait or done       `Wait("transit")` until a `goods_receipt` record is on the case; the receipt landing wakes the run
                         (`lifecycle_evidence.wake_transit`, as `resume_waiting` does for approvals), then `Done`
A case with none of the lifecycle records is skipped with the reason "not a lease return", with no call.
Never does: write anything itself (the runtime runs the calls), read a clock or delete or approve (R16). Pure.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip, Wait
from di.services.agents.stage_context import StageId
from di.services.agents.stages import lifecycle
from di.services.modeler.evidence import evidence_of, parse_time

ID: StageId = "transit"
ACTIONS = ("case.get", "case.evidence", "transit.flagDelay")
FIELDS = ("pickup_on", "eta", "freight_cost", "carrier")


def received(case: Mapping[str, Any]) -> bool:
    return evidence_of(case, "goods_receipt") is not None


def _eta(case: Mapping[str, Any]) -> tuple[Any, datetime | None]:
    raw = lifecycle.fields_of(case, "shipment", ("eta",))["eta"]
    return raw, parse_time(raw)


def delayed(st: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    """The ETA is before the workspace clock and no goods receipt is on file."""
    eta, now = _eta(case)[1], parse_time(st.get("now"))
    return eta is not None and now is not None and eta < now and not received(case)


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if not lifecycle.is_lease_return(case):
        return Done(lifecycle.NOT_A_LEASE_RETURN, skipped=True)
    if received(case):
        return Done("The goods are received.")
    if n == 0:
        if delayed(st, case):
            return Call("transit.flagDelay", {"case_id": case["id"], "eta": str(_eta(case)[0])})
        return Skip("not delayed")
    return Wait("transit")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call changes what the stage knows: the records are on the case."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    if not lifecycle.is_lease_return(case):
        return None
    return lifecycle.share(list(lifecycle.fields_of(case, "shipment", FIELDS).values()))


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    if not lifecycle.is_lease_return(case):
        return lifecycle.skipped_output()
    return {**lifecycle.fields_of(case, "shipment", FIELDS), "delayed": delayed(st, case)}


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return lifecycle.sources_of(case, ("shipment",))
