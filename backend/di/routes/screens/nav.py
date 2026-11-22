"""The /api/screens/nav endpoints (the menu, the record scope, the sign-in accounts). What they serve, and the facade
map: di.services.screens.nav."""

from fastapi import APIRouter

from di.core.deps import CurrentPrincipal, DbSession
from di.services.screens import nav as svc

router = APIRouter(prefix="/api/screens/nav", tags=["screens: nav"])


@router.get("")
def nav(
    p: CurrentPrincipal,
    session: DbSession,
    cc_mode: str = "operational",
    last_asset: str | None = None,
    tenant_filter: str = "All",
):
    return svc.page(p, session, cc_mode, last_asset, tenant_filter)


@router.get("/scope")
def scope(p: CurrentPrincipal, session: DbSession):  # noqa: ARG001 - the dependency authenticates the caller
    return svc.scope(session)


@router.get("/accounts")
def accounts(session: DbSession):
    """The demo accounts, as the identity mapping has them now, with the sign-in email (shown before sign-in)."""
    return svc.accounts(session)
