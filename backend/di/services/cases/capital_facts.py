"""The facts the medical capital gates read (plan 9, P9-12.9). Pure.

    lay(case) -> None     sets `device`, `market`, `work` and `sanitisationRef` on the case dict from its flat facts

A `medical_capital` case carries its facts flat (the standard valuer's, as the trade-in register's adapter writes them:
`single_use`, `udi`, `origin_market`, `target_market`, `service_record_ref`, `recalls_closed`, `changes_performance`,
`sanitisation_ref`), in the case or in its `valuer` snapshot. The gates' triggers and checks read them as `device.single_use`
(G-MED-2), `market.cross_market` (G-MED-3), `work.changes_performance` (G-MED-1) and the case's `sanitisationRef` (G-DATA-3).
`decide_case` calls `lay` for this pack on its own copy of the case, so every path (intake, re-evaluation, the Modeler's queue,
replay) reads the same facts. `changes_performance` is true unless a fact says
otherwise: refurbishing for resale changes the device. Never does: read a session or the clock, or decide anything.
"""

from collections.abc import MutableMapping
from typing import Any

PACK = "medical_capital"


def lay(case: MutableMapping[str, Any]) -> None:
    """Set the derived fact groups on `case` (module docstring)."""
    facts = {**{k: v for k, v in case.items() if k != "valuer"}, **(case.get("valuer") or {})}
    origin, target = facts.get("origin_market"), facts.get("target_market")
    groups: dict[str, Any] = {
        "device": {"single_use": facts.get("single_use") is True, "udi": facts.get("udi")},
        "market": {
            "origin": origin, "target": target, "cross_market": bool(origin and target and origin != target),
            "udi": facts.get("udi"), "service_record_ref": facts.get("service_record_ref"),
            "recalls_closed": facts.get("recalls_closed"),
        },
        "work": {"changes_performance": facts.get("changes_performance") is not False},
    }  # fmt: skip
    case.update(groups)
    if facts.get("sanitisation_ref") and not case.get("sanitisationRef"):
        case["sanitisationRef"] = facts["sanitisation_ref"]
