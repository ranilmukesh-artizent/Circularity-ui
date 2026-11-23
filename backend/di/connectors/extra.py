"""Connectors beyond the demo's 21 sources (plan 8, MVP-9.3): PTC Windchill (plm_wc).

Such an adapter (`extra = True`, with `vendor`, `source_type`, `interval`, `owner`) starts unregistered: no
source_system row, so every demo screen and count stays the demo's. A source row appears when a person registers one:

    register(s, "plm_wc", "Customer A")   → "plm_wc" (then "plm_wc_2", "plm_wc_3" ... for more instances), disconnected
    ensure_registered(s, "plm_wc")        → source.reconnect on an unregistered one registers it (shared) first

Then source.reconnect connects it (live, a sync queued). The demo reset removes these rows like any source created in
the Connection Fabric (di.connectors.sync.reset_sources). No commit here: the caller's transaction.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.connectors.registry import ADAPTERS, python_adapter


def _insert(s: Session, sid: str, base: str, org_unit_id: str | None) -> None:
    a: Any = ADAPTERS[base]  # an extra adapter: vendor, source_type, interval, owner
    s.execute(
        text(
            "INSERT INTO source_system (id, vendor, type, status, interval_min, owner, org_unit_id) "
            "VALUES (:i, :v, :t, 'disconnected', :iv, :o, :org)"
        ),
        {"i": sid, "v": a.vendor, "t": a.source_type, "iv": a.interval, "o": a.owner, "org": org_unit_id},
    )


def is_extra(base: str) -> bool:
    return bool(getattr(ADAPTERS.get(base), "extra", False))


def register(s: Session, base: str, org_unit_id: str | None = None) -> str:
    """A new disconnected source of the extra system `base`, bound to `org_unit_id` (None: shared): `base` when free,
    else base_2, base_3 ... Raises KeyError for a system that is not an extra one."""
    if not is_extra(base):
        raise KeyError(f"No extra connector {base}")
    taken = set(s.execute(text("SELECT id FROM source_system")).scalars())
    sid, n = base, 2
    while sid in taken:
        sid, n = f"{base}_{n}", n + 1
    _insert(s, sid, base, org_unit_id)
    return sid


def ensure_registered(s: Session, sid: str) -> bool:
    """Register `sid` (shared) when it is an extra system's source without a row. True when it registered it."""
    a = python_adapter(sid)
    base = sid if sid in ADAPTERS else sid.rpartition("_")[0]
    if a is None or not is_extra(base):
        return False
    if s.execute(text("SELECT 1 FROM source_system WHERE id = :i"), {"i": sid}).first() is not None:
        return False
    _insert(s, sid, base, None)
    return True
