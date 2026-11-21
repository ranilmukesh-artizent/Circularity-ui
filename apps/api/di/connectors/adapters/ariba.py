"""SAP Ariba (proc): purchase alternatives, supplier quotes, lead times (the demo's SOURCES.proc). Read only.

apiKey header + OAuth client-credentials bearer, realm on every call, page tokens. The event list has no delta
filter, so events are read in full (46 events; the bids of each event are a second call).

Facts
    demand.PO-<externalReference>   purchase_alternative (USD from the best EUR quote at 0.92), purchase_alternative_eur,
                                    supplier_lead_time (days), supplier_ref, rfq_ref
The demo's mapping: QuotedUnitPrice €10,400.00 → demand.purchase_alternative $11,300 ("Currency at dated rate");
SupplierLeadTime 21 days; SupplierId SUP-88120.
"""

from decimal import ROUND_HALF_UP, Decimal

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import ApiKey, Combined, OAuthClientCredentials

API = "/ariba/api"
REALM = {"realm": "northfield-T"}
EUR_PER_USD = Decimal("0.92")


def usd_from_eur(eur: Decimal) -> float:
    """To whole hundreds, as the demo shows quoted alternatives ($11,300)."""
    return float((eur / EUR_PER_USD / 100).quantize(Decimal("1"), ROUND_HALF_UP) * 100)


class AribaAdapter(Adapter):
    source_id = "proc"

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        """The application key identifies the client (kept here); the stored secret is the OAuth client secret."""
        return Combined(
            [
                ApiKey("apiKey", "circularity-demo-ariba-key"),
                OAuthClientCredentials("/ariba/v2/oauth/token", "di-connector", secret or "circularity-demo-ariba-secret"),
            ]
        )

    def resources(self):
        return [Resource("event", self.read_events, delta=False)]

    def read_events(self, client, since):  # noqa: ARG002 - the adapter read interface; this read is always full
        token = None
        while True:
            params = REALM | ({"pageToken": token} if token else {})
            r = client.request("GET", f"{API}/sourcing-event/v2/prod/events", params=params)
            body = r.json()
            client.note_records(len(body["payload"]))
            for ev in body["payload"]:
                bids = client.get_json(f"{API}/sourcing-event/v2/prod/events/{ev['eventId']}/bids", params=REALM)["payload"]
                yield Record("event", ev["eventId"], ev | {"bids": bids}, str(r.request.url), ev.get("lastModified"))
            token = body.get("pageToken")
            if not token:
                return

    def map(self, record: Record) -> list[Fact]:
        ev = record.payload
        bids = sorted(ev.get("bids") or [], key=lambda b: b["unitPrice"]["amount"])
        if not ev.get("externalReference") or not bids:
            return []
        best = bids[0]
        eur = Decimal(str(best["unitPrice"]["amount"]))
        key = f"PO-{ev['externalReference']}"
        return [
            Fact(
                "demand",
                key,
                "purchase_alternative",
                usd_from_eur(eur),
                "QuotedUnitPrice",
                f"€{eur:,.2f}",
                "Currency at dated rate (0.92 EUR/USD)",
            ),
            Fact("demand", key, "purchase_alternative_eur", float(eur), "QuotedUnitPrice", float(eur), "Pass-through"),
            Fact(
                "demand",
                key,
                "supplier_lead_time",
                best["leadTimeDays"],
                "SupplierLeadTime",
                f"{best['leadTimeDays']} days",
                "Integer days",
            ),
            Fact("demand", key, "supplier_ref", best["supplierId"], "SupplierId", best["supplierId"], "Pass-through"),
            Fact("demand", key, "rfq_ref", ev["eventId"], "eventId", ev["eventId"], "Pass-through"),
        ]


ADAPTER = AribaAdapter()
