"""Oracle Transportation Management (tms): lanes and rate records, carriers, shipments with ETD / ETA, tracking events
and proof of delivery (the demo's SOURCES.tms; OTM replaces the demo's fictional ShipLane TMS, VENDOR_OVERRIDES).

REST under /otm/logisticsRestApi/resources/v2 with an OAuth 2.0 client-credentials bearer (POST /otm/oauth2/v1/token).
Collections page with limit / offset until hasMore is false; delta reads filter q=updateDate gt "<cursor>", where the
cursor is the newest updateDate seen (OTM returns it on every object, so Record.changed is the source's own stamp).
Lookups read at the start of a lane, carrier or shipment read (not records): carrier locations (names), service
provider aliases (SCAC), xLanes (ends, distance, transit), locations (Manhattan facility ids in attribute2) and the
rate offering (carrier of a rate record). Conventions of the mock's deployment (refnum qualifiers, flexfields): see
apps/source-sim/sim/vendors/otm/__init__.py.

Facts (tms has authority over lane_rate, carrier, eta) — the same as the ShipLane adapter wrote:
    route.<lane, e.g. WH-MAA-02>LOC-CHN-03>   (rateGeos) leg, origin, destination, origin_facility,
                        destination_facility, distance_km, transit_hours, lane_rate (USD), lane_rate_inr, rate_basis,
                        carrier, rate_card, mode
    route.<RC-2026.2>   (rateOfferings) kind, carrier, contract_ref, currency, valid_from/to, status,
                        per_km_rate_inr, loading_charge_inr, minimum_charge_inr
    route.<LD-21048>    (shipments) leg, lane_id, kind load, direction, asset_id, case_ref, carrier, status
                        (BOOKED | IN_TRANSIT | DELIVERED), etd, eta (site time kept), delivered_at, pod_ref, freight (USD)
    asset.<ITEM_ID>     inbound_load / outbound_load; inbound loads also inbound_lane, inbound_carrier, inbound_eta,
                        inbound_pod_ref, inbound_freight (USD)
    vendor.<SCAC>       (serviceProviders) name, kind carrier, role, contract_ref, rate_card, status
The demo's mapping (MAPPINGS.tms), on lane WH-MAA-02>LOC-CHN-03: lane → route.leg "WH-MAA-02 → LOC-CHN-03" (Lane
decode); the rate 3600.00 INR (rate record minCost over its per-km and loading charges) → $43 "Currency at 83.5 (rate
dated 2026-10-06)"; carrier NLTL → Northline 3PL (Carrier lookup); a shipment's endTime → route.eta (Site time kept).
Changed by the real API: the source fields are OTM's (xLaneGid, minCost, servprovGid, endTime, totalActualCost,
trackingEvents ...) instead of ShipLane's (LaneId, RateAmt, CarrierSCAC, ETA); values are unchanged.
"""

import math
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, overload

import httpx

from di.canonical.store import Fact
from di.connectors.base import Adapter, Record, Resource
from di.connectors.http import OAuthClientCredentials, SourceClient

API = "/logisticsRestApi/resources/v2"
PAGE = 500
INR_PER_USD = Decimal("83.5")
RATE_NOTE = "Currency at 83.5 (rate dated 2026-10-06)"
ENROUTE = {"ENROUTE_NOT STARTED": "BOOKED", "ENROUTE_STARTED": "IN_TRANSIT", "ENROUTE_COMPLETED": "DELIVERED"}


def usd_whole(inr: Decimal) -> float:
    """To whole dollars, half up (3600 INR → $43), as the demo and Optoro show freight."""
    return float(math.floor(inr / INR_PER_USD + Decimal("0.5")))


@overload
def xid(gid: str) -> str: ...
@overload
def xid(gid: None) -> None: ...
def xid(gid: str | None) -> str | None:
    return gid.split(".", 1)[1] if gid and "." in gid else gid


def val(v):
    return v.get("value") if isinstance(v, dict) else v


def site_time(v: dict | None) -> str | None:
    """dateTimeType {"value": "2026-10-13T08:36:00+05:30"} → '2026-10-13T08:36' (the site's local time)."""
    s = val(v)
    return s[:16] if s else None


def utc(v: dict | str | None) -> str | None:
    s = val(v)
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def items(v) -> list[dict]:
    return (v or {}).get("items", []) if isinstance(v, dict) else (v or [])


class OtmAdapter(Adapter):
    source_id = "tms"
    base_path = "/otm"

    def __init__(self):
        self.names: dict[str, str] = {}  # carrier gid → name
        self.scac: dict[str, str | None] = {}  # carrier gid → SCAC
        self.lanes: dict[str, dict] = {}  # xLaneGid → lane
        self.locations: dict[str, dict] = {}  # locationGid → location
        self.offerings: dict[str, dict] = {}  # rateOfferingGid → rate offering

    def auth(self, conn=None, secret=None):  # noqa: ARG002 - conn: the Adapter interface
        return OAuthClientCredentials("/oauth2/v1/token", "di-connector", secret or "tms-demo-secret")

    def resources(self):
        return [
            Resource("serviceProviders", self.reader("serviceProviders", "servprovGid", "servprovAliases")),
            Resource("rateOfferings", self.reader("rateOfferings", "rateOfferingGid")),
            Resource("rateGeos", self.reader("rateGeos", "rateGeoGid", "costs")),
            Resource("shipments", self.reader("shipments", "shipmentGid", "refnums,statuses,trackingEvents")),
        ]

    # ------------------------------------------------------------------ reading
    def pages(self, client: SourceClient, resource: str, since: str | None = None, **params) -> Iterator[tuple[dict, str]]:
        offset = 0
        while True:
            q = {**params, "limit": str(PAGE), "offset": str(offset)}
            if since:
                q["q"] = f'updateDate gt "{since}"'
            body = client.get_json(f"{API}/{resource}", params=q)
            rows = body.get("items") or []
            client.note_records(len(rows))
            url = str(httpx.URL(client.url(f"{API}/{resource}"), params=q))
            for row in rows:
                yield row, url
            if not body.get("hasMore") or not rows:
                return
            offset += len(rows)

    def lookups(self, client: SourceClient) -> None:
        for loc, _ in self.pages(client, "locations"):
            self.locations[loc["locationGid"]] = loc
            if loc.get("locationName"):
                self.names[loc["locationGid"]] = loc["locationName"]
        for sp, _ in self.pages(client, "serviceProviders", expand="servprovAliases"):
            alias = next((a["alias"] for a in items(sp.get("servprovAliases")) if a.get("servprovAliasQualGid") == "SCAC"), None)
            self.scac[sp["servprovGid"]] = alias or xid(sp["servprovGid"])
        for lane, _ in self.pages(client, "xLanes"):
            self.lanes[lane["xLaneGid"]] = lane
        for ro, _ in self.pages(client, "rateOfferings"):
            self.offerings[ro["rateOfferingGid"]] = ro

    def reader(self, resource: str, id_field: str, expand: str | None = None):
        def read(client: SourceClient, since):
            self.lookups(client)
            params = {"expand": expand} if expand else {}
            for doc, url in self.pages(client, resource, since, **params):
                yield Record(resource, xid(doc[id_field]), doc, url, val(doc.get("updateDate")))

        return read

    def carrier(self, gid: str | None) -> str | None:
        return self.names.get(gid, xid(gid)) if gid else None

    # ------------------------------------------------------------------ mapping
    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        out: list[Fact] = []

        def fact(model, key, field, value, sf, sv, transform):
            if value is not None and key:
                out.append(Fact(model, key, field, value, sf, sv, transform))

        if record.resource == "serviceProviders":
            g = p["servprovGid"]
            k = self.scac.get(g) or xid(g)
            fact("vendor", k, "name", self.carrier(g), "servprovGid", g, "Carrier lookup")
            fact("vendor", k, "kind", "carrier", "servprovAliases.alias", k, "Carrier")
            fact("vendor", k, "role", p.get("attribute1"), "attribute1", p.get("attribute1"), "Pass-through")
            ro = next((r for r in self.offerings.values() if r.get("servprovGid") == g), None)
            if ro:
                fact(
                    "vendor",
                    k,
                    "contract_ref",
                    ro.get("attribute1"),
                    "rateOfferings.attribute1",
                    ro.get("attribute1"),
                    "Pass-through",
                )
                fact(
                    "vendor",
                    k,
                    "rate_card",
                    ro["rateOfferingXid"],
                    "rateOfferings.rateOfferingGid",
                    ro["rateOfferingGid"],
                    "Pass-through",
                )
            fact(
                "vendor",
                k,
                "status",
                "ACTIVE" if p.get("isActive") else "INACTIVE",
                "isActive",
                p.get("isActive"),
                "Flag to status",
            )
        elif record.resource == "rateOfferings":
            k = p["rateOfferingXid"]
            sg: Any = p.get("servprovGid")
            fact("route", k, "kind", "rate_card", "rateOfferingGid", p["rateOfferingGid"], "Rate card")
            fact("route", k, "carrier", self.carrier(sg), "servprovGid", self.scac.get(sg, xid(sg)), "Carrier lookup")
            fact("route", k, "contract_ref", p.get("attribute1"), "attribute1", p.get("attribute1"), "Pass-through")
            fact("route", k, "currency", p.get("currencyGid"), "currencyGid", p.get("currencyGid"), "Pass-through")
            for src, field in (("effectiveDate", "valid_from"), ("expirationDate", "valid_to")):
                fact("route", k, field, (val(p.get(src)) or "")[:10] or None, src, val(p.get(src)), "Date")
            fact(
                "route",
                k,
                "status",
                "ACTIVE" if p.get("isActive") else "INACTIVE",
                "isActive",
                p.get("isActive"),
                "Flag to status",
            )
            for src, field in (
                ("attributeNumber1", "per_km_rate_inr"),
                ("attributeNumber2", "loading_charge_inr"),
                ("attributeNumber3", "minimum_charge_inr"),
            ):
                fact("route", k, field, p.get(src), src, p.get(src), "Pass-through (INR)")
        elif record.resource == "rateGeos":
            self._lane(p, fact)
        elif record.resource == "shipments":
            self._shipment(p, fact)
        return out

    def _lane(self, p: dict, fact) -> None:
        lane_gid: Any = p.get("xLaneGid")
        lane = self.lanes.get(lane_gid) or {}
        k = xid(lane_gid)
        a, b = xid(lane.get("sourceLocationGid")), xid(lane.get("destLocationGid"))
        if not (k and a and b):
            return
        fact("route", k, "leg", f"{a} → {b}", "xLaneGid", k, "Lane decode")
        fact("route", k, "origin", a, "xLanes.sourceLocationGid", lane["sourceLocationGid"], "Pass-through")
        fact("route", k, "destination", b, "xLanes.destLocationGid", lane["destLocationGid"], "Pass-through")
        for end, field in ((lane["sourceLocationGid"], "origin_facility"), (lane["destLocationGid"], "destination_facility")):
            fac = (self.locations.get(end) or {}).get("attribute2")
            fact("route", k, field, fac, "locations.attribute2", fac, "Pass-through")
        km = lane.get("attributeNumber1")
        fact("route", k, "distance_km", int(km) if km is not None else None, "xLanes.attributeNumber1", km, "Kilometres")
        fact(
            "route",
            k,
            "transit_hours",
            lane.get("attributeNumber2"),
            "xLanes.attributeNumber2",
            lane.get("attributeNumber2"),
            "Hours",
        )
        costs = sorted(items(p.get("costs")), key=lambda c: c.get("rateGeoCostSeq") or 0)
        cur = (p.get("minCost") or {}).get("currency") or "INR"
        per_km = sum(
            Decimal(str(val(c["chargeAmount"]))) for c in costs if c.get("chargeMultiplier") == "SHIPMENT.LOADED_DISTANCE"
        )
        flat = sum(Decimal(str(val(c["chargeAmount"]))) for c in costs if c.get("chargeMultiplier") == "SHIPMENT")
        minimum = Decimal(str(val(p.get("minCost")) or 0))
        raw = Decimal(km or 0) * per_km + flat
        inr = max(minimum, raw)
        if cur == "INR" and costs:
            fact("route", k, "lane_rate", usd_whole(inr), "minCost", f"{inr:.2f} INR", RATE_NOTE)
            fact("route", k, "lane_rate_inr", float(inr), "minCost", f"{inr:.2f} INR", "Pass-through (INR)")
            basis = (
                f"{int(km or 0):,} km · minimum charge ₹{int(minimum):,}"
                if raw < minimum
                else f"{int(km or 0):,} km × ₹{per_km:.0f} + ₹{flat:,.0f} loading"
            )
            fact("route", k, "rate_basis", basis, "costs", None, "Rate record charges")
        offering: Any = p.get("rateOfferingGid")
        ro = self.offerings.get(offering) or {}
        partner = p.get("attribute1") == "PARTNER"
        sg: Any = ro.get("servprovGid")
        if not partner:
            fact("route", k, "carrier", self.carrier(sg), "servprovGid", self.scac.get(sg, xid(sg)), "Carrier lookup")
        fact("route", k, "rate_card", xid(p.get("rateOfferingGid")), "rateOfferingGid", p.get("rateOfferingGid"), "Pass-through")
        fact("route", k, "mode", p.get("attribute1"), "attribute1", p.get("attribute1"), "Pass-through")

    def _shipment(self, p: dict, fact) -> None:
        k = p["shipmentXid"]
        refs: dict[str | None, Any] = {
            xid(r.get("shipmentRefnumQualGid")): r.get("shipmentRefnumValue") for r in items(p.get("refnums"))
        }
        a, b = xid(p.get("sourceLocationGid")), xid(p.get("destLocationGid"))
        lane = f"{a}>{b}" if a and b else None
        if lane:
            fact("route", k, "leg", f"{a} → {b}", "sourceLocationGid, destLocationGid", lane, "Lane decode")
        fact("route", k, "lane_id", lane, "sourceLocationGid, destLocationGid", lane, "Pass-through")
        fact("route", k, "kind", "load", "shipmentGid", p["shipmentGid"], "Load")
        inbound = refs.get("MOVE_TYPE") == "RETURN_COLLECTION"
        direction = "INBOUND" if inbound else "OUTBOUND"
        fact("route", k, "direction", direction, "refnums.MOVE_TYPE", refs.get("MOVE_TYPE"), "Move type map")
        item = refs.get("ITEM_ID")
        fact("route", k, "asset_id", item, "refnums.ITEM_ID", item, "Pass-through")
        fact("route", k, "case_ref", refs.get("CASE_REF"), "refnums.CASE_REF", refs.get("CASE_REF"), "Pass-through")
        sg: Any = p.get("servprovGid")
        carrier = self.carrier(sg)
        fact("route", k, "carrier", carrier, "servprovGid", self.scac.get(sg, xid(sg)), "Carrier lookup")
        enroute = next(
            (xid(s["statusValueGid"]) for s in items(p.get("statuses")) if xid(s.get("statusTypeGid")) == "ENROUTE"), None
        )
        fact("route", k, "status", ENROUTE.get(enroute or ""), "statuses.ENROUTE", enroute, "Status map")
        fact("route", k, "etd", site_time(p.get("startTime")), "startTime", val(p.get("startTime")), "Site time kept")
        fact("route", k, "eta", site_time(p.get("endTime")), "endTime", val(p.get("endTime")), "Site time kept")
        d1 = next((e for e in items(p.get("trackingEvents")) if (e.get("statusCodeGid") or "").endswith(".D1")), None)
        if d1:
            fact(
                "route",
                k,
                "delivered_at",
                utc(d1.get("eventdate")),
                "trackingEvents.D1.eventdate",
                val(d1.get("eventdate")),
                "Timestamp to UTC",
            )
            pod = d1.get("externalEventReference")
            fact("route", k, "pod_ref", pod, "trackingEvents.D1.externalEventReference", pod, "Pass-through")
        cost = p.get("totalActualCost") or {}
        freight = None
        if cost.get("value") is not None:
            amt, cur = Decimal(str(cost["value"])), (cost.get("currency") or "INR").upper()
            freight = usd_whole(amt) if cur == "INR" else float(amt) if cur == "USD" else None
            note = RATE_NOTE if cur == "INR" else "Pass-through (USD)"
            fact("route", k, "freight", freight, "totalActualCost", f"{amt:.2f} {cur}", note)
        if not item:
            return
        fact("asset", item, "inbound_load" if inbound else "outbound_load", k, "shipmentXid", k, "Pass-through")
        if inbound:
            fact("asset", item, "inbound_lane", lane, "sourceLocationGid, destLocationGid", lane, "Pass-through")
            fact("asset", item, "inbound_carrier", carrier, "servprovGid", self.scac.get(sg, xid(sg)), "Carrier lookup")
            fact("asset", item, "inbound_eta", site_time(p.get("endTime")), "endTime", val(p.get("endTime")), "Site time kept")
            if d1:
                pod = d1.get("externalEventReference")
                fact("asset", item, "inbound_pod_ref", pod, "trackingEvents.D1.externalEventReference", pod, "Pass-through")
            if freight is not None:
                fact(
                    "asset",
                    item,
                    "inbound_freight",
                    freight,
                    "totalActualCost",
                    f"{Decimal(str(cost['value'])):.2f} {cost.get('currency')}",
                    RATE_NOTE,
                )


ADAPTER = OtmAdapter()
