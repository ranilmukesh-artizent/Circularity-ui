"""The facts a tool's wear and remaining life are computed from, as evidence (plan 9, P9-3.9, story TF-06).

    evidence(s, case) -> {"life_inputs": Evidence | None}     what the canonical store holds for the case's serial

Read from the canonical store, nothing else: the telematics (`condition.<serial>`: run_hours, high_load_share, event_counts,
telemetry_coverage_pct, telemetry_at; P9-3.2), the months on the contract (`contract_line.<serial>.months_on_contract`), the
repair log's replacements (`repair_event` orders of the serial that are not open: each component's run hours at its last
replacement; P9-3.1) and PLM's rated life of the class's wear components (`plm.tool_ratings`, P9-3.3). The record is None
when there are neither run hours nor months on contract: the case then keeps its own life inputs.

`value.repair_history_complete` is False when a replaced component in the log has no run hours at its replacement (its wear
cannot be restarted from the replacement). What the numbers mean, and the computation, is `tool_inputs.life_of` and `tool_life`
(pure). Never does: compute life, write to the canonical store or move a case.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import plm
from di.services.modeler.evidence import Evidence, parse_time
from di.services.modeler.valuers import tool_inputs

SOURCE = "tooltel"


def _data(s: Session, model: str, key: str) -> Mapping[str, Any]:
    row = s.execute(text("SELECT data FROM canonical WHERE model = :m AND key = :k"), {"m": model, "k": key}).scalar()
    return row or {}


def _replacements(s: Session, serial: str) -> tuple[dict[str, float], bool]:
    """(component name -> run hours at its latest replacement, whether every replacement says its hours) from the serial's
    repair orders that are not open."""
    rows = s.execute(
        text(
            "SELECT data FROM canonical WHERE model = 'repair_event' AND data ->> 'serial' = :s "
            "AND COALESCE(data ->> 'status', '') <> 'open' AND jsonb_typeof(data -> 'components') = 'array' ORDER BY key"
        ),
        {"s": serial},
    ).scalars()
    out: dict[str, float] = {}
    complete = True
    for d in rows:
        for comp in d.get("components") or []:
            if not isinstance(comp, Mapping) or not comp.get("replaced"):
                continue
            hrs = comp.get("runHoursAtReplacement")
            if isinstance(hrs, int | float) and not isinstance(hrs, bool):
                out[str(comp.get("name"))] = max(out.get(str(comp.get("name")), 0.0), float(hrs))
            else:
                complete = False
    return out, complete


def evidence(s: Session, case: Mapping[str, Any]) -> dict[str, Evidence | None]:
    """The life facts of the case's serial (module docstring)."""
    serial = str(case.get("serial") or case.get("assetId") or "")
    if not serial:
        return {tool_inputs.LIFE: None}
    cond = _data(s, "condition", serial)
    hours = cond.get("run_hours")
    months = _data(s, "contract_line", serial).get("months_on_contract")
    if hours is None and months is None:
        return {tool_inputs.LIFE: None}
    replaced, complete = _replacements(s, serial)
    ratings = [
        {"name": r.name, "rated_life_hours": r.rated_life_hours, "weight": r.weight, "critical": r.critical}
        for r in plm.tool_ratings(s, case.get("owner"), str(case.get("cls") or ""))
    ]
    seen = cond.get("telemetry_at")
    value = {
        "hours": hours, "high_load_share": cond.get("high_load_share"), "events": cond.get("event_counts") or {},
        "coverage_pct": cond.get("telemetry_coverage_pct"), "telemetry_at": seen, "months_on_contract": months,
        "replacements": replaced, "repair_history_complete": complete, "ratings": ratings,
    }  # fmt: skip
    return {tool_inputs.LIFE: Evidence(tool_inputs.LIFE, SOURCE, parse_time(seen) or clock.now(), "pass", value)}
