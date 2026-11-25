"""What the three lifecycle stages share (plan 9, P9-2.20; registry entries I-7 and I-3): reading the lease, return and shipment
records of a returned asset.

Owns: `is_lease_return`, `fields_of` (a record's wanted fields), `share` (fields found over fields required), `can_request`,
`sources_of` and the one sentence a skipped stage records. A lease return is a case whose asset has any of the `LEASE_TYPES`
records on file; every other case (the demo's 128 cases and RT-1048 among them) skips the three stages with no call.
Never does: call an action, read the database or a clock (the runtime puts the records on the case, `lifecycle_evidence`).
Pure.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.modeler.evidence import evidence_of

LEASE_TYPES = ("lease_record", "customer_intent", "return_authorisation", "shipment", "goods_receipt")
NOT_A_LEASE_RETURN = "not a lease return"
LABELS = {
    "lease_record": "Lease record", "customer_intent": "Customer intent", "return_authorisation": "Return authorisation",
    "shipment": "Shipment",
}  # fmt: skip


def is_lease_return(case: Mapping[str, Any]) -> bool:
    return any(evidence_of(case, t) is not None for t in LEASE_TYPES)


def present(v: Any) -> bool:
    """A value that was read (zero and false count; None and an empty string do not)."""
    return v is not None and v != ""


def fields_of(case: Mapping[str, Any], type: str, keys: Sequence[str]) -> dict[str, Any]:
    """The wanted fields of the newest record of `type` (None for a field the record does not have, or no record)."""
    e = evidence_of(case, type)
    value = e.value if e is not None else {}
    return {k: value.get(k) if present(value.get(k)) else None for k in keys}


def share(found: Sequence[Any]) -> float:
    """Fields found over fields required (0.0 when there are none)."""
    return sum(1 for v in found if present(v)) / len(found) if found else 0.0


def can_request(case: Mapping[str, Any]) -> bool:
    """`evidence.request` has something to ask for: the case names what it is blocked on and no request went out yet."""
    return bool(case.get("blocked")) and not case.get("requested")


def skipped_output() -> dict[str, Any]:
    return {"reason": NOT_A_LEASE_RETURN}


def sources_of(case: Mapping[str, Any], types: Sequence[str]) -> list[dict[str, Any]]:
    """`{fact, source, at}` for each of the record types that is on file."""
    out: list[dict[str, Any]] = []
    for t in types:
        if (e := evidence_of(case, t)) is not None:
            out.append({"fact": LABELS[t], "source": e.source, "at": e.at.isoformat()})
    return out
