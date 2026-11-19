"""What every mocked system provides, and how source-sim finds them (docs/BACKEND_STEPS.md, B3-B5).

A full mock is a package in `sim/vendors/` whose `__init__.py` defines `MOCK = Mock(...)`.
A generic mock is a module in `sim/generic/specs/` that defines `SPEC = Spec(...)` (see sim/generic/spec.py).
Both are picked up at start-up; no shared file needs editing to add one.
"""

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.engine import Connection

from sim.seed import Seed


@dataclass(frozen=True)
class Mock:
    source_id: str  # the demo's SOURCES[].id, as in sim/registry.py
    router: APIRouter | None
    ensure: Callable[[Connection, Seed], None]  # create tables and load the seed if empty
    reset: Callable[[Connection, Seed], dict[str, int]]  # drop, recreate, load; returns row counts
    title: str = ""


DISCOVERY_ERRORS: dict[str, str] = {}  # module -> error; must stay empty (tests/test_registry.py)


def discover() -> dict[str, Mock]:
    from sim.ariba import api as ariba_api
    from sim.ariba import seed as ariba_seed
    from sim.generic import build
    from sim.s4 import api as s4_api
    from sim.s4 import seed as s4_seed

    mocks = {
        "erp": Mock("erp", s4_api.router, s4_seed.ensure, s4_seed.reset, "SAP S/4HANA"),
        "proc": Mock("proc", ariba_api.router, ariba_seed.ensure, ariba_seed.reset, "SAP Ariba"),
    }
    import sim.generic.specs as specs_pkg
    import sim.vendors as vendors_pkg

    # A module that fails to import is recorded and skipped, so one broken mock does not take the others down.
    DISCOVERY_ERRORS.clear()
    for info in pkgutil.iter_modules(vendors_pkg.__path__):
        name = f"sim.vendors.{info.name}"
        try:
            m = importlib.import_module(name).MOCK
            mocks[m.source_id] = m
        except Exception as e:  # noqa: BLE001
            DISCOVERY_ERRORS[name] = f"{type(e).__name__}: {e}"
    for info in pkgutil.iter_modules(specs_pkg.__path__):
        name = f"sim.generic.specs.{info.name}"
        try:
            spec = importlib.import_module(name).SPEC
            if spec.source_id in mocks:
                raise RuntimeError(f"{spec.source_id} is mocked twice")
            mocks[spec.source_id] = build(spec)
        except Exception as e:  # noqa: BLE001
            DISCOVERY_ERRORS[name] = f"{type(e).__name__}: {e}"
    for name, error in DISCOVERY_ERRORS.items():
        print(f"[source-sim] mock {name} not loaded: {error}", flush=True)
    return mocks
