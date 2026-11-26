"""Reserve and release the replacement demand a device case fills (plan 9, P9-6.16, story DV-12).

    on_approve(s, case) -> str | None     the approved route is Replacement stock: reserve one demand unit for the case
    on_decline(s, case) -> int            a rejected decision gives its units back

A device case valued on `replacement` shows the demand unit it would fill (`valuer.inputs.replacement`), but nothing is held until
a person approves the decision (`decision.approve`, `decision.override`) or the standing policy does: `on_approve` then reserves
the unit in the approval's own transaction, once (a repeat is a no-op) and atomically, so two approvals cannot take the last unit.
When none is left, it answers the refusal text and the approval is refused ("No open replacement demand"). A declined decision
(`decision.decline`) releases the case's units. Any other chosen route reserves nothing.
Never does: approve, decline or choose a route, call a model (every number is counted, R16) or add an action: the reservation is
a step of the existing approval, which only a person (or the standing policy) takes (R21, `forbidden.py`).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from di.repositories import device_market

ROUTE = "replacement"
NONE_LEFT = "No open replacement demand"


def _chosen(case: Mapping[str, Any]) -> str | None:
    r = case.get("chosen")
    return str(r["id"]) if isinstance(r, Mapping) and r.get("id") else None


def on_approve(s: Session, case: dict[str, Any]) -> str | None:
    """Reserve a demand unit when the case's chosen route is Replacement stock. None when there is nothing to refuse (another
    route,
    or the unit is reserved); else the refusal's text. The unit is the one the case's valuation named, else any open one of its
    SKU and grade. Records `replacement: {demand_id, unit_cost}` on the case."""
    lot = case.get("valuer")
    if _chosen(case) != ROUTE or not isinstance(lot, dict) or not lot.get("imei"):
        return None
    named = ((lot.get("inputs") or {}).get("replacement") or {}).get("demand_id")
    rows = device_market.open_replacement(s, str(lot.get("sku_key") or ""), str(lot["grade"]), str(case["id"]))
    rows.sort(key=lambda d: d.id != named)  # the valued unit first
    for d in rows:
        if device_market.reserve_replacement(s, d.id, str(case["id"])):
            case["replacement"] = {"demand_id": d.id, "unit_cost": d.unit_cost}
            return None
    return NONE_LEFT


def on_decline(s: Session, case: Mapping[str, Any]) -> int:
    """Give the case's reserved units back; how many it held."""
    return device_market.release_replacement(s, str(case["id"]))
