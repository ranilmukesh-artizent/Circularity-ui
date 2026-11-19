"""Adapters are discovered from di/connectors/adapters/*.py, each defining ADAPTER = <Adapter instance>."""

import importlib
import logging
import pkgutil

from di.connectors.base import Adapter

log = logging.getLogger("di.connectors")
LOAD_ERRORS: dict[str, str] = {}


def _discover() -> dict[str, Adapter]:
    import di.connectors.adapters as pkg

    out: dict[str, Adapter] = {}
    for info in pkgutil.iter_modules(pkg.__path__):
        name = f"di.connectors.adapters.{info.name}"
        try:
            a = importlib.import_module(name).ADAPTER
            if a.source_id in out:
                raise RuntimeError(f"two adapters for {a.source_id}")
            out[a.source_id] = a
        except Exception as e:  # noqa: BLE001 - one broken adapter must not stop the others
            LOAD_ERRORS[name] = f"{type(e).__name__}: {e}"
            log.exception("adapter %s not loaded", name)
    return out


ADAPTERS: dict[str, Adapter] = _discover()
