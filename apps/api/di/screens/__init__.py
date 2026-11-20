"""Read APIs for the screens (docs/backend-steps.md, B14): what each page shows, already scoped to the signed-in account.

One module per area (home, command, product, case, orchestration, analytics, audit, reference, integration, mcp,
access, workflows), mirroring the frontend facade files in apps/web/src/api/*.ts. Each module defines
`router = APIRouter(prefix="/api/screens/<area>", tags=["screens: <area>"])`; every module in this package that has a
`router` is included here, so adding an area needs no shared edit. Each module's docstring maps the facade functions it
serves to its endpoints, for the frontend switch-over (B17). Formatting (money, percentages, dates for display) stays in
the frontend; endpoints return data.
"""

import importlib
import pkgutil

from fastapi import APIRouter

router = APIRouter()

for _info in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    if isinstance(getattr(_mod, "router", None), APIRouter):
        router.include_router(_mod.router)
