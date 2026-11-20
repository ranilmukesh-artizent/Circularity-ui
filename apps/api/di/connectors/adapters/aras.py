"""Aras Innovator (bom): parts, part BOMs, manufacturer parts (the demo's SOURCES.bom). Read only.

The RESTful API (OData v4) under /aras/InnovatorServer/server/odata with a bearer token from the Innovator OAuth
server (POST /aras/InnovatorServer/oauthserver/connect/token, password grant: client_id IOMApp, scope Innovator,
username, the MD5 hash of the password, database). Each product Part (classification Product; its item_number is
Teamcenter's ITEM_ID) is read with its structure in one request: $expand of Part BOM -> related_id (the assemblies) ->
Part BOM -> related_id (the spare parts) -> Part AML -> related_id (Manufacturer Part) -> manufacturer, paged with
Prefer: odata.maxpagesize and @odata.nextLink.

Aras keeps the bill of materials per product configuration, not per asset. The assets built to a configuration come
from the canonical store (asset.configuration_item, which the Teamcenter adapter records), so sync Teamcenter first.
Delta read: the ids of every Part, Part BOM, Part AML and Manufacturer Part with modified_on after the cursor
($filter=modified_on gt '...'); a product is read again when its structure holds one of them, or when it has assets
that hold no BOM facts yet (Teamcenter synced after Aras). The cursor is the newest modified_on in a structure.

Facts (bom has authority over the part structure)
    asset.<asset>   components (list: name, part, qty, harvestable, state, spare_parts), harvestable_components,
                    bom_item, bom_revision, bom_state, manufacturer_parts
The demo's mapping: Part.item_number P-55-ROT-01 → asset.components[0] Rotor assembly (Part name lookup); Part BOM.quantity
1 → components[0].qty 1 (Integer); Part.state Released → released (State map).
"""

import hashlib
import time
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import text

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import keep, to_usd
from di.connectors.http import Auth, SourceClient, SourceError

ODATA = "/aras/InnovatorServer/server/odata"
TOKEN = "/aras/InnovatorServer/oauthserver/connect/token"  # noqa: S105 - a URL path, not a secret
PAGE = 25
PART = "item_number,name,state,major_rev,classification,nf_harvestable,cost,nf_cost_currency,modified_on"
AML = "Part AML($select=modified_on;$expand=related_id($select=item_number,modified_on;$expand=manufacturer($select=name)))"
LINE = "$select=quantity,sort_order,modified_on"
EXPAND = (
    f"Part BOM({LINE};$expand=related_id($select={PART};$expand=Part BOM({LINE};"
    f"$expand=related_id($select={PART};$expand={AML})))),{AML}"
)


class ArasPassword(Auth):
    """OAuth 2.0 password grant against the Innovator OAuth server; the token is cached until it expires."""

    def __init__(self, username: str, password: str, database: str):
        self.username, self.database = username, database
        self.password_md5 = hashlib.md5(password.encode()).hexdigest()  # noqa: S324 - Aras logins send the MD5 of the password (the vendor's protocol)
        self.token: str | None = None
        self.expires = 0.0

    def headers(self, client: SourceClient, force_refresh: bool = False) -> dict[str, str]:
        if force_refresh or not self.token or self.expires < time.time() + 30:
            token_url = client.base_url.removesuffix(ODATA) + TOKEN
            form = {
                "grant_type": "password",
                "scope": "Innovator",
                "client_id": "IOMApp",
                "username": self.username,
                "password": self.password_md5,
                "database": self.database,
            }
            r = client.raw("POST", token_url, data=form, log_records=False)
            if r.status_code != 200:
                raise SourceError("auth", f"bom: token request failed: HTTP {r.status_code} {r.text[:200]}", r.status_code)
            body = r.json()
            self.token, self.expires = body["access_token"], time.time() + float(body.get("expires_in", 3600))
        return {"Authorization": "Bearer " + self.token}


def aras_stamp(iso: str) -> str:
    """ISO 8601 → Innovator's date-time (no offset, the server's zone: UTC)."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def utc_iso(stamp: str) -> str:
    return datetime.fromisoformat(stamp).replace(tzinfo=UTC).isoformat()


class ArasAdapter(Adapter):
    source_id = "bom"
    base_path = ODATA

    def auth(self):
        return ArasPassword("di-connector", "Circularity-demo-aras-1", "InnovatorDB")

    def resources(self):
        return [Resource("structure", self.read_structure)]

    # ------------------------------------------------------------- reading
    def collection(self, client: SourceClient, path: str, params: dict) -> Iterator[tuple[dict, str]]:
        """Every entity of a collection, following @odata.nextLink."""
        url, q = path, params
        while url:
            r = client.request("GET", url, params=q, headers={"Prefer": f"odata.maxpagesize={PAGE}"})
            body = r.json()
            client.note_records(len(body["value"]))
            for row in body["value"]:
                yield row, str(r.request.url)
            url, q = body.get("@odata.nextLink"), None

    def changed_ids(self, client: SourceClient, since: str) -> set[str]:
        flt = f"modified_on gt '{aras_stamp(since)}'"
        ids: set[str] = set()
        for itemtype in ("Part", "Part BOM", "Part AML", "Manufacturer Part"):
            ids |= {row["id"] for row, _ in self.collection(client, f"/{itemtype}", {"$filter": flt, "$select": "id"})}
        return ids

    def read_structure(self, client: SourceClient, since: str | None) -> Iterator[Record]:
        assets: dict[str, list[str]] = {}
        for key, item in client.session.execute(
            text(
                "SELECT key, value #>> '{}' FROM provenance WHERE model = 'asset' AND field = 'configuration_item' "
                "AND source_id = 'plm' ORDER BY key"
            )
        ).all():
            if item and key not in assets.setdefault(item, []):
                assets[item].append(key)
        changed: set[str] | None = None
        pending: set[str] = set()
        if since:
            changed = self.changed_ids(client, since)
            done = {
                k
                for (k,) in client.session.execute(
                    text("SELECT DISTINCT key FROM provenance WHERE model = 'asset' AND field = 'bom_item' AND source_id = 'bom'")
                ).all()
            }
            pending = {item for item, keys in assets.items() if any(k not in done for k in keys)}
            if not changed and not pending:
                return
        params = {"$filter": "classification eq 'Product'", "$select": PART, "$expand": EXPAND, "$orderby": "item_number"}
        for product, url in self.collection(client, "/Part", params):
            structure, ids, stamps = self._tree(product)
            if changed is not None and not (ids & changed) and product["item_number"] not in pending:
                continue
            payload = {
                "product": self._part(product),
                "structure": structure,
                "manufacturer_parts": self._aml(product),
                "assets": assets.get(product["item_number"], []),
            }
            yield Record("structure", product["item_number"], payload, url, utc_iso(max(stamps)))

    @staticmethod
    def _part(p: dict) -> dict:
        return {
            "id": p["id"],
            "item_number": p["item_number"],
            "name": p.get("name"),
            "state": p.get("state"),
            "major_rev": p.get("major_rev"),
            "classification": p.get("classification"),
            "harvestable": p.get("nf_harvestable") == "1",
            "cost": p.get("cost"),
            "cost_currency": p.get("nf_cost_currency"),
        }

    @staticmethod
    def _aml(p: dict) -> list[dict]:
        out = []
        for a in p.get("Part AML") or []:
            mp = a.get("related_id") or {}
            out.append({"manufacturer": (mp.get("manufacturer") or {}).get("name"), "item_number": mp.get("item_number")})
        return out

    def _tree(self, product: dict) -> tuple[list[dict], set[str], list[str]]:
        ids, stamps = {product["id"]}, [product["modified_on"]]

        def walk(part: dict) -> list[dict]:
            for a in part.get("Part AML") or []:
                ids.add(a["id"])
                stamps.append(a["modified_on"])
                if a.get("related_id"):
                    ids.add(a["related_id"]["id"])
                    stamps.append(a["related_id"]["modified_on"])
            nodes = []
            for line in part.get("Part BOM") or []:
                child = line.get("related_id")
                ids.add(line["id"])
                stamps.append(line["modified_on"])
                if not child:
                    continue
                ids.add(child["id"])
                stamps.append(child["modified_on"])
                nodes.append(
                    {
                        "line": {"id": line["id"], "quantity": line.get("quantity"), "sort_order": line.get("sort_order")},
                        "part": self._part(child),
                        "children": walk(child),
                        "mfr": self._aml(child),
                    }
                )
            return nodes

        return walk(product), ids, stamps

    # ------------------------------------------------------------- mapping
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
                    "Part.nf_harvestable",
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
