"""The fleet contract line of a tool-fleet case, as evidence (plan 9, P9-3.6, story TF-02).

    evidence(s, serial) -> dict | None     the `contract_line` evidence record of the serial, or None when no line is on file

The canonical `contract_line` of the serial (the key is the tool's serial, `fleet_contracts` adapter) and its contract's
`owner_org` become one record `{type: "contract_line", source, at, result: "pass", value}`, `value` in the fleet contract
system's names (`fleet_evidence.line_value`). `result` says the line is on file; whether it gives the right to dispose of
the tool is the gate's (`fleet_evidence.contract_check`). `gate_hold.attach_evidence` adds the record to a tool-fleet case.

Never does: decide whether the line is good, write to the canonical store or move a case. A later write of the line
queues `case.gateRecheck` for the serial (canonical.store.apply), which releases a case the line now clears.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.modeler.valuers import fleet_evidence

MODEL = "contract_line"


def evidence(s: Session, serial: Any) -> dict[str, Any] | None:
    """The evidence record of the serial's contract line (module docstring)."""
    if not serial:
        return None
    row = s.execute(
        text(
            "SELECT c.data, c.updated_at, (SELECT p.source_id FROM provenance p WHERE p.model = :m AND p.key = c.key "
            "ORDER BY p.fetched_at DESC LIMIT 1) AS source FROM canonical c WHERE c.model = :m AND c.key = :k"
        ),
        {"m": MODEL, "k": str(serial)},
    ).first()
    if row is None:
        return None
    contract = s.execute(
        text("SELECT data FROM canonical WHERE model = 'contract' AND key = :k"), {"k": (row.data or {}).get("contract_id")}
    ).scalar()
    return {
        "type": fleet_evidence.CONTRACT_LINE, "source": row.source or "", "at": row.updated_at.isoformat(), "result": "pass",
        "value": fleet_evidence.line_value(row.data or {}, contract),
    }  # fmt: skip
