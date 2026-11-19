"""Connected systems, sync runs, the fetch log, canonical records and conflicts (docs/BACKEND_STEPS.md, B9).

    GET /api/sources                      every source with status, freshness, completeness, open conflicts
    GET /api/sources/{id}                 one source with its recent runs
    GET /api/fetch-log?source=&limit=     every connector HTTP call (Audit › Fetch log)
    GET /api/canonical/{model}/{key}      the canonical record with each field's provenance
    GET /api/conflicts?status=open        the conflict queue
Changes (sync now, resolve or escalate a conflict) are actions: POST /api/actions/source.sync etc.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.auth import Principal, principal
from di.canonical import store
from di.connectors.registry import ADAPTERS
from di.db import get_session

router = APIRouter(prefix="/api", tags=["Connectors"])


def _can_see_integration(p: Principal) -> None:
    if not any(
        policy.can_page(p.account, "integration", s) for s in ("map", "overview", "events", "conflicts", "tables", "models")
    ):
        raise HTTPException(403, {"code": "out_of_scope", "message": f"Not available for the {p.account.role} view."})


def _source_row(r) -> dict:
    now = datetime.now(UTC)
    fresh = round((now - r["last_success_at"]).total_seconds() / 60, 1) if r["last_success_at"] else None
    return dict(r) | {"fresh_minutes": fresh, "connector": r["id"] in ADAPTERS}


@router.get("/sources")
def sources(p: Principal = Depends(principal), session: Session = Depends(get_session)):
    _can_see_integration(p)
    rows = session.execute(
        text(
            "SELECT s.*, (SELECT count(*) FROM conflict c WHERE c.status = 'open' AND c.authority = s.id) AS open_conflicts, "
            "(SELECT count(*) FROM provenance v WHERE v.source_id = s.id) AS facts FROM source_system s ORDER BY s.id"
        )
    ).mappings()
    return [_source_row(r) for r in rows]


@router.get("/sources/{source_id}")
def source(source_id: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    _can_see_integration(p)
    r = session.execute(text("SELECT * FROM source_system WHERE id = :i"), {"i": source_id}).mappings().first()
    if r is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No source {source_id}."})
    runs = session.execute(
        text("SELECT * FROM sync_run WHERE source_id = :i ORDER BY id DESC LIMIT 20"), {"i": source_id}
    ).mappings()
    return _source_row(r) | {"runs": [dict(x) for x in runs]}


@router.get("/fetch-log")
def fetch_log(
    source: str | None = None, limit: int = 100, p: Principal = Depends(principal), session: Session = Depends(get_session)
):
    p.require_page("audit", "log")
    rows = session.execute(
        text("SELECT * FROM fetch_log WHERE (CAST(:s AS text) IS NULL OR source_id = :s) ORDER BY id DESC LIMIT :n"),
        {"s": source, "n": max(1, min(limit, 500))},
    ).mappings()
    return [dict(r) for r in rows]


@router.get("/canonical/{model}/{key}")
def canonical(model: str, key: str, p: Principal = Depends(principal), session: Session = Depends(get_session)):
    if not (policy.can_page(p.account, "product") or policy.can_page(p.account, "integration", "models")):
        raise HTTPException(403, {"code": "out_of_scope", "message": f"Not available for the {p.account.role} view."})
    rec = store.get(session, model, key)
    if rec is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No {model} {key}."})
    owner = rec["data"].get("owner_tenant") if model == "asset" else None
    if owner and not p.tenant_ok(owner):
        raise HTTPException(403, {"code": "tenant_boundary", "message": f"{key} belongs to {owner}, a tenant you cannot see."})
    return rec


@router.get("/conflicts")
def conflicts(status: str = "open", p: Principal = Depends(principal), session: Session = Depends(get_session)):
    p.require_page("integration", "conflicts")
    rows = session.execute(
        text("SELECT * FROM conflict WHERE (:s = 'all' OR status = :s) ORDER BY id DESC LIMIT 500"), {"s": status}
    ).mappings()
    return [dict(r) for r in rows]
