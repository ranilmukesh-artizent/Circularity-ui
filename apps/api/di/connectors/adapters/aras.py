"""Aras Innovator (bom): parts, part BOMs, manufacturer parts (the demo's SOURCES.bom). Read only.

OAuth client credentials (token at /oauthserver/connect/token), OData-style $top/$skiptoken paging.
Aras keeps the bill of materials per product configuration (the product Part's item_number is Teamcenter's ITEM_ID),
not per asset. One record per product joins the product with its assemblies (Part BOM lines, sort order), each
assembly's spare parts and the manufacturer parts. The assets built to that configuration come from the canonical
store (asset.configuration_item, which the Teamcenter adapter records), so sync Teamcenter first; a product whose assets
are not known yet gives no facts until the next sync. The structure is read in full every time (delta=False): a
multi-level BOM can only be rebuilt from all its lines.

Facts (bom has authority over the part structure)
    asset.<asset>   components (list: name, part, qty, harvestable, state, spare_parts), harvestable_components,
                    bom_item, bom_revision, bom_state, manufacturer_parts
The demo's mapping: Part.item_number P-55-ROT-01 → asset.components[0] Rotor assembly (Part name lookup); Part BOM.quantity
1 → components[0].qty 1 (Integer); Part.state Released → released (State map).
"""

from sqlalchemy import text

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep, to_usd


class ArasAdapter(GenericAdapter):
    source_id = "bom"
    base_path = "/aras/InnovatorServer/odata"
    token_path = "/oauthserver/connect/token"
    items_key, next_key, next_param, size_param, page_size = "value", "@odata.skipToken", "$skiptoken", "$top", 200

    def resources(self):
        return [Resource("structure", self.read_structure, delta=False)]

    def read_structure(self, client, since):
        parts = {p["id"]: p for p in self.read_all(client, "/Part")}
        lines: dict[str, list[dict]] = {}
        for b in self.read_all(client, "/Part_BOM"):
            lines.setdefault(b["source_id"], []).append(b)
        mparts: dict[str, list[dict]] = {}
        for m in self.read_all(client, "/Manufacturer_Part"):
            mparts.setdefault(m["part_id"], []).append(m)
        assets: dict[str, list[str]] = {}
        for key, item in client.session.execute(
            text(
                "SELECT key, value #>> '{}' FROM provenance WHERE model = 'asset' AND field = 'configuration_item' "
                "ORDER BY key"
            )
        ).all():
            if item and key not in assets.setdefault(item, []):
                assets[item].append(key)
        url = client.url("/Part")

        def children(part_id: str) -> list[dict]:
            out = []
            for b in sorted(lines.get(part_id, []), key=lambda b: b.get("sort_order") or 0):
                child = parts.get(b["related_id"])
                if child:
                    out.append({"line": b, "part": child, "children": children(child["id"]), "mfr": mparts.get(child["id"], [])})
            return out

        for p in sorted(parts.values(), key=lambda p: p["item_number"]):
            if p.get("classification") != "Product":
                continue
            payload = {
                "product": p,
                "structure": children(p["id"]),
                "manufacturer_parts": mparts.get(p["id"], []),
                "assets": assets.get(p["item_number"], []),
            }
            yield Record("structure", p["item_number"], payload, url)

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        product = p["product"]
        components = []
        for node in p["structure"]:
            part, line = node["part"], node["line"]
            components.append(
                {
                    "name": part["name"],
                    "part": part["item_number"],
                    "qty": int(line.get("quantity") or 1),
                    "harvestable": bool(part.get("harvestable")),
                    "state": (part.get("state") or "").lower(),
                    "spare_parts": [
                        {
                            "name": c["part"]["name"],
                            "part": c["part"]["item_number"],
                            "qty": int(c["line"].get("quantity") or 1),
                            "unit_cost": to_usd(c["part"]["cost"], c["part"].get("cost_currency") or "USD")
                            if c["part"].get("cost") is not None
                            else None,
                            "manufacturer": c["mfr"][0]["manufacturer"] if c["mfr"] else None,
                        }
                        for c in node["children"]
                    ],
                }
            )
        nums = [n["part"]["item_number"] for n in p["structure"]]
        facts = []
        for key in p["assets"]:
            facts += [
                Fact("asset", key, "components", components, "Part.item_number", nums, "Part name lookup"),
                Fact(
                    "asset",
                    key,
                    "harvestable_components",
                    [c["name"] for c in components if c["harvestable"]],
                    "Part.harvestable",
                    [n["part"].get("harvestable") for n in p["structure"]],
                    "Flag",
                ),
                Fact(
                    "asset", key, "bom_item", product["item_number"], "Part.item_number", product["item_number"], "Pass-through"
                ),
                Fact(
                    "asset",
                    key,
                    "bom_revision",
                    product.get("major_rev"),
                    "Part.major_rev",
                    product.get("major_rev"),
                    "Pass-through",
                ),
                Fact(
                    "asset",
                    key,
                    "bom_state",
                    (product.get("state") or "").lower() or None,
                    "Part.state",
                    product.get("state"),
                    "State map",
                ),
                Fact(
                    "asset",
                    key,
                    "manufacturer_parts",
                    [{"manufacturer": m["manufacturer"], "part": m["item_number"]} for m in p["manufacturer_parts"]],
                    "Manufacturer Part.item_number",
                    [m["item_number"] for m in p["manufacturer_parts"]],
                    "Pass-through",
                ),
            ]
        return keep(facts)


ADAPTER = ArasAdapter()
