"""The read endpoints per page area (docs/backend-steps.md, B14): one module per area, each with
`router = APIRouter(prefix="/api/screens/<area>", tags=["screens: <area>"])`. Every module in this package that has a
`router` is included here, so adding an area needs no shared edit. The endpoints are thin: what each page shows is
built by the matching module in di.services.screens, which also maps the facade functions to the endpoints."""

import importlib
import pkgutil

from fastapi import APIRouter

router = APIRouter()

for _info in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if isinstance(getattr(_mod, "router", None), APIRouter):
        router.include_router(_mod.router)
