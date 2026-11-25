# ruff: noqa: ARG001 - every stage module has the same function signatures (stages/__init__.py StageModule)
"""Stage `lease_end` (plan 9, P9-2.20; registry entry I-7; journey stage 1, "Lease ends"): the serial, model, site, usage, the
customer's intent and the lease's end and terms, from the lease record and the customer-intent record.

Owns: the step list, the stage's output `{serial, model, site, usage, intent, lease_end, terms}` and its confidence (fields
found over the seven required):
    0 case.evidence     read
    1 evidence.request  only when a field is missing and the case has something to ask for (`lifecycle.can_request`)
    2 done
A case with none of the lifecycle records is skipped with the reason "not a lease return", with no call.
Never does: write anything itself (the runtime runs the calls) or delete or approve (R16). Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import Call, Done, Next, Skip
from di.services.agents.stage_context import StageId
from di.services.agents.stages import lifecycle

ID: StageId = "lease_end"
ACTIONS = ("case.get", "case.evidence", "evidence.request")
LEASE_FIELDS = ("serial", "model", "site", "usage", "lease_end", "terms")
ORDER = ("serial", "model", "site", "usage", "intent", "lease_end", "terms")


def _fields(case: Mapping[str, Any]) -> dict[str, Any]:
    lease = lifecycle.fields_of(case, "lease_record", LEASE_FIELDS)
    lease["intent"] = lifecycle.fields_of(case, "customer_intent", ("intent",))["intent"]
    return {k: lease[k] for k in ORDER}


def next_call(n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next:
    if not lifecycle.is_lease_return(case):
        return Done(lifecycle.NOT_A_LEASE_RETURN, skipped=True)
    cid = {"case_id": case["id"]}
    if n == 0:
        return Call("case.evidence", cid)
    if n == 1:
        missing = confidence(st, case) != 1.0
        return Call("evidence.request", cid) if missing and lifecycle.can_request(case) else Skip("nothing to request")
    return Done("The lease is read.")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """No call changes what the stage knows: the records are on the case."""


def confidence(st: dict[str, Any], case: Mapping[str, Any]) -> float | None:
    return lifecycle.share(list(_fields(case).values())) if lifecycle.is_lease_return(case) else None


def output(st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    return _fields(case) if lifecycle.is_lease_return(case) else lifecycle.skipped_output()


def sources(st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]:
    return lifecycle.sources_of(case, ("lease_record", "customer_intent"))
