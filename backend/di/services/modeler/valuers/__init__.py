"""Valuers of the non-industrial templates (plan 8, phase 6; D11): ports of the PO prototype's engines that price every
path of a case. `tool_fleet` (Recover's `value`/`decide`, rng(26110) sample cases) and `device` (`dScore`/`dDecide`,
rng(4242) sample lots). Pure: no Session, no I/O.

Plan 9 (registry entry I-21): a pack whose routes need code registers a plug-in in `VALUERS`, keyed by the pack's
`valuer.kind`: `value_routes(case, pack, as_of) -> list[PathValue]`. `decide_case` (the one decider) reads this table. The
standard valuer (`standard.py`, the pack's own value lines, no code) is `VALUERS["standard"]`.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from di.services.modeler.pack import Pack
from di.services.modeler.valuers import medical_rental, standard, telecom_network, used_cars
from di.services.modeler.valuers.tool_fleet import PathValue

ValuerFn = Callable[[Mapping[str, Any], Pack, datetime | None], list[PathValue]]

ApprovalFn = Callable[[Mapping[str, Any], Pack, Sequence[PathValue]], list[dict[str, Any]]]

VALUERS: dict[str, ValuerFn] = {
    "standard": standard.value_routes,
    "used_cars": used_cars.value_routes,
    "telecom_network": telecom_network.value_routes,
    "medical_rental": medical_rental.value_routes,
}

# A plug-in that holds a decision for a person registers its guardrail check here (P9-11.9): given the facts, the pack and the
# values it priced, the approval items (`{id, owner, reason, ...}`) the decision is held with. `decide_case` reads this table.
APPROVALS: dict[str, ApprovalFn] = {"medical_rental": medical_rental.approval_holds}


def kind_of(pack: Pack) -> str:
    """The key `VALUERS` is read with: a standard pack that names a code plug-in (`valuer.params.params.plugin`) is valued by
    it (P9-9.10, P9-11.8), else the pack's own `valuer.kind`."""
    plugin = (pack.valuer.params.get("params") or {}).get("plugin") if pack.valuer.kind == "standard" else None
    return plugin if plugin in VALUERS else pack.valuer.kind
