"""The telematics of a tool-fleet case, as evidence (plan 9, P9-3.8, story TF-05).

    evidence(s, serial) -> dict | None     the `telematics_reading` evidence record of the serial, or None when none is on file

The canonical `condition.<serial>` the telematics adapter fills (`tool_telematics`, P9-3.2): its `telemetry_at` (the tool's last
seen) is the record's time and `value.lastSeen`; `value.coveragePct` is its coverage. `result` says a reading is on file; whether
it is fresh enough is the gate's (`fleet_evidence.telematics_check`, GR-13). `gate_hold.attach_evidence` adds the record to a
tool-fleet case. Never does: decide freshness, write to the canonical store or move a case.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.modeler.valuers import fleet_evidence


def evidence(s: Session, serial: Any) -> dict[str, Any] | None:
    """The evidence record of the serial's telematics (module docstring)."""
    if not serial:
        return None
    row = s.execute(
        text(
            "SELECT c.data, (SELECT p.source_id FROM provenance p WHERE p.model = 'condition' AND p.key = c.key "
            "AND p.field = 'telemetry_at' ORDER BY p.fetched_at DESC LIMIT 1) AS source "
            "FROM canonical c WHERE c.model = 'condition' AND c.key = :k"
        ),
        {"k": str(serial)},
    ).first()
    data = (row.data if row else None) or {}
    if row is None or not data.get("telemetry_at"):
        return None
    return {
        "type": fleet_evidence.TELEMATICS, "source": row.source or "", "at": data["telemetry_at"], "result": "pass",
        "value": {"lastSeen": data["telemetry_at"], "coveragePct": data.get("telemetry_coverage_pct")},
    }  # fmt: skip
