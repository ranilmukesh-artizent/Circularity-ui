"""IBM Sterling OMS (oms): sales orders and lines, ship-to, need-by, returns, fulfilment (the demo's SOURCES.oms).

REST under /sterling/smcfs/restapi with an OAuth 2.0 client-credentials bearer. Lists page with PageNumber /
PageSize until IsLastPage = Y; deltas by FromModifyts (inclusive, to the second), so records stamped at the cursor
itself are read again and skipped here. Sterling has authority over the order line, the ship-to and the need-by date.

Facts
    demand.<OrderNo>   (sales orders, DocumentType 0001; the line that takes a returned unit, else the last line)
                       demand_id, line, kind (CONTRACT_REPLACEMENT → replacement), status (ExtnDemandStatus →
                       confirmed | forecast), order_status, buyer (BuyerOrganizationCode CUSTOMER_A → Customer A),
                       ship_to and location ("Site 3 · Chennai Foundry"), ship_to_key, ship_to_site, need_by, item,
                       item_desc, qty, unit_price (USD), accepts_refurbished, min_certified_months,
                       purchase_ref (the avoided purchase, PO-49048: S/4's demand.PO-49048),
                       once allocated / fulfilled: allocated_asset, reservation_ref, ship_node, shipment_ref, carrier,
                       shipped_at, delivered_at, pod_ref, pod_received_by
    asset.<SerialNo>   (return orders, DocumentType 0003) return_ref (RMA), return_received_at, return_status,
                       return_reason, return_reason_text, customer_intent, receiving_node, receipt_ref (WMS GR),
                       relase_ref (ExtnLeaseNo), item; for a unit allocated to a sales line: allocated_to (OrderNo)
The demo's mapping (MAPPINGS.oms): OrderNo SO-48102 → demand.demand_id; PrimeLineNo 10 → demand.line 10;
ShipToKey LOC-CHN-03 → demand.location "Site 3 · Chennai Foundry" ("Location lookup"; also written as
demand.ship_to, the field Sterling has authority over); ReqDeliveryDate 2026-10-17T00:00:00+05:30 → demand.need_by
2026-10-17 ("Date to ISO").
The receipt time is written as return_received_at, not asset.received_at: the returns system (rl, Optoro) owns
received_at and holds the scan time, while Sterling holds the received date only, so the two would always conflict.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import OAuthClientCredentials, SourceClient

API = "/sterling/smcfs/restapi"
PAGE = 200
STATUS_MAP = {"CONFIRMED": "confirmed", "FORECAST": "forecast"}
ORDER_KINDS: dict[str | None, str] = {"CONTRACT_REPLACEMENT": "replacement"}


def utc(v: str | None) -> str | None:
    """'2026-10-06T14:30:00+05:30' → '2026-10-06T09:00:00+00:00'."""
    return datetime.fromisoformat(v).astimezone(UTC).isoformat() if v else None


def tenant(code: str | None) -> str | None:
    """CUSTOMER_A → Customer A."""
    return code.replace("_", " ").title() if code else None


def number(v: str | None) -> int | float | None:
    if v in (None, ""):
        return None
    d = Decimal(v)
    return int(d) if d == d.to_integral_value() else float(d)


class SterlingAdapter(Adapter):
    source_id = "oms"

    def auth(self):
        return OAuthClientCredentials(f"{API}/oauth/token", "di-connector", "circularity-demo-sterling-secret")

    def resources(self):
        return [Resource("order", self.read_orders), Resource("return", self.read_returns)]

    # ------------------------------------------------------------- reading
    def _pages(self, client: SourceClient, resource: str, since: str | None) -> Iterator[Record]:
        params: dict = {"PageSize": PAGE}
        if since:
            params["FromModifyts"] = since
        page = 1
        while True:
            r = client.request("GET", f"{API}/{resource}", params=params | {"PageNumber": page})
            body = r.json()
            orders = body.get("Order") or []
            client.note_records(len(orders))
            for o in orders:
                changed = utc(o.get("Modifyts"))
                if since and changed and changed <= since:
                    continue  # FromModifyts is inclusive: already read at the cursor
                yield Record(resource, o["OrderNo"], o, str(r.request.url), changed)
            if body.get("IsLastPage", "Y") == "Y" or not orders:
                return
            page += 1

    def read_orders(self, client, since):
        return self._pages(client, "order", since)

    def read_returns(self, client, since):
        return self._pages(client, "return", since)

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        if record.resource == "order":
            return self._order(record.payload)
        if record.resource == "return":
            return self._return(record.payload)
        return []

    def _order(self, o: dict) -> list[Fact]:
        lines = (o.get("OrderLines") or {}).get("OrderLine") or []
        if not lines:
            return []
        ln = next((x for x in lines if (x.get("Extn") or {}).get("ExtnAcceptsRefurbished") == "Y"), lines[-1])
        key = o["OrderNo"]
        extn, lext = o.get("Extn") or {}, ln.get("Extn") or {}
        item = ln.get("Item") or {}
        ship = o.get("PersonInfoShipTo") or {}
        ship_key = ln.get("ShipToKey") or o.get("ShipToKey")
        site, site_name = ship.get("AddressLine2"), ship.get("AddressLine1")
        place = " · ".join(x for x in (site, site_name) if x) or None
        need = ln.get("ReqDeliveryDate") or o.get("ReqDeliveryDate")

        def d(field, value, sf, sv, transform="Pass-through"):
            return Fact("demand", key, field, value, sf, sv, transform)

        facts = [
            d("demand_id", key, "OrderNo", key),
            d("line", int(ln["PrimeLineNo"]), "PrimeLineNo", ln["PrimeLineNo"], "Integer"),
            d(
                "kind",
                ORDER_KINDS.get(o.get("OrderType"), (o.get("OrderType") or "").lower() or None),
                "OrderType",
                o.get("OrderType"),
                "Order type map",
            ),
            d("order_status", ln.get("Status"), "OrderLine.Status", ln.get("MinLineStatus"), "Status code → description"),
            d(
                "buyer",
                tenant(o.get("BuyerOrganizationCode")),
                "BuyerOrganizationCode",
                o.get("BuyerOrganizationCode"),
                "Tenant key",
            ),
            d("item", item.get("ItemID"), "Item.ItemID", item.get("ItemID")),
            d("item_desc", item.get("ItemShortDesc"), "Item.ItemShortDesc", item.get("ItemShortDesc")),
            d("qty", number(ln.get("OrderedQty")), "OrderedQty", ln.get("OrderedQty"), "Integer"),
            d(
                "accepts_refurbished",
                lext.get("ExtnAcceptsRefurbished") == "Y",
                "Extn.ExtnAcceptsRefurbished",
                lext.get("ExtnAcceptsRefurbished"),
                "Boolean (Y/N)",
            ),
        ]
        if extn.get("ExtnDemandStatus"):
            s = extn["ExtnDemandStatus"]
            facts.append(
                d(
                    "status",
                    STATUS_MAP.get(s, s.lower()),
                    "Extn.ExtnDemandStatus",
                    s,
                    f"Status map: {s} → {STATUS_MAP.get(s, s.lower())}",
                )
            )
        if need:
            facts.append(d("need_by", need[:10], "ReqDeliveryDate", need, "Date to ISO"))
        if ship_key:
            facts += [
                d("ship_to", place or ship_key, "ShipToKey", ship_key, "Location lookup"),
                d("location", place or ship_key, "ShipToKey", ship_key, "Location lookup"),
                d("ship_to_key", ship_key, "ShipToKey", ship_key),
            ]
            if site:
                facts.append(d("ship_to_site", site, "PersonInfoShipTo.AddressLine2", site))
        price = (ln.get("LinePriceInfo") or {}).get("UnitPrice")
        if price is not None:
            cur = (o.get("PriceInfo") or {}).get("Currency", "USD")
            facts.append(d("unit_price", float(Decimal(price)), "LinePriceInfo.UnitPrice", f"{price} {cur}", "Currency (USD)"))
        if lext.get("ExtnMinCertifiedMonths"):
            m = lext["ExtnMinCertifiedMonths"]
            facts.append(d("min_certified_months", int(m), "Extn.ExtnMinCertifiedMonths", m, "Integer months"))
        if lext.get("ExtnAvoidedPurchaseOrder"):
            po = lext["ExtnAvoidedPurchaseOrder"]
            facts.append(d("purchase_ref", po, "Extn.ExtnAvoidedPurchaseOrder", po))

        res = ((ln.get("OrderLineReservations") or {}).get("OrderLineReservation") or [None])[0]
        if res and res.get("SerialNo"):
            serial = res["SerialNo"]
            facts += [
                d("allocated_asset", serial, "OrderLineReservation.SerialNo", serial),
                d("reservation_ref", res.get("ReservationID"), "OrderLineReservation.ReservationID", res.get("ReservationID")),
                d("ship_node", res.get("Node"), "OrderLineReservation.Node", res.get("Node")),
                Fact("asset", serial, "allocated_to", key, "OrderLineReservation.SerialNo", serial, "Reservation → order"),
            ]
        shp = ln.get("Shipment")
        if shp:
            facts += [
                d("shipment_ref", shp.get("ShipmentNo"), "Shipment.ShipmentNo", shp.get("ShipmentNo")),
                d("carrier", shp.get("SCAC") or None, "Shipment.SCAC", shp.get("SCAC")),
                d("shipped_at", utc(shp.get("ShipDate")), "Shipment.ShipDate", shp.get("ShipDate"), "Timestamp to UTC"),
            ]
        pod = ln.get("ProofOfDelivery")
        if pod:
            facts += [
                d(
                    "delivered_at",
                    utc(pod.get("DeliveryDate")),
                    "ProofOfDelivery.DeliveryDate",
                    pod.get("DeliveryDate"),
                    "Timestamp to UTC",
                ),
                d("pod_ref", pod.get("PODReference") or None, "ProofOfDelivery.PODReference", pod.get("PODReference")),
                d("pod_received_by", pod.get("ReceivedBy"), "ProofOfDelivery.ReceivedBy", pod.get("ReceivedBy")),
            ]
        return facts

    def _return(self, o: dict) -> list[Fact]:
        facts: list[Fact] = []
        extn = o.get("Extn") or {}
        for ln in (o.get("OrderLines") or {}).get("OrderLine") or []:
            serial = ln.get("SerialNo")
            if not serial:
                continue
            lext, item = ln.get("Extn") or {}, ln.get("Item") or {}

            def a(field, value, sf, sv, transform="Pass-through", serial=serial):
                return Fact("asset", serial, field, value, sf, sv, transform)

            facts += [
                a("return_ref", o["OrderNo"], "OrderNo", o["OrderNo"]),
                a("return_status", ln.get("Status"), "OrderLine.Status", ln.get("MinLineStatus"), "Status code → description"),
                a("return_reason", ln.get("ReturnReason"), "ReturnReason", ln.get("ReturnReason")),
                a(
                    "return_reason_text",
                    lext.get("ExtnReturnReasonText"),
                    "Extn.ExtnReturnReasonText",
                    lext.get("ExtnReturnReasonText"),
                ),
                a("customer_intent", extn.get("ExtnCustomerIntent"), "Extn.ExtnCustomerIntent", extn.get("ExtnCustomerIntent")),
                a("receiving_node", o.get("ReceivingNode"), "ReceivingNode", o.get("ReceivingNode")),
                a("item", item.get("ItemID"), "Item.ItemID", item.get("ItemID")),
            ]
            if lext.get("ExtnReceivedDate"):
                v = lext["ExtnReceivedDate"]
                facts.append(a("return_received_at", utc(v), "Extn.ExtnReceivedDate", v, "Timestamp to UTC"))
            if extn.get("ExtnReceiptNo"):
                facts.append(a("receipt_ref", extn["ExtnReceiptNo"], "Extn.ExtnReceiptNo", extn["ExtnReceiptNo"]))
            if extn.get("ExtnLeaseNo"):
                facts.append(a("relase_ref", extn["ExtnLeaseNo"], "Extn.ExtnLeaseNo", extn["ExtnLeaseNo"]))
        return facts


ADAPTER = SterlingAdapter()
