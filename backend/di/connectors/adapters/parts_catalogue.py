"""Tool service, stock and trade demand (parts, plan 9 P9-3.2): open repair orders, the spare-parts catalogue, the
refurbished stock, certified pre-owned sales orders, tool pool requests and dealer trade bids. Read only.

Written against source-sim's synthetic parts mock (source-sim/sim/generic/specs/parts_catalogue.py): no real system is
connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`); `?updated_since=` delta reads.

Not one of the demo's 21 sources: it starts unregistered, so every demo screen and count is unchanged
(di.connectors.extra registers it, source.reconnect connects it). It implements no registry entry of its own: it fills the
canonical models `demand` and `stock_unit` that the tool-fleet pack's queue reads. Nothing is ever written to the source.

Resources and facts
    openRepairOrders  demand.<roId>          kind `wo`, part_name, tool_class, backorder, need_by, buyer (the customer)
    salesOrders       demand.<soId>          kind `so`, tool_class, site, need_by, price, buyer
    poolRequests      demand.<requestId>     kind `proj`, site, tool_class, need_by, amount (= avoidedPurchase), order_ref
                                             (= quoteRef)
    bids              demand.<bidId>         kind `bid`, tool_class, grade_min, price, expires, buyer (the dealer)
    stock             stock_unit.<unitId>    unit_id, serial, tool_class, grade, rul_pct, site, status, refurbished_at
    catalogue         no fact: the price list is read from the raw records
"""

from collections.abc import Iterator
from typing import Any

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

REPAIR_ORDER = {
    "partName": "part_name", "toolClass": "tool_class", "backorder": "backorder", "needBy": "need_by", "customer": "buyer",
}  # fmt: skip
SALES_ORDER = {"toolClass": "tool_class", "site": "site", "needBy": "need_by", "price": "price", "customer": "buyer"}
POOL_REQUEST = {
    "site": "site", "toolClass": "tool_class", "needBy": "need_by", "avoidedPurchase": "amount", "quoteRef": "order_ref",
}  # fmt: skip
BID = {"toolClass": "tool_class", "gradeMin": "grade_min", "price": "price", "expires": "expires", "dealer": "buyer"}
UNIT = {
    "unitId": "unit_id", "serial": "serial", "toolClass": "tool_class", "grade": "grade", "rulPct": "rul_pct", "site": "site",
    "status": "status", "refurbishedAt": "refurbished_at",
}  # fmt: skip
DEMAND = {  # resource: (id field, kind, fields)
    "openRepairOrders": ("roId", "wo", REPAIR_ORDER), "salesOrders": ("soId", "so", SALES_ORDER),
    "poolRequests": ("requestId", "proj", POOL_REQUEST), "bids": ("bidId", "bid", BID),
}  # fmt: skip


def facts_of(model: str, key: str, doc: dict[str, Any], names: dict[str, str], transform: str) -> list[Fact]:
    return keep([Fact(model, key, to, doc.get(src), src, doc.get(src), transform) for src, to in names.items()])


class PartsCatalogueAdapter(GenericAdapter):
    source_id = "parts"
    base_path = "/parts/api"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Tool service, stock and trade demand (synthetic)"
    source_type = "parts"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [
            Resource("openRepairOrders", self.read("openRepairOrders", "/repair-orders/open", "roId")),
            Resource("catalogue", self.read("catalogue", "/catalogue", "partNo")),
            Resource("stock", self.read("stock", "/refurbished-units", "unitId")),
            Resource("salesOrders", self.read("salesOrders", "/sales-orders", "soId")),
            Resource("poolRequests", self.read("poolRequests", "/pool-requests", "requestId")),
            Resource("bids", self.read("bids", "/trade-bids", "bidId")),
        ]

    def read(self, name: str, path: str, id_field: str):
        def reader(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, name, path, id_field, since)

        return reader

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "stock":
            return facts_of("stock_unit", p["unitId"], p, UNIT, "Camel case to snake case")
        if record.resource in DEMAND:
            id_field, kind, names = DEMAND[record.resource]
            key = p[id_field]
            head = Fact("demand", key, "kind", kind, id_field, key, "Demand kind of the resource")
            return [head, *facts_of("demand", key, p, names, "Camel case to snake case")]
        return []  # the catalogue is read from the raw records


ADAPTER = PartsCatalogueAdapter()
