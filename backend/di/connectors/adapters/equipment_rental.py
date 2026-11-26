"""Equipment rental system (rf_rental, plan 9 P9-12.4): off-rent machines with their branch's utilisation, used price, damage
claims, purchase plans and idle days. Read only.

Written against source-sim's synthetic rental mock (source-sim/sim/vendors/equipment_rental): no real rental system is
connected. API key in `x-api-key`; unpaged lists, read in full (Resource.delta False).

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is unchanged
(di.connectors.extra registers it, source.reconnect connects it). It implements no registry entry of its own: it fills the
canonical model for a unit, keyed by the source's org unit (schema.serial_key) and the machine id.

Resource and facts
    machines   asset.<key>       machine_id, asset_class, hours, branch, age_years, book_value, owner_tenant, idle_days
               demand.<key>      branch_utilisation (the branch and class), purchase_plans (the plans of OTHER branches for the
                                 class: {branch, assetClass, qty}; absent when there are none)
               market.<key>      price_index (the used price of the class and the machine's 1,000-hour band)
               condition.<key>   damage_claims (the machine's claims: {claimId, renterRef, amount, photosRef}; absent when none)
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import serial_key
from di.services.canonical.store import Fact

ASSET = {
    "machineId": "machine_id", "assetClass": "asset_class", "hours": "hours", "branch": "branch", "ageYears": "age_years",
    "bookValue": "book_value",
}  # fmt: skip


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


def hours_band(hours: int | float) -> str:
    """The 1,000-hour band of a reading: 6,200 -> `6000-7000`."""
    low = int(hours) // 1000 * 1000
    return f"{low}-{low + 1000}"


class EquipmentRentalAdapter(GenericAdapter):
    source_id = "rf_rental"
    base_path = "/equipment-rental/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Equipment rental system (synthetic)"
    source_type = "equipment_rental"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def machines(client: SourceClient, _since: str | None) -> Iterator[Record]:
            org, url = _org(client), client.url("/off-rent")
            rows = client.get_json("/off-rent")
            client.note_records(len(rows))
            util = {(u["branch"], u["assetClass"]): u["utilisation"] for u in client.get_json("/utilisation")}
            claims = client.get_json("/damage-claims")
            plans = client.get_json("/purchase-plans")
            idle = {i["machineId"]: i["idleDays"] for i in client.get_json("/idle")}
            for row in rows:
                query = {"class": row["assetClass"], "hoursBand": hours_band(row["hours"])}
                price = client.get_json("/price-index", params=query)
                payload: dict[str, Any] = row | {
                    "org_unit_id": org,
                    "utilisation": util.get((row["branch"], row["assetClass"])),
                    "price": (price or {}).get("price"),
                    "claims": [c for c in claims if c["machineId"] == row["machineId"]],
                    "plans": [
                        {k: p[k] for k in ("branch", "assetClass", "qty")}
                        for p in plans
                        if p["assetClass"] == row["assetClass"] and p["branch"] != row["branch"]
                    ],
                    "idleDays": idle.get(row["machineId"]),
                }
                yield Record("machines", str(row["machineId"]), payload, url)

        return [Resource("machines", machines, delta=False)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = serial_key(p.get("org_unit_id"), p["machineId"])

        def fact(model: str, field: str, src: str, value: Any, how: str) -> Fact:
            return Fact(model, key, field, value, src, value, how)

        org, plans, claims = p.get("org_unit_id"), p.get("plans") or None, p.get("claims") or None
        facts = [fact("asset", to, src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        facts += [
            fact("asset", "owner_tenant", "org_unit_id", org, "The source's org"),
            fact("asset", "idle_days", "idleDays", p.get("idleDays"), "Days idle at the branch"),
            fact("demand", "branch_utilisation", "utilisation", p.get("utilisation"), "Utilisation of the branch and class"),
            fact("demand", "purchase_plans", "purchase-plans", plans, "Other branches planning to buy the class"),
            fact("market", "price_index", "price-index", p.get("price"), "Used price of the hours band"),
            fact("condition", "damage_claims", "damage-claims", claims, "Check-in damage claims"),
        ]
        return keep(facts)


ADAPTER = EquipmentRentalAdapter()
