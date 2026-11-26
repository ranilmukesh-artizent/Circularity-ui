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


# The pack each extra system serves (a pack file's key, di.services.modeler.pack.pack_keys). A system lists under the one
# pack whose story reads it; the Connection Fabric shows them grouped by pack (`pack_systems`). A new extra adapter is
# added here too: tests/test_fabric_pack_systems.py fails for one that has no pack.
PACK_OF: dict[str, str] = {
    "plm_wc": "industrial",
    "dvreg": "device", "dvlab": "device", "dvmkt": "device",
    "tooltel": "tool_fleet", "sdesk": "tool_fleet", "fleet": "tool_fleet", "parts": "tool_fleet", "rephist": "tool_fleet",
    "repairlog": "tool_fleet", "recall": "tool_fleet",
    "uc_dms": "used_cars", "uc_auction": "used_cars", "uc_insp": "used_cars", "uc_lease": "used_cars",
    "uc_price": "used_cars", "uc_recall": "used_cars", "uc_title": "used_cars",
    "tn_inv": "telecom_network", "tn_decom": "telecom_network", "tn_bench": "telecom_network",
    "tn_spares": "telecom_network", "tn_recycler": "telecom_network", "tn_broker": "telecom_network",
    "mr_rental": "medical_rental", "mr_assets": "medical_rental", "mr_biomed": "medical_rental",
    "mr_decon": "medical_rental", "mr_parts": "medical_rental", "mr_disposal": "medical_rental",
    "it_cmdb": "itad", "it_logistics": "itad",
    "rf_rental": "rental_fleet", "bat_bms": "battery", "core_ret": "auto_core", "mc_tradein": "medical_capital",
    "cpe_bss": "telecom_cpe", "b2c_ret": "b2c_serial",
}  # fmt: skip


def label_of(base: str) -> str:
    """A readable name: the adapter's vendor label without its "(synthetic)" mark ("Dealer management system")."""
    return str(getattr(ADAPTERS[base], "vendor", base)).removesuffix(" (synthetic)")


def systems(s: Session) -> list[dict[str, Any]]:
    """Every extra system: id, name, vendor (the adapter's label), type, pack (key, "" when unmapped) and whether a source
    with its id is registered. Sorted by pack, then name. A read: it registers nothing."""
    taken = set(s.execute(text("SELECT id FROM source_system")).scalars())
    rows = [
        {"id": b, "name": label_of(b), "vendor": str(getattr(a, "vendor", b)), "type": str(getattr(a, "source_type", "")),
         "pack": PACK_OF.get(b, ""), "registered": b in taken}
        for b, a in ADAPTERS.items() if is_extra(b)
    ]  # fmt: skip
    return sorted(rows, key=lambda r: (r["pack"], r["name"]))


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
