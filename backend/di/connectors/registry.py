"""Adapters are discovered from di/connectors/adapters/*.py, each defining ADAPTER = <Adapter instance>.

adapter_for(s, "erp")       → the Python adapter of a demo source
adapter_for(s, "workday")   → a ConfiguredAdapter on the source's stored connection (plan 6 A3), or None
"""

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
        except Exception as e:  # one broken adapter must not stop the others
            LOAD_ERRORS[name] = f"{type(e).__name__}: {e}"
            log.exception("adapter %s not loaded", name)
    return out


ADAPTERS: dict[str, Adapter] = _discover()


def python_adapter(source_id: str) -> Adapter | None:
    """The source's Python adapter: its own, or (plan 8 MVP-9.3) the adapter of another instance of a system whose
    adapter makes instances (plm_wc_2 → the Windchill adapter, reading as plm_wc_2)."""
    if source_id in ADAPTERS:
        return ADAPTERS[source_id]
    base, _, n = source_id.rpartition("_")
    make = getattr(ADAPTERS.get(base), "instance", None)
    return make(source_id) if n.isdigit() and make is not None else None


def adapter_for(s, source_id: str) -> Adapter | None:
    """The Python adapter if the source has one; else a ConfiguredAdapter on its stored connection (with the source's
    field mapping), when it has one with resources to read; else None."""
    if (a := python_adapter(source_id)) is not None:
        return a
    from di.connectors.configured import ConfiguredAdapter, active_rows
    from di.connectors.connection import connection_for

    conn = connection_for(s, source_id)
    if conn is None or not conn.resources:
        return None
    return ConfiguredAdapter(conn, active_rows(s, source_id))


def has_adapter(s, source_id: str) -> bool:
    """A sync can read this source: a Python adapter, or a stored connection with resources."""
    if python_adapter(source_id) is not None:
        return True
    from sqlalchemy import text

    return bool(
        s.execute(
            text("SELECT 1 FROM source_connection WHERE source_id = :i AND jsonb_array_length(resources) > 0"),
            {"i": source_id},
        ).first()
    )
