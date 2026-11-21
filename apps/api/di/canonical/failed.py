"""Failed records: data held instead of stored (plan 6, B1; table failed_record, migration 0015).

    hold(s, run_kind="sync", run_id=42, source_id="insp", reason="Unknown field condition.colour", step="canonical",
         resource="audits", ext_id="audit_1", field="condition.colour", rule="schema", value="red", payload={...}) -> id

Writers: the sync (a fact that does not fit its canonical model, di/canonical/schema.py check_fact), Manual Import
(a row that fails its checks, di/connectors/manual.py) and the workflow engine (a row a step rejected). A held record
keeps its value, the reason and the record it came from, so it can be fixed and reprocessed, or dropped. `hold` writes
in the caller's transaction (no commit).
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

RUN_KINDS = ("sync", "workflow", "import")


def hold(
    s: Session,
    *,
    run_kind: str,
    reason: str,
    run_id: Any = None,
    source_id: str | None = None,
    step: str | None = None,
    resource: str | None = None,
    ext_id: str | None = None,
    field: str | None = None,
    rule: str | None = None,
    value: Any = None,
    payload: Any = None,
) -> int:
    """Hold one failed record; returns its id."""
    if run_kind not in RUN_KINDS:
        raise ValueError(f"unknown run kind {run_kind!r}")
    return int(
        s.execute(
            text(
                "INSERT INTO failed_record (run_kind, run_id, source_id, step, resource, ext_id, field, rule, value, reason, "
                "payload) VALUES (:k, :run, :src, :step, :res, :ext, :f, :rule, CAST(:v AS jsonb), :why, CAST(:p AS jsonb)) "
                "RETURNING id"
            ),
            {
                "k": run_kind,
                "run": None if run_id is None else str(run_id),
                "src": source_id,
                "step": step,
                "res": resource,
                "ext": ext_id,
                "f": field,
                "rule": rule,
                "v": json.dumps(value, default=str),
                "why": reason[:1000],
                "p": None if payload is None else json.dumps(payload, default=str),
            },
        ).scalar_one()
    )


def held(s: Session, *, run_kind: str | None = None, run_id: Any = None, source_id: str | None = None) -> list[dict]:
    """The records still held, newest first, filtered by run and source."""
    rows = s.execute(
        text(
            "SELECT * FROM failed_record WHERE status = 'held' AND (CAST(:k AS text) IS NULL OR run_kind = :k) "
            "AND (CAST(:run AS text) IS NULL OR run_id = :run) AND (CAST(:src AS text) IS NULL OR source_id = :src) "
            "ORDER BY id DESC"
        ),
        {"k": run_kind, "run": None if run_id is None else str(run_id), "src": source_id},
    ).mappings()
    return [dict(r) for r in rows]
