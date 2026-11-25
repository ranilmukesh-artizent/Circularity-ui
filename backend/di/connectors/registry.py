"""Adapters are discovered from di/connectors/adapters/*.py, each defining ADAPTER = <Adapter instance>.

adapter_for(s, "erp")       → the Python adapter of a demo source
adapter_for(s, "workday")   → a ConfiguredAdapter on the source's stored connection (plan 6 A3), or None

Plan 9 P9-8.1 (entry I-18) adds the adapter registry beside them: `catalogue_entries()` (the connection templates and the
generic REST connector as `RegistryEntry`, pure) and `access_of(rw_label)`. Saved entries (kinds generic_rest and
from_spec) are rows read by di.repositories.adapter_registry; connections are made by di.services.actions.connections.
Never reads a secret: an entry's `spec` holds connection fields only.
"""

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import Any, Literal

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


# ---------------------------------------------------------------- the adapter registry (plan 9 P9-8.1, entry I-18)
ConnectorKind = Literal["catalogue", "generic_rest", "from_spec"]
Environment = Literal["test", "production"]
Access = Literal["read", "read_write"]
EntryStatus = Literal["draft", "tested", "released", "deprecated"]
GENERIC_REST_ID = "generic-rest"
GENERIC_AUTH_METHODS = ("none", "api_key", "bearer", "basic", "oauth_cc")
_PRIVATE_SPEC_KEYS = ("demo_secret", "maps")  # a template's synthetic credential and mapping rows are not connection fields


@dataclass(frozen=True)
class RegistryEntry:
    """One connector a person can start a connection from. `catalogue` entries are code (one per template of
    di.connectors.catalog); `generic_rest` and `from_spec` entries are rows of table adapter_registry."""

    id: str
    version: int
    kind: ConnectorKind
    system_type: str
    vendor_family: str
    auth_methods: tuple[str, ...]
    resources: tuple[dict[str, Any], ...]
    canonical_entities: tuple[str, ...]
    write_actions: tuple[str, ...]
    status: EntryStatus
    maintainer: str
    source_licence: str | None
    spec: dict[str, Any]
    org_unit_id: str | None

    def public(self) -> dict[str, Any]:
        """The entry as a screen or an agent sees it (never a secret: a spec holds connection fields only)."""
        return {
            "id": self.id, "version": self.version, "kind": self.kind, "system_type": self.system_type,
            "vendor_family": self.vendor_family, "auth_methods": list(self.auth_methods), "resources": list(self.resources),
            "canonical_entities": list(self.canonical_entities), "write_actions": list(self.write_actions),
            "status": self.status, "maintainer": self.maintainer, "source_licence": self.source_licence,
            "spec": self.spec, "org_unit_id": self.org_unit_id,
        }  # fmt: skip


def access_of(rw_label: str) -> Access:
    """The access a source's `rw` label says: "Read" is `read`, "Read / write" is `read_write`, anything else `read`.
    The source description's `rw` stays the one truth for access (no access column)."""
    return "read_write" if rw_label == "Read / write" else "read"


def _catalogue_entry(c: dict[str, Any]) -> RegistryEntry | None:
    from di.connectors import catalog

    tpl = catalog.template(c["id"])
    if tpl is None:
        return None
    spec = {k: v for k, v in tpl.items() if k not in _PRIVATE_SPEC_KEYS}
    return RegistryEntry(
        id=c["id"], version=1, kind="catalogue", system_type=c["type"], vendor_family=c["vendor"],
        auth_methods=(tpl["auth_kind"],), resources=tuple(tpl["resources"]),
        canonical_entities=tuple(sorted({m["model"] for m in tpl["maps"]})), write_actions=(), status="released",
        maintainer="Circularity", source_licence=None, spec=spec, org_unit_id=None,
    )  # fmt: skip


def catalogue_entries() -> list[RegistryEntry]:
    """One `catalogue` entry per connection template (di.connectors.catalog; status released, `spec` its connection
    fields), then the one `generic_rest` entry. Pure: no database."""
    from di.core import golden

    out = [e for c in golden.load("screens/reference")["CATALOG"] if (e := _catalogue_entry(c)) is not None]
    out.append(
        RegistryEntry(
            id=GENERIC_REST_ID,
            version=1,
            kind="generic_rest",
            system_type="api",
            vendor_family="Generic REST",
            auth_methods=GENERIC_AUTH_METHODS,
            resources=(),
            canonical_entities=(),
            write_actions=(),
            status="released",
            maintainer="Circularity",
            source_licence=None,
            spec={},
            org_unit_id=None,
        )  # fmt: skip
    )
    return out
