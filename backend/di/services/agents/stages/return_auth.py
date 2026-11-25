# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `return_auth` (plan 9, P9-2.20; registry entry I-7; journey stage 2, "Return authorised"): the return authorisation's
number, fees, replacement order, book value and acquisition date, from the return-authorisation record.

Owns: the step list, the stage's output `{ra_number, fees, replacement_order, book_value, acquired_on}` and its confidence
(fields found over the five required):
    0 case.evidence     read
    1 evidence.request  only when a field is missing and the case has something to ask for (`lifecycle.can_request`)
    2 done
A case with none of the lifecycle records is skipped with the reason "not a lease return", with no call.
Never does: write anything itself (the runtime runs the calls), compute a value or delete or approve (R16). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip
from di.services.agents.stage_context import StageId
from di.services.agents.stages import lifecycle

ID: StageId = "return_auth"
ACTIONS = ("case.get", "case.evidence", "evidence.request")
FIELDS = ("ra_number", "fees", "replacement_order", "book_value", "acquired_on")


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if not lifecycle.is_lease_return(case):
        return Done(lifecycle.NOT_A_LEASE_RETURN, skipped=True)
    cid = {"case_id": case["id"]}
    if n == 0:
        return Call("case.evidence", cid)
    if n == 1:
        missing = confidence(st, case) != 1.0
        return Call("evidence.request", cid) if missing and lifecycle.can_request(case) else Skip("nothing to request")
    return Done("The return authorisation is read.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call changes what the stage knows: the records are on the case."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    if not lifecycle.is_lease_return(case):
        return None
    return lifecycle.share(list(lifecycle.fields_of(case, "return_authorisation", FIELDS).values()))


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    if not lifecycle.is_lease_return(case):
        return lifecycle.skipped_output()
    return lifecycle.fields_of(case, "return_authorisation", FIELDS)


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return lifecycle.sources_of(case, ("return_authorisation",))
