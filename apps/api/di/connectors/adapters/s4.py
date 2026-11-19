"""SAP S/4HANA (erp): finance only — inventory valuation, stock, purchase baseline (the demo's SOURCES.erp).

OData v2 over Basic auth (communication user). Delta reads by LastChangeDateTime.

Facts
    asset.<MATNR>        book_value (USD), stock_plant, stock_location (plant decoded: 2010 → Warehouse 1), stock_qty
    demand.PO-<EBELN>    kind = purchase_plan, purchase_baseline (USD from INR at the dated rate), purchase_baseline_inr,
                         ship_to_site (plant decoded: 1030 → Site 3), qty, cancelled (deletion flag)
The demo's mapping: EKPO-NETPR ₹10,02,000.00 INR → demand.purchase_baseline $12,000.00 USD, "Currency at 83.5
(rate dated 2026-10-06)"; EKPO-WERKS 1030 → Site 3.
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import Basic, SourceClient

SRV = "/sap/opu/odata/sap"
INR_PER_USD = Decimal("83.5")
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"
PAGE = 200
FACILITY_PLANTS = {"2010": "Warehouse 1", "2020": "Warehouse 2", "2030": "Repair centre"}


def plant_name(werks: str | None) -> str | None:
    if not werks:
        return None
    if werks in FACILITY_PLANTS:
        return FACILITY_PLANTS[werks]
    m = re.fullmatch(r"10(\d)0", werks)
    return f"Site {m[1]}" if m else werks


def odata_time(v: str | None) -> str | None:
    """'/Date(1791363600000+0000)/' → ISO 8601 UTC."""
    m = re.match(r"/Date\((-?\d+)", v or "")
    return datetime.fromtimestamp(int(m[1]) / 1000, UTC).isoformat() if m else None


def usd(inr: Decimal) -> float:
    return float((inr / INR_PER_USD).quantize(Decimal("0.01")))


class S4Adapter(Adapter):
    source_id = "erp"

    def auth(self):
        return Basic("DI_CONNECTOR", "Circularity-demo-1")

    def resources(self):
        return [
            Resource("product", self.read_products),
            Resource("stock", self.read_stock),
            Resource("purchase_order", self.read_purchase_orders),
        ]

    # ------------------------------------------------------------- reading
    def _pages(self, client: SourceClient, path: str, params: dict, since: str | None) -> Iterator[tuple[dict, str]]:
        if since:
            stamp = since.replace("+00:00", "Z")
            f = f"LastChangeDateTime gt datetimeoffset'{stamp}'"
            params = params | {"$filter": f"({params['$filter']}) and {f}" if "$filter" in params else f}
        skip = 0
        while True:
            q = params | {"$top": str(PAGE), "$skip": str(skip), "$format": "json"}
            r = client.request("GET", path, params=q)
            rows = r.json()["d"]["results"]
            client.note_records(len(rows))
            for row in rows:
                yield row, str(r.request.url)
            if len(rows) < PAGE:
                return
            skip += PAGE

    def read_products(self, client, since):
        for row, url in self._pages(client, f"{SRV}/API_PRODUCT_SRV/A_Product", {"$expand": "to_Valuation"}, since):
            yield Record("product", row["Product"], row, url, odata_time(row.get("LastChangeDateTime")))

    def read_stock(self, client, since):
        path = f"{SRV}/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod"
        for row, url in self._pages(client, path, {"$filter": "InventoryStockType eq '01'"}, since):
            ext = f"{row['Material']}|{row['Plant']}|{row['StorageLocation']}"
            yield Record("stock", ext, row, url, odata_time(row.get("LastChangeDateTime")))

    def read_purchase_orders(self, client, since):
        for row, url in self._pages(
            client, f"{SRV}/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder", {"$expand": "to_PurchaseOrderItem"}, since
        ):
            yield Record("purchase_order", row["PurchaseOrder"], row, url, odata_time(row.get("LastChangeDateTime")))

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "product":
            vals = (p.get("to_Valuation") or {}).get("results") or []
            if not vals:
                return []
            v = vals[0]
            price = Decimal(v["StandardPrice"])
            return [
                Fact(
                    "asset",
                    p["Product"],
                    "book_value",
                    usd(price),
                    "MBEW-STPRS",
                    f"{v['StandardPrice']} {v['Currency']}",
                    RATE_NOTE,
                )
            ]
        if record.resource == "stock":
            qty = Decimal(p["MatlWrhsStkQtyInMatlBaseUnit"])
            if qty <= 0:
                return []  # an emptied location after a transfer says nothing about where the asset is
            key = p["Material"]
            return [
                Fact("asset", key, "stock_plant", p["Plant"], "MARD-WERKS", p["Plant"], "Pass-through"),
                Fact("asset", key, "stock_location", plant_name(p["Plant"]), "MARD-WERKS", p["Plant"], "Plant code lookup"),
                Fact("asset", key, "stock_qty", float(qty), "MARD-LABST", p["MatlWrhsStkQtyInMatlBaseUnit"], "Decimal"),
            ]
        if record.resource == "purchase_order":
            items = (p.get("to_PurchaseOrderItem") or {}).get("results") or []
            if not items:
                return []
            it = items[0]
            key = f"PO-{p['PurchaseOrder']}"
            inr = Decimal(it["NetPriceAmount"]) * Decimal(it.get("OrderQuantity") or "1")
            status = "confirmed" if p.get("PurchasingDocumentCategory") == "F" else "planned"
            return [
                Fact(
                    "demand", key, "kind", "purchase_plan", "EKKO-BSTYP", p.get("PurchasingDocumentCategory"), "Document category"
                ),
                Fact(
                    "demand",
                    key,
                    "purchase_baseline",
                    usd(inr),
                    "EKPO-NETPR",
                    f"{it['NetPriceAmount']} {it['DocumentCurrency']}",
                    RATE_NOTE,
                ),
                Fact("demand", key, "purchase_baseline_inr", float(inr), "EKPO-NETPR", it["NetPriceAmount"], "Pass-through"),
                Fact(
                    "demand", key, "ship_to_site", plant_name(it.get("Plant")), "EKPO-WERKS", it.get("Plant"), "Plant code lookup"
                ),
                Fact(
                    "demand",
                    key,
                    "qty",
                    float(Decimal(it.get("OrderQuantity") or "1")),
                    "EKPO-MENGE",
                    it.get("OrderQuantity"),
                    "Integer",
                ),
                Fact(
                    "demand",
                    key,
                    "status",
                    status,
                    "EKKO-BSTYP",
                    p.get("PurchasingDocumentCategory"),
                    "Status map: F → confirmed",
                ),
                Fact(
                    "demand",
                    key,
                    "cancelled",
                    bool(it.get("PurchasingDocumentDeletionCode")),
                    "EKPO-LOEKZ",
                    it.get("PurchasingDocumentDeletionCode"),
                    "Deletion flag",
                ),
            ]
        return []


ADAPTER = S4Adapter()
