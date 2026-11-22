"""What every mocked system provides, and how source-sim finds them (docs/backend-steps.md, B3-B5).

A full mock is a package in `sim/vendors/` whose `__init__.py` defines `MOCK = Mock(...)`.
A generic mock is a module in `sim/generic/specs/` that defines `SPEC = Spec(...)` (see sim/generic/spec.py); a module there
that defines `MOCK` instead is taken as it is (sim/generic/specs/sandbox.py).
Both are picked up at start-up; no shared file needs editing to add one.
"""

import importlib
import pkgutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from sqlalchemy.engine import Connection

from sim.seed import Seed


@dataclass(frozen=True)
class Mock:
    source_id: str  # the demo's SOURCES[].id, as in sim/core/registry.py
    router: APIRouter | None
    ensure: Callable[[Connection, Seed], None]  # create tables and load the seed if empty
    reset: Callable[[Connection, Seed], dict[str, int]]  # drop, recreate, load; returns row counts
    title: str = ""
    # optional: an async callable run once at start-up (e.g. the Sims SFTP server); returns an object with .close()
    startup: Callable[[], Awaitable[Any]] | None = None


DISCOVERY_ERRORS: dict[str, str] = {}  # module -> error; must stay empty (tests/test_registry.py)


def discover() -> dict[str, Mock]:
    import sim.generic.specs as specs_pkg
    import sim.vendors as vendors_pkg
    from sim.generic.routes import build

    mocks: dict[str, Mock] = {}
    # S/4HANA and Ariba load first, so the order of the routers and of a full reset is the same as before they
    # moved into sim/vendors/ (plan 7).
    first = ["s4", "ariba"]
    packages = first + sorted(i.name for i in pkgutil.iter_modules(vendors_pkg.__path__) if i.name not in first)
    # A module that fails to import is recorded and skipped, so one broken mock does not take the others down.
    DISCOVERY_ERRORS.clear()
    for pkg in packages:
        name = f"sim.vendors.{pkg}"
        try:
            m = importlib.import_module(name).MOCK
            mocks[m.source_id] = m
        except Exception as e:  # noqa: BLE001
            DISCOVERY_ERRORS[name] = f"{type(e).__name__}: {e}"
    for info in pkgutil.iter_modules(specs_pkg.__path__):
        name = f"sim.generic.specs.{info.name}"
        try:
            mod = importlib.import_module(name)
            if not hasattr(mod, "SPEC") and hasattr(mod, "MOCK"):  # a hand-written mock beside the specs (the sandbox)
                mocks[mod.MOCK.source_id] = mod.MOCK
                continue
            spec = mod.SPEC
            if spec.source_id in mocks:
                raise RuntimeError(f"{spec.source_id} is mocked twice")
            mocks[spec.source_id] = build(spec)
        except Exception as e:  # noqa: BLE001
            DISCOVERY_ERRORS[name] = f"{type(e).__name__}: {e}"
    for name, error in DISCOVERY_ERRORS.items():
        print(f"[source-sim] mock {name} not loaded: {error}", flush=True)
    return mocks
