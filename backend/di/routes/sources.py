"""Connected systems, sync runs, the fetch log, canonical records and conflicts (docs/backend-steps.md, B9).

    GET /api/sources                      every source with status, freshness, completeness, open conflicts
    GET /api/sources/{id}                 one source with its recent runs
    GET /api/fetch-log?source=&limit=     every connector HTTP call (Audit › Fetch log)
    GET /api/canonical/{model}/{key}      the canonical record with each field's provenance
    GET /api/conflicts?status=open        the conflict queue
Changes (sync now, resolve or escalate a conflict) are actions: POST /api/actions/source.sync etc. A deleted source
(source.delete, until its deletion is undone; di.connectors.lifecycle) is not listed. The Connection Fabric's
lifecycle (save, delete, reconnect, rotate, pause, resume, disconnect, test) is in di.services.actions.fabric_sources.

B5c, provisioning a source that has a connector but starts not provisioned (AWS IoT, as in the demo); needs the
manageIntegrations permission (Admin, Developer):
    POST /api/sources/{id}/connect                 status live, full initial sync queued
    POST /api/sources/{id}/disconnect?purge=false  back to unavailable; purge=true also removes what it synced

The reads and their SQL: di.services.sources.
"""

from fastapi import APIRouter

from di.core.auth import Principal
from di.core.deps import CurrentPrincipal, DbSession, PersonPrincipal
from di.services import sources as service

router = APIRouter(prefix="/api", tags=["Connectors"])


_INTEGRATION_SECTIONS = ("map", "overview", "events", "conflicts", "tables", "models")


def _can_see_integration(p: Principal) -> None:
    p.require_any_page(*(("integration", s) for s in _INTEGRATION_SECTIONS))


@router.get("/sources")
def sources(p: CurrentPrincipal, session: DbSession):
    _can_see_integration(p)
    return service.sources(session)


@router.get("/sources/{source_id}")
def source(source_id: str, p: CurrentPrincipal, session: DbSession):
    _can_see_integration(p)
    return service.source(session, source_id)


@router.post("/sources/{source_id}/connect")
def connect(source_id: str, p: PersonPrincipal, session: DbSession):
    p.require("manageIntegrations")
    return service.connect(session, source_id)


@router.post("/sources/{source_id}/disconnect")
def disconnect(source_id: str, p: PersonPrincipal, session: DbSession, purge: bool = False):
    p.require("manageIntegrations")
    return service.disconnect(session, source_id, purge)


@router.get("/fetch-log")
def fetch_log(p: CurrentPrincipal, session: DbSession, source: str | None = None, limit: int = 100):
    p.require_page("audit", "log")
    return service.fetch_log(session, source, limit)


@router.get("/canonical/{model}/{key}")
def canonical(model: str, key: str, p: CurrentPrincipal, session: DbSession):
    p.require_any_page(("product", None), ("integration", "models"))
    return service.canonical(p, session, model, key)


@router.get("/conflicts")
def conflicts(p: CurrentPrincipal, session: DbSession, status: str = "open"):
    p.require_page("integration", "conflicts")
    return service.conflicts(session, status)
