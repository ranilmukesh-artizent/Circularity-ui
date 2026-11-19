"""Optoro (rl): return receipts, disposition decisions, inbound shipments, carrier status (SOURCES.rl).

API key (X-Api-Key); page paging (?page=&per_page=, body {data, next_page, total_count}); ?updated_since= for delta
reads. Optoro reports times in the returns centre's local time (-04:00); they are stored in UTC.

Facts (rl has authority over return_ref, received_at, disposition)
    asset.<SKU>   return_ref (RMA_ID), received_at, case_ref (CLIENT_REF), return_id, return_receipt_status, return_reason_code,
                  receiving_facility, origin_site (returns)
                  disposition (RESTOCK → restock, REFURB → refurbish …), disposition_reason, disposition_status,
                  disposition_final (dispositions)
                  inbound_shipment_ref, inbound_load, inbound_carrier, inbound_tracking, inbound_delivered_at,
                  inbound_freight (USD), carrier_status (shipments)
                  return_authorization_ref, return_authorized_at, replacement_order (return authorisations)
The demo's mapping (MAPPINGS.rl): RMA_ID → asset.return_ref "Pass-through"; DISPOSITION REFURB → refurbish
"Disposition map"; RECEIVED_AT -04:00 → UTC "Timestamp to UTC". The seed gives RT-1048 RMA-56509, received
2026-10-03T15:28:00-04:00 and RESTOCK, not the demo's RMA-55820 / 2026-10-05T10:11 / REFURB.
"""

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import generic_pages, source_clock, utc
from di.connectors.http import ApiKey, SourceClient

DISPOSITION = {
    "RESTOCK": "restock",
    "REFURB": "refurbish",
    "RECYCLE": "recycle",
    "LIQUIDATE": "liquidate",
    "RETURN_TO_VENDOR": "return_to_vendor",
    "PENDING_INSPECTION": "pending_inspection",
}
RESOURCES = (
    ("returns", "/returns", "RETURN_ID"),
    ("dispositions", "/dispositions", "DISPOSITION_ID"),
    ("shipments", "/shipments", "SHIPMENT_ID"),
    ("return_authorizations", "/return-authorizations", "RA_ID"),
)


class OptoroAdapter(Adapter):
    source_id = "rl"
    base_path = "/optoro/v1"

    def auth(self):
        return ApiKey("X-Api-Key", "rl-demo-key")

    def __init__(self):
        self.sku_of_return: dict[str, str] = {}  # RETURN_ID → SKU (shipments name their return, not the SKU)

    def resources(self):
        return [Resource(name, self.reader(name, path, id_field)) for name, path, id_field in RESOURCES]

    def reader(self, name: str, path: str, id_field: str):
        def read(client: SourceClient, since):
            stamp = source_clock(client)
            for doc, url in generic_pages(
                client, path, since, items_key="data", next_key="next_page", next_param="page", size_param="per_page"
            ):
                if name == "returns" and doc.get("SKU"):
                    self.sku_of_return[doc["RETURN_ID"]] = doc["SKU"]
                elif name == "shipments" and doc.get("RETURN_ID") and doc["RETURN_ID"] not in self.sku_of_return:
                    ret = client.get_json(f"/returns/{doc['RETURN_ID']}")
                    if ret.get("SKU"):
                        self.sku_of_return[doc["RETURN_ID"]] = ret["SKU"]
                yield Record(name, str(doc[id_field]), doc, url, stamp)

        return read

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = p.get("SKU") or self.sku_of_return.get(p.get("RETURN_ID") or "")
        out: list[Fact] = []

        def fact(field, value, sf, transform, sv=None):
            if value is not None:
                out.append(Fact("asset", key, field, value, sf, p.get(sf) if sv is None else sv, transform))

        if not key:
            return []
        if record.resource == "returns":
            fact("return_ref", p.get("RMA_ID"), "RMA_ID", "Pass-through")
            fact("received_at", utc(p.get("RECEIVED_AT")), "RECEIVED_AT", "Timestamp to UTC")
            fact("case_ref", p.get("CLIENT_REF"), "CLIENT_REF", "Pass-through")
            fact("return_id", p.get("RETURN_ID"), "RETURN_ID", "Pass-through")
            fact("return_receipt_status", p.get("STATUS"), "STATUS", "Pass-through")
            fact("return_reason_code", p.get("RETURN_REASON"), "RETURN_REASON", "Pass-through")
            fact("receiving_facility", p.get("RECEIVING_FACILITY"), "RECEIVING_FACILITY", "Pass-through")
            fact("origin_site", p.get("ORIGIN_SITE"), "ORIGIN_SITE", "Pass-through")
        elif record.resource == "dispositions":
            d = p.get("DISPOSITION")
            fact("disposition", DISPOSITION.get(d, (d or "").lower() or None), "DISPOSITION", "Disposition map")
            fact("disposition_reason", p.get("DISPOSITION_REASON"), "DISPOSITION_REASON", "Pass-through")
            fact("disposition_status", p.get("STATUS"), "STATUS", "Pass-through")
            fact("disposition_final", p.get("FINAL"), "FINAL", "Boolean")
        elif record.resource == "shipments":
            fact("inbound_shipment_ref", p.get("SHIPMENT_ID"), "SHIPMENT_ID", "Pass-through")
            fact("inbound_load", p.get("TMS_LOAD_ID"), "TMS_LOAD_ID", "Pass-through")
            fact("inbound_carrier", p.get("CARRIER"), "CARRIER", "Pass-through")
            fact("inbound_tracking", p.get("TRACKING_NO"), "TRACKING_NO", "Pass-through")
            fact("inbound_delivered_at", utc(p.get("DELIVERED_AT")), "DELIVERED_AT", "Timestamp to UTC")
            if p.get("FREIGHT_USD") is not None:
                inr = p.get("FREIGHT_INR")
                sv = f"{p['FREIGHT_USD']:.2f} USD" + (f" ({inr:.2f} INR)" if inr is not None else "")
                fact("inbound_freight", float(p["FREIGHT_USD"]), "FREIGHT_USD", "Pass-through (USD)", sv)
            fact("carrier_status", p.get("CARRIER_STATUS"), "CARRIER_STATUS", "Pass-through")
        elif record.resource == "return_authorizations":
            fact("return_authorization_ref", p.get("RA_ID"), "RA_ID", "Pass-through")
            fact("return_authorized_at", utc(p.get("AUTHORIZED_AT")), "AUTHORIZED_AT", "Timestamp to UTC")
            fact("replacement_order", p.get("REPLACEMENT_ORDER"), "REPLACEMENT_ORDER", "Pass-through")
            fact("case_ref", p.get("CLIENT_REF"), "CLIENT_REF", "Pass-through")
        return out


ADAPTER = OptoroAdapter()
