"""Connected systems, sync runs, the fetch log, canonical records and conflicts, behind di.routes.sources (B9)."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

from di.connectors import lifecycle, sync
from di.connectors.registry import ADAPTERS
from di.core.auth import Principal
from di.services.canonical import store


def _source_row(r: RowMapping) -> dict:
    now = datetime.now(UTC)
    fresh = round((now - r["last_success_at"]).total_seconds() / 60, 1) if r["last_success_at"] else None
    return dict(r) | {"fresh_minutes": fresh, "connector": r["id"] in ADAPTERS}


def sources(session: Session) -> list[dict]:
    """Every source that is not deleted, with its open conflicts and facts."""
    rows = session.execute(
        text(
            "SELECT s.*, (SELECT count(*) FROM conflict c WHERE c.status IN ('open', 'escalated') AND c.authority = s.id) "
            "AS open_conflicts, "
            "(SELECT count(*) FROM provenance v WHERE v.source_id = s.id) AS facts FROM source_system s ORDER BY s.id"
        )
    ).mappings()
    gone = lifecycle.deleted(session)
    return [_source_row(r) for r in rows if r["id"] not in gone]


def source(session: Session, source_id: str) -> dict:
    """One source with its recent runs; 404 for an unknown or deleted source."""
    r = session.execute(text("SELECT * FROM source_system WHERE id = :i"), {"i": source_id}).mappings().first()
    if r is None or lifecycle.is_deleted(session, source_id):
        raise HTTPException(404, {"code": "not_found", "message": f"No source {source_id}."})
    runs = session.execute(
        text("SELECT * FROM sync_run WHERE source_id = :i ORDER BY id DESC LIMIT 20"), {"i": source_id}
    ).mappings()
    return _source_row(r) | {"runs": [dict(x) for x in runs]}


def connect(session: Session, source_id: str) -> dict:
    """B5c: provisions a source that has a connector (status live, full initial sync queued)."""
    try:
        return sync.connect_source(session, source_id)
    except KeyError as e:
        raise HTTPException(404, {"code": "not_found", "message": f"No connector for {source_id}."}) from e


def disconnect(session: Session, source_id: str, purge: bool) -> dict:
    """B5c: back to unavailable; purge also removes what it synced."""
    if source_id not in ADAPTERS:
        raise HTTPException(404, {"code": "not_found", "message": f"No connector for {source_id}."})
    try:
        return sync.disconnect_source(session, source_id, purge)
    except KeyError as e:
        raise HTTPException(404, {"code": "not_found", "message": f"No source {source_id}."}) from e


def fetch_log(session: Session, source: str | None, limit: int) -> list[dict]:
    rows = session.execute(
        text("SELECT * FROM fetch_log WHERE (CAST(:s AS text) IS NULL OR source_id = :s) ORDER BY id DESC LIMIT :n"),
        {"s": source, "n": max(1, min(limit, 500))},
    ).mappings()
    return [dict(r) for r in rows]


def canonical(p: Principal, session: Session, model: str, key: str) -> dict:
    """The canonical record with each field's provenance; an asset of a tenant the account cannot see is refused."""
    rec = store.get(session, model, key)
    if rec is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No {model} {key}."})
    owner = rec["data"].get("owner_tenant") if model == "asset" else None
    if owner and not p.tenant_ok(owner):
        raise HTTPException(403, {"code": "tenant_boundary", "message": f"{key} belongs to {owner}, a tenant you cannot see."})
    return rec


def conflicts(session: Session, status: str) -> list[dict]:
    rows = session.execute(
        text("SELECT * FROM conflict WHERE (:s = 'all' OR status = :s) ORDER BY id DESC LIMIT 500"), {"s": status}
    ).mappings()
    return [dict(r) for r in rows]
