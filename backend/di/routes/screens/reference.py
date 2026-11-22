"""The /api/screens/reference endpoint. What it serves, list by list: di.services.screens.reference."""

from fastapi import APIRouter

from di.services.screens import reference as svc

router = APIRouter(prefix="/api/screens/reference", tags=["screens: reference"])


@router.get("")
def reference(names: str | None = None):
    return svc.reference(names)
