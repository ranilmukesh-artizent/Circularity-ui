"""The product compliance gate of serialised retail returns (plan 9, P9-12.10, story NS-B2C-02). Pure.
Implements the check of registry entry I-2 for the catalogue gate `G-ESPR-1` (Compliance, stage decide).

    check_destruction_ban(case, pack, gate) -> GateResult    G-ESPR-1: an unsold apparel or footwear item is not destroyed

The case's `valuer` (the facts of the returned item as the retail returns portal lists them) holds `itemClass`, `unsold` and
`exceptionEvidence`. The gate applies to the item classes of `params.classes` (apparel, footwear). An unsold item makes every
route of `params.routes` (`exit`) fail, effect `block`, with "Destruction of unsold apparel and footwear is banned; reuse,
donation or recycling first"; `donate` and `recycle` stay open. When `exceptionEvidence` names one of
`params.allowed_exceptions` (an object `{exception, ref}`, or the exception's name alone) the route passes, and the result's
reason and the route note keep the evidence reference. A sold item passes ("Item is not unsold stock"); a class the gate does
not list is left to the data.

Never does: read the canonical store, the clock or a session, decide whether an exception is true (a person checks the
evidence), or write a case. Legal: the text summarises Regulation (EU) 2024/1781 (the ecodesign destruction ban; large companies
from 19 Jul 2026). It is a research summary, not legal advice: Kinective's Legal team must review it before it is relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

GATE = "G-ESPR-1"
BAN = "Destruction of unsold apparel and footwear is banned; reuse, donation or recycling first"
DEFAULT_CLASSES = ("apparel", "footwear")
DEFAULT_ROUTES = ("exit",)


def named_exception(evidence: Any, allowed: tuple[str, ...]) -> tuple[str, str | None] | None:
    """(exception, evidence reference) when the evidence names an allowed exception, else None. The evidence is an object
    `{exception, ref}` or the exception's name alone."""
    if isinstance(evidence, Mapping):
        name, ref = evidence.get("exception"), evidence.get("ref")
        return (str(name), str(ref) if ref else None) if name in allowed else None
    return (evidence, None) if isinstance(evidence, str) and evidence in allowed else None


def check_destruction_ban(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-ESPR-1 (module docstring); None for an item the gate does not judge."""
    item = case.get("valuer")
    item = item if isinstance(item, Mapping) else {}
    classes = tuple(str(c) for c in gate.params.get("classes") or DEFAULT_CLASSES)
    if item.get("itemClass") not in classes:
        return None
    if not item.get("unsold"):  # the ban is for unsold goods: nothing to show, nothing blocked
        return GateResult(gate.id, True, GateEffect("block", (), False, None), (), "Item is not unsold stock")
    mine = {r.id for r in pack.routes}
    routes = tuple(r for r in gate.params.get("routes") or DEFAULT_ROUTES if r in mine)
    allowed = tuple(str(x) for x in gate.params.get("allowed_exceptions") or ())
    found = named_exception(item.get("exceptionEvidence"), allowed)
    if found is None:
        return GateResult(gate.id, False, GateEffect("block", routes, False, None), (), BAN)
    name, ref = found
    why = f"Allowed exception on file: {name}" + (f", evidence {ref}" if ref else "")
    notes = tuple((r, why) for r in routes)
    return GateResult(gate.id, True, GateEffect("block", (), False, None), (), why, route_notes=notes)


CHECKS[GATE] = check_destruction_ban
