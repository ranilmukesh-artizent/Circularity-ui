"""Optoro (rl): return authorisations (RMAs), receipts, dispositions, inbound shipments (ASNs) (the demo's SOURCES.rl),
against Optoro's API (source-sim's sim/vendors/optoro).

Auth: OAuth 2.0 client credentials at the auth host (/auth/oauth/token), bearer token. Lists use Optoro's list
conventions: ?per_page=&offset=<cursor> following next_page.offset to the end, ?updated_at=<cursor> for deltas
(records changed after it); the cursor is the newest updated_at read.

Facts (rl has authority over return_ref, received_at, disposition)
    asset.<sku>   return_ref, return_authorization_ref (rma_identifier), return_authorized_at (created_at),
                  case_ref (secondary_identifier), replacement_order (exchange_order_identifier),
                  return_receipt_status (receiving_status), return_reason_code (return_reason)          (RMAs)
                  received_at, return_id (OptiTurn LP), receiving_facility, origin_site, case_ref       (receipts)
                  disposition (rts → restock, refurbish → refurbish, recycle → recycle, client_liquidation /
                  b2b / d2c / outlets → liquidate ...), disposition_status, disposition_final  (disposition updates
                  are proposals; a final disposition makes them final)
                  inbound_shipment_ref (asn_number), inbound_load (shipment_identifier), inbound_carrier,
                  inbound_tracking, inbound_delivered_at, inbound_freight (USD), carrier_status          (ASNs)
The demo's mapping (MAPPINGS.rl): RMA_ID → asset.return_ref "Pass-through" (Optoro's field: rma_identifier);
DISPOSITION REFURB → refurbish "Disposition map" (Optoro's field: to_disposition, channel refurbish);
RECEIVED_AT -04:00 → UTC "Timestamp to UTC" (the receipt's received_at). The seed gives RT-1048 RMA-56509,
received 2026-10-03T15:28:00-04:00 and rts (restock).
"""

from collections.abc import Iterator
from datetime import UTC, datetime

from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import utc
from di.connectors.http import OAuthClientCredentials, SourceClient
from di.services.canonical.store import Fact

PER_PAGE = 100
DISPOSITION: dict[str | None, str] = {
    "rts": "restock",
    "rts_drop_ship": "restock",
    "refurbish": "refurbish",
    "recycle": "recycle",
    "client_liquidation": "liquidate",
    "b2b": "liquidate",
    "d2c": "liquidate",
    "outlets": "liquidate",
    "rtv": "return_to_vendor",
    "donate": "donate",
    "destroy": "dispose",
    "dispose": "dispose",
    "needs_testing": "pending_inspection",
}
RESOURCES = (  # name, path, list key, id field
    ("rmas", "/returns/rmas", "rmas", "rma_identifier"),
    ("receipts", "/inventory/inventory_receipts", "inventory_receipts", "unit_identifier"),
    ("dispositions", "/returns/dispositions", "dispositions", "id"),
    ("final_dispositions", "/returns/final_dispositions", "final_dispositions", "id"),
    ("asns", "/asn/asns", "asns", "asn_number"),
)


def cursor(v: str | None) -> str | None:
    """Optoro's 2026-10-03T19:28:00.000Z → ISO with +00:00 (the cursor form)."""
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(UTC).isoformat() if v else None


class OptoroAdapter(Adapter):
    source_id = "rl"
    base_path = "/optoro"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials("/auth/oauth/token", "di-connector", secret or "rl-demo-secret", form=True)

    def resources(self):
        return [Resource(name, self.reader(path, key, id_field), True) for name, path, key, id_field in RESOURCES]

    def pages(self, client: SourceClient, path: str, key: str, since: str | None) -> Iterator[tuple[dict, str]]:
        params: dict = {"per_page": PER_PAGE}
        if since:
            params["updated_at"] = since
        while True:
            r = client.request("GET", path, params=params)
            body = r.json()
            rows = body.get(key) or []
            client.note_records(len(rows))
            for row in rows:
                yield row, str(r.request.url)
            nxt = body.get("next_page")
            if not nxt or not rows:
                return
            params = params | {"offset": nxt["offset"]}

    def reader(self, path: str, key: str, id_field: str):
        name = next(n for n, p, _, _ in RESOURCES if p == path)

        def read(client: SourceClient, since: str | None):
            for doc, url in self.pages(client, path, key, since):
                yield Record(name, str(doc[id_field]), doc, url, cursor(doc.get("updated_at")))

        return read

    # ------------------------------------------------------------- mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        out: list[Fact] = []

        def fact(key, field, value, sf, sv, transform="Pass-through"):
            if key and value is not None:
                out.append(Fact("asset", key, field, value, sf, sv, transform))

        r = record.resource
        if r == "rmas":
            rid = p.get("rma_identifier")
            for it in p.get("items") or []:
                k = it.get("sku")
                fact(k, "return_ref", rid, "rma_identifier", rid)
                fact(k, "return_authorization_ref", rid, "rma_identifier", rid)
                fact(k, "return_authorized_at", utc(p.get("created_at")), "created_at", p.get("created_at"), "Timestamp to UTC")
                fact(k, "case_ref", it.get("secondary_identifier"), "items.secondary_identifier", it.get("secondary_identifier"))
                ex = it.get("exchange_order_identifier")
                fact(k, "replacement_order", ex, "items.exchange_order_identifier", ex)
                fact(k, "return_receipt_status", it.get("receiving_status"), "items.receiving_status", it.get("receiving_status"))
                fact(k, "return_reason_code", it.get("return_reason"), "items.return_reason", it.get("return_reason"))
        elif r == "receipts":
            k = p.get("sku")
            fact(k, "received_at", utc(p.get("received_at")), "received_at", p.get("received_at"), "Timestamp to UTC")
            fact(k, "return_id", p.get("unit_identifier"), "unit_identifier", p.get("unit_identifier"))
            to = p.get("to") or {}
            fac = to.get("original_identifier") or (str(to["identifier"]) if to.get("identifier") is not None else None)
            fact(k, "receiving_facility", fac, "to.original_identifier", fac)
            site = (p.get("from") or {}).get("name")
            fact(k, "origin_site", site, "from.name", site)
            ref = (p.get("reference") or {}).get("alternate_identifier")
            fact(k, "case_ref", ref, "reference.alternate_identifier", ref)
        elif r == "dispositions":
            k = p.get("to_sku") or p.get("sku")
            d = p.get("to_disposition")
            fact(k, "disposition", DISPOSITION.get(d, d), "to_disposition", d, "Disposition map")
            status = "ON_HOLD" if d == "needs_testing" else "PROPOSED"
            fact(k, "disposition_status", status, "to_disposition", d, "Disposition update → proposal")
            fact(k, "disposition_final", False, "to_disposition", d, "Disposition update → not final")
        elif r == "final_dispositions":
            k = p.get("sku")
            d = p.get("disposition")
            fact(k, "disposition", DISPOSITION.get(d, d), "disposition", d, "Disposition map")
            fact(k, "disposition_status", "FINAL", "disposition", d, "Final disposition")
            fact(k, "disposition_final", True, "disposition", d, "Final disposition")
        elif r == "asns":
            for carton in p.get("cartons") or []:
                for det in carton.get("details") or []:
                    k = det.get("sku")
                    fact(k, "inbound_shipment_ref", p.get("asn_number"), "asn_number", p.get("asn_number"))
                    fact(k, "inbound_load", p.get("shipment_identifier"), "shipment_identifier", p.get("shipment_identifier"))
                    fact(k, "inbound_carrier", p.get("carrier"), "carrier", p.get("carrier"))
                    fact(k, "inbound_tracking", p.get("tracking_number"), "tracking_number", p.get("tracking_number"))
                    fact(
                        k,
                        "inbound_delivered_at",
                        utc(p.get("delivered_at")),
                        "delivered_at",
                        p.get("delivered_at"),
                        "Timestamp to UTC",
                    )
                    fr = p.get("freight") or {}
                    if fr.get("amount_cents") is not None and fr.get("currency", "USD") == "USD":
                        usd = fr["amount_cents"] / 100
                        sv = f"{usd:.2f} USD"
                        if fr.get("local_amount_cents") is not None:
                            sv += f" ({fr['local_amount_cents'] / 100:.2f} {fr.get('local_currency') or ''})".replace(" )", ")")
                        fact(k, "inbound_freight", usd, "freight.amount_cents", sv, "Pass-through (USD)")
                    st = p.get("status")
                    fact(k, "carrier_status", st.upper() if st else None, "status", st, "Status (upper case)")
        return out


ADAPTER = OptoroAdapter()
