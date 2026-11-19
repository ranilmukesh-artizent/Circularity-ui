"""Siemens Teamcenter (plm): product configuration, compatibility, approved alternates (the demo's SOURCES.plm). Read only.

API key header (X-TC-API-Key), startIndex/maxToLoad paging, `?updated_since=` deltas (see oracle_lease.GenericAdapter).
Teamcenter keeps items and alternates per product configuration and one compatibility rule per asset, so one record
per asset joins its rule with its item and the item's alternates. A delta read takes the rules that changed plus the
rules of every item or alternate that changed.

Facts (plm has authority over configuration and compatibility)
    asset.<ASSET_ID>   configuration (decoded name), configuration_item (ITEM_ID), config_revision, bom_ref,
                       config_properties, compatibility, config_status, compatible_items, approved_alternates,
                       target_use
The demo's mapping: ITEM_ID MTR-55-IE3-250M → asset.configuration "55 kW · IE3 · 250M" (Config decoded); ALT_APPROVED Y
→ compatible (Boolean); REV C → asset.bom_ref BOM-55-C (Revision prefix).
"""

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep


class TeamcenterAdapter(GenericAdapter):
    source_id = "plm"
    base_path = "/teamcenter/tc/rest"
    auth_kind, api_key_header = "api_key", "X-TC-API-Key"
    items_key, next_key, next_param, size_param, page_size = "objects", "nextStartIndex", "startIndex", "maxToLoad", 200

    def resources(self):
        return [Resource("compatibility", self.read_compatibility)]

    def read_compatibility(self, client, since):
        now = self.source_now(client)
        rules = {r["RULE_ID"]: (r, u) for r, u in self.pages(client, "/v1/compatibility", since)}
        if since:  # an item or alternate that changed changes the rules of its assets
            touched = {r["ITEM_ID"] for r, _ in self.pages(client, "/v1/items", since)}
            touched |= {r["ITEM_ID"] for r, _ in self.pages(client, "/v1/alternates", since)}
            for item in sorted(touched):
                for r, u in self.pages(client, "/v1/compatibility", ITEM_ID=item):
                    rules.setdefault(r["RULE_ID"], (r, u))
        if not rules:
            return
        items = {r["ITEM_ID"]: r for r in self.read_all(client, "/v1/items")}
        alternates: dict[str, list[dict]] = {}
        for a in self.read_all(client, "/v1/alternates"):
            alternates.setdefault(a["ITEM_ID"], []).append(a)
        for rule_id in sorted(rules):
            r, url = rules[rule_id]
            payload = r | {"item": items.get(r["ITEM_ID"]), "alternates": alternates.get(r["ITEM_ID"], [])}
            yield Record("compatibility", rule_id, payload, url, now)

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = p["ASSET_ID"]
        item = p.get("item") or {}
        approved = [a for a in p.get("alternates") or [] if a.get("ALT_APPROVED") == "Y"]
        ok = p.get("ALT_APPROVED") == "Y"
        compat = "compatible" if ok else "under_review" if p.get("COMPATIBILITY") == "UNDER_REVIEW" else "incompatible"
        return keep(
            [
                Fact("asset", key, "configuration", item.get("OBJECT_NAME"), "ITEM_ID", p["ITEM_ID"], "Config decoded"),
                Fact("asset", key, "configuration_item", p["ITEM_ID"], "ITEM_ID", p["ITEM_ID"], "Pass-through"),
                Fact("asset", key, "config_revision", p.get("REV"), "REV", p.get("REV"), "Pass-through"),
                Fact("asset", key, "bom_ref", item.get("BOM_REF"), "REV", p.get("REV"), "Revision prefix"),
                Fact(
                    "asset",
                    key,
                    "config_properties",
                    item.get("PROPERTIES"),
                    "PROPERTIES",
                    item.get("PROPERTIES"),
                    "Pass-through",
                ),
                Fact("asset", key, "compatibility", compat, "ALT_APPROVED", p.get("ALT_APPROVED"), "Boolean"),
                Fact(
                    "asset",
                    key,
                    "config_status",
                    (p.get("CONFIG_STATUS") or "").lower() or None,
                    "CONFIG_STATUS",
                    p.get("CONFIG_STATUS"),
                    "Status map",
                ),
                Fact(
                    "asset",
                    key,
                    "compatible_items",
                    p.get("COMPATIBLE_ITEMS"),
                    "COMPATIBLE_ITEMS",
                    p.get("COMPATIBLE_ITEMS"),
                    "Pass-through",
                ),
                Fact(
                    "asset",
                    key,
                    "approved_alternates",
                    [{"item": a["ALT_ITEM_ID"], "reason": a.get("REASON")} for a in approved],
                    "ALT_APPROVED",
                    [f"{a['ALT_ITEM_ID']}:{a['ALT_APPROVED']}" for a in p.get("alternates") or []],
                    "Approved alternates (ALT_APPROVED = Y)",
                ),
                Fact("asset", key, "target_use", p.get("TARGET_USE"), "TARGET_USE", p.get("TARGET_USE"), "Pass-through"),
            ]
        )


ADAPTER = TeamcenterAdapter()
