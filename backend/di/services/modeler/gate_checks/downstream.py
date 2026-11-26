"""The downstream vendor gates (plan 9, P9-10.16, stories TN-24; X-13 and X-14 reuse this module). Pure.
Implements the checks of registry entry I-2 for the catalogue gates `G-DS-1` and `G-WEEE-2`; they run before any business rule.

    check_downstream_vendor(case, pack, gate) -> GateResult | None   G-DS-1: recycle only to a vendor with a valid certificate
    check_weee_record(case, pack, gate) -> GateResult | None         G-WEEE-2: an EU site's recycling has WEEE data

The case's `downstream` is the recycler portal's read of the vendor the route would use: `vendor_id`, `certificate` ({scheme, ref,
expires}) and the pickup's `weee_category` and `weight_kg`; `gateNow` is the decision date. G-DS-1: a certificate whose `expires`
date is before the decision date fails every route of `params.routes` with "Recycler certificate expired <date>" (effect `block`);
a valid one passes and `certificate_ref` is in the result text, which the decision keeps
("Recycler certificate <ref> valid to <date>").
G-WEEE-2: when the site's region is in `params.regions` (EU), a missing category or weight fails the route with
"WEEE category and weight required for an EU site". Neither judges a case with no `downstream` record (None).
Never does: read the store or the clock, choose a vendor, or write a case. R2v3, e-Stewards and Directive 2012/19/EU are research
summaries: Kinective's Legal team reviews the wording before it is relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.evidence import parse_time
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

VENDOR_GATE = "G-DS-1"
WEEE_GATE = "G-WEEE-2"
REASON_WEEE = "WEEE category and weight required for an EU site"


def _routes(gate: GateDef, pack: Pack) -> tuple[str, ...]:
    want = gate.params.get("routes") or ("recycle",)
    return tuple(r.id for r in pack.routes if r.id in want)


def check_downstream_vendor(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-DS-1 (module docstring)."""
    d = case.get("downstream")
    if not isinstance(d, Mapping) or not d.get("vendor_id"):
        return None
    cert = d.get("certificate") or {}
    expires = str(cert.get("expires") or "")
    now = parse_time(case.get("gateNow"))
    if not expires or (now is not None and expires < now.date().isoformat()):
        return GateResult(
            gate.id, False, GateEffect("block", _routes(gate, pack), False, None), (),
            f"Recycler certificate expired {expires}" if expires else "Recycler certificate not on file",
        )  # fmt: skip
    return GateResult(
        gate.id, True, GateEffect("block", (), False, None), (), f"Recycler certificate {cert.get('ref')} valid to {expires}"
    )  # fmt: skip


def check_weee_record(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-WEEE-2 (module docstring)."""
    d = case.get("downstream")
    region = (d or {}).get("site_region") if isinstance(d, Mapping) else None
    if not isinstance(d, Mapping) or region not in (gate.params.get("regions") or ["EU"]):
        return None
    weight = d.get("weight_kg")
    ok = bool(d.get("weee_category")) and isinstance(weight, int | float) and not isinstance(weight, bool) and weight > 0
    if ok:
        return GateResult(gate.id, True, GateEffect("block", (), False, None), (), "WEEE category and weight on the pickup")
    return GateResult(gate.id, False, GateEffect("block", _routes(gate, pack), False, None), (), REASON_WEEE)


CHECKS[VENDOR_GATE] = check_downstream_vendor
CHECKS[WEEE_GATE] = check_weee_record
