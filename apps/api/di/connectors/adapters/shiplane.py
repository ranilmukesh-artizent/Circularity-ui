"""ShipLane TMS (tms): lane rate cards, carrier bookings, loads, ETD and ETA, proof of delivery (SOURCES.tms).

OAuth 2.0 client credentials; cursor paging (?limit=&cursor=, body {Items, NextCursor, TotalCount}); ?updated_since=
for delta reads. Carrier names (NLTL → Northline 3PL) come from GET /carriers, read at the start of each lane or load
read as a lookup.

Facts (tms has authority over lane_rate, carrier, eta)
    route.<LaneId>      leg ("WH-MAA-02 → LOC-CHN-03"), origin, destination, origin_facility, destination_facility,
                        distance_km, transit_hours, lane_rate (USD), lane_rate_inr, rate_basis, carrier, rate_card, mode
    route.<RateCardId>  rate card terms: carrier, currency, valid_from/to, per_km_rate, loading_charge, minimum_charge
    route.<LoadId>      leg, lane_id, direction, asset_id, carrier, status, etd, eta (site time kept), delivered_at,
                        pod_ref, freight (USD)
    asset.<ItemId>      inbound_load / outbound_load, and for inbound loads inbound_lane, inbound_carrier,
                        inbound_eta, inbound_pod_ref, inbound_freight (USD)
    vendor.<SCAC>       name, role, contract_ref, status (carriers)
The demo's mapping (MAPPINGS.tms), reproduced on lane WH-MAA-02>LOC-CHN-03: LaneId → leg "Lane decode"; RateAmt
3600.00 INR → $43 "Currency at 83.5 (rate dated 2026-10-06)" (field lane_rate; whole dollars, as Optoro's freight);
CarrierSCAC NLTL → carrier Northline 3PL "Carrier lookup". ETA → route.eta "Site time kept" on loads (the demo's
2026-10-13T08:36 outbound load is not seeded; seeded loads are the inbound returns).
"""

import math
from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.generic import generic_pages, source_clock, utc
from di.connectors.http import OAuthClientCredentials, SourceClient

INR_PER_USD = Decimal("83.5")
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"
CARRIERS = {"NLTL": "Northline 3PL", "VLFR": "Velo Freight", "CSHL": "Coastal Haulage"}  # fallback when /carriers fails
RESOURCES = (
    ("carriers", "/carriers", "CarrierSCAC"),
    ("rate_cards", "/rate-cards", "RateCardId"),
    ("lanes", "/lanes", "LaneId"),
    ("loads", "/loads", "LoadId"),
)


def usd_whole(inr: Decimal) -> float:
    """To whole dollars, half up (3600 INR → $43), as the demo and Optoro show freight."""
    return float(math.floor(inr / INR_PER_USD + Decimal("0.5")))


def site_time(v: str | None) -> str | None:
    """'2026-10-13T08:36:00+05:30' → '2026-10-13T08:36' (the site's local time, offset dropped)."""
    return v[:16] if v else None


class ShipLaneAdapter(Adapter):
    source_id = "tms"
    base_path = "/shiplane/v3"

    def __init__(self):
        self.carriers: dict[str, str] = dict(CARRIERS)

    def auth(self):
        return OAuthClientCredentials("/oauth/token", "di-connector", "tms-demo-secret")

    def resources(self):
        return [Resource(name, self.reader(name, path, id_field)) for name, path, id_field in RESOURCES]

    def _pages(self, client, path, since):
        return generic_pages(
            client, path, since, items_key="Items", next_key="NextCursor", next_param="cursor", size_param="limit"
        )

    def reader(self, name: str, path: str, id_field: str):
        def read(client: SourceClient, since):
            if name in ("lanes", "loads"):
                for c, _ in self._pages(client, "/carriers", None):
                    if c.get("CarrierSCAC") and c.get("Name"):
                        self.carriers[c["CarrierSCAC"]] = c["Name"]
            stamp = source_clock(client)
            for doc, url in self._pages(client, path, since):
                yield Record(name, str(doc[id_field]), doc, url, stamp)

        return read

    def carrier(self, scac: str | None) -> str | None:
        return self.carriers.get(scac, scac) if scac else None

    # ------------------------------------------------------------------ mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        out: list[Fact] = []

        def fact(model, key, field, value, sf, transform, sv=None):
            if value is not None and key:
                out.append(Fact(model, key, field, value, sf, p.get(sf) if sv is None else sv, transform))

        if record.resource == "carriers":
            k = p.get("CarrierSCAC")
            fact("vendor", k, "name", p.get("Name"), "Name", "Pass-through")
            fact("vendor", k, "kind", "carrier", "Mode", "Carrier")
            fact("vendor", k, "role", p.get("Role"), "Role", "Pass-through")
            fact("vendor", k, "contract_ref", p.get("ContractRef"), "ContractRef", "Pass-through")
            fact("vendor", k, "rate_card", p.get("RateCardId"), "RateCardId", "Pass-through")
            fact("vendor", k, "status", p.get("Status"), "Status", "Pass-through")
        elif record.resource == "rate_cards":
            k = p.get("RateCardId")
            ftl = p.get("FullTruckLoad") or {}
            fact("route", k, "kind", "rate_card", "RateCardId", "Rate card")
            fact("route", k, "carrier", self.carrier(p.get("CarrierSCAC")), "CarrierSCAC", "Carrier lookup")
            fact("route", k, "contract_ref", p.get("ContractRef"), "ContractRef", "Pass-through")
            fact("route", k, "currency", p.get("Currency"), "Currency", "Pass-through")
            fact("route", k, "valid_from", p.get("ValidFrom"), "ValidFrom", "Date")
            fact("route", k, "valid_to", p.get("ValidTo"), "ValidTo", "Date")
            fact("route", k, "status", p.get("Status"), "Status", "Pass-through")
            for src, field in (
                ("PerKmRate", "per_km_rate_inr"),
                ("LoadingCharge", "loading_charge_inr"),
                ("MinimumCharge", "minimum_charge_inr"),
            ):
                fact("route", k, field, ftl.get(src), f"FullTruckLoad.{src}", "Pass-through (INR)", ftl.get(src))
        elif record.resource == "lanes":
            k = p.get("LaneId")
            a, b = p.get("OriginLocationCode"), p.get("DestinationLocationCode")
            fact("route", k, "leg", f"{a} → {b}", "LaneId", "Lane decode")
            fact("route", k, "origin", a, "OriginLocationCode", "Pass-through")
            fact("route", k, "destination", b, "DestinationLocationCode", "Pass-through")
            fact("route", k, "origin_facility", p.get("OriginFacilityId"), "OriginFacilityId", "Pass-through")
            fact("route", k, "destination_facility", p.get("DestinationFacilityId"), "DestinationFacilityId", "Pass-through")
            fact("route", k, "distance_km", p.get("DistanceKm"), "DistanceKm", "Kilometres")
            fact("route", k, "transit_hours", p.get("TransitHours"), "TransitHours", "Hours")
            self._rate(fact, "route", k, "lane_rate", p)
            fact("route", k, "rate_basis", p.get("RateBasis"), "RateBasis", "Pass-through")
            fact("route", k, "carrier", self.carrier(p.get("CarrierSCAC")), "CarrierSCAC", "Carrier lookup")
            fact("route", k, "rate_card", p.get("RateCardId"), "RateCardId", "Pass-through")
            fact("route", k, "mode", p.get("Mode"), "Mode", "Pass-through")
        elif record.resource == "loads":
            k = p.get("LoadId")
            a, b = p.get("OriginLocationCode"), p.get("DestinationLocationCode")
            if a and b:
                fact("route", k, "leg", f"{a} → {b}", "LaneId", "Lane decode")
            fact("route", k, "lane_id", p.get("LaneId"), "LaneId", "Pass-through")
            fact("route", k, "kind", "load", "LoadId", "Load")
            fact("route", k, "direction", p.get("Direction"), "Direction", "Pass-through")
            fact("route", k, "asset_id", p.get("ItemId"), "ItemId", "Pass-through")
            fact("route", k, "case_ref", p.get("ReturnReference"), "ReturnReference", "Pass-through")
            fact(
                "route", k, "carrier", p.get("CarrierName") or self.carrier(p.get("CarrierSCAC")), "CarrierSCAC", "Carrier lookup"
            )
            fact("route", k, "status", p.get("Status"), "Status", "Pass-through")
            fact("route", k, "etd", site_time(p.get("ETD")), "ETD", "Site time kept")
            fact("route", k, "eta", site_time(p.get("ETA")), "ETA", "Site time kept")
            fact("route", k, "delivered_at", utc(p.get("ActualDeliveryAt")), "ActualDeliveryAt", "Timestamp to UTC")
            pod = p.get("ProofOfDelivery") or {}
            fact("route", k, "pod_ref", pod.get("PodRef"), "ProofOfDelivery.PodRef", "Pass-through", pod.get("PodRef"))
            self._rate(fact, "route", k, "freight", p)
            item = p.get("ItemId")
            inbound = (p.get("Direction") or "").upper() == "INBOUND"
            fact("asset", item, "inbound_load" if inbound else "outbound_load", k, "LoadId", "Pass-through")
            if inbound:
                fact("asset", item, "inbound_lane", p.get("LaneId"), "LaneId", "Pass-through")
                fact(
                    "asset",
                    item,
                    "inbound_carrier",
                    p.get("CarrierName") or self.carrier(p.get("CarrierSCAC")),
                    "CarrierSCAC",
                    "Carrier lookup",
                )
                fact("asset", item, "inbound_eta", site_time(p.get("ETA")), "ETA", "Site time kept")
                fact(
                    "asset",
                    item,
                    "inbound_pod_ref",
                    pod.get("PodRef"),
                    "ProofOfDelivery.PodRef",
                    "Pass-through",
                    pod.get("PodRef"),
                )
                self._rate(fact, "asset", item, "inbound_freight", p)
        return out

    @staticmethod
    def _rate(fact, model: str, key: str, field: str, p: dict) -> None:
        amt, cur = p.get("RateAmt"), (p.get("RateCurrency") or "INR").upper()
        if amt is None:
            return
        amount = Decimal(str(amt))
        if cur == "USD":
            fact(model, key, field, float(amount), "RateAmt", "Pass-through (USD)", f"{amount:.2f} USD")
        elif cur == "INR":
            fact(model, key, field, usd_whole(amount), "RateAmt", RATE_NOTE, f"{amount:.2f} INR")
            if field == "lane_rate":
                fact(model, key, "lane_rate_inr", float(amount), "RateAmt", "Pass-through (INR)", f"{amount:.2f} INR")


ADAPTER = ShipLaneAdapter()
