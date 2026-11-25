"""The safety recall register's notices of a tool-fleet case, as evidence (plan 9, P9-3.7, story TF-04).

    evidence(s, cls, released) -> dict     the `recall_check` evidence record (the notices of the class)

The canonical `recall` records (`recall` adapter, one per notice) of the tool's class whose serial range might hold the serial,
with the case's own release (`case["recallRelease"]`, set by `recall.release`), become one record
`{type: "recall_check", source, at, result: "pass", value: {recalls, released}}`. It is always on file (no notice reads as no
active recall; whether the register is connected is the Source Map's to say). Whether a notice holds the serial, and what it
blocks, is `fleet_evidence.recall_check`; `gate_hold.attach_evidence` adds the record to a tool-fleet case.

Never does: decide anything, write to the canonical store or move a case.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.modeler.valuers import fleet_evidence

MODEL = "recall"


def evidence(s: Session, cls: Any, released: dict[str, Any] | None) -> dict[str, Any]:
    """The evidence record of the serial's recall check (module docstring)."""
    rows = s.execute(
        text(
            "SELECT c.data, (SELECT p.source_id FROM provenance p WHERE p.model = :m AND p.key = c.key "
            "ORDER BY p.fetched_at DESC LIMIT 1) AS source FROM canonical c WHERE c.model = :m ORDER BY c.key"
        ),
        {"m": MODEL},
    ).all()
    notices = [dict(r.data or {}) for r in rows if not cls or not (r.data or {}).get("tool_class") or r.data["tool_class"] == cls]
    return {
        "type": fleet_evidence.RECALL, "source": next((r.source for r in rows if r.source), "") or "recall",
        "at": clock.now().isoformat(), "result": "pass", "value": {"recalls": notices, "released": released or None},
    }  # fmt: skip
