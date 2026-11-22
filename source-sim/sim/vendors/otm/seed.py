"""Load the seed (B2) into the OTM mock, as OTM holds it at the demo's as-of time.

Same values as the retired generic ShipLane mock, reshaped into OTM objects (domain NORTHFIELD):
- locations: the demo's LOCS (warehouses WH-PNQ-01 / WH-MAA-02, repair centre RC-HSR-01, the eight customer sites
  LOC-*, the buyer hubs EXT-*, the recycler PTN-MAA) plus one location per carrier (in OTM a service provider is a
  location with the CARRIER role; its name is the location name)
- serviceProviders: NLTL Northline 3PL (contracted lane carrier), VLFR Velo Freight and CSHL Coastal Haulage (return
  collections); the SCAC is the service provider alias (qualifier SCAC)
- rateOfferings: RC-2026.2 (Northline 3PL, contract NL-MSA-2025-11, INR, 2026-07-01..2027-06-30)
- xLanes and rateGeos: one per lane the demo moves on: every customer site to every facility (inbound returns) and
  every facility to every other location (outbound). The rate record carries the dedicated LCV charges of RATE_CARD:
  INR 20 per loaded km + INR 1,200 loading, minimum INR 3,600 (WH-MAA-02 > LOC-CHN-03: 34 km, INR 3,600 = $43)
- shipments: one delivered inbound return collection per returned case (LD-2xxxx, e.g. LD-21048 for RT-1048:
  LOC-CHN-03 → WH-PNQ-01, delivered 2026-10-03 10:00 IST, POD-21048), with stops, refnums, statuses and its three
  tracking events (AF departed pickup, X1 arrived, D1 delivered with proof of delivery)
"""

from datetime import datetime, timedelta

from sqlalchemy import insert, text
from sqlalchemy.engine import Connection

from sim.seed import Seed
from sim.vendors.otm import models as t
from sim.vendors.otm.demo import (
    CARRIERS,
    FAC_LOC,
    LANE_KM,
    LOCS,
    RATE_CARD,
    SCAC,
    at_ist,
    case_no,
    ex_kg,
    lane_cost,
    lane_km,
    loc_facility,
    return_logistics,
    transit_h,
)

DOMAIN = "NORTHFIELD"
TZ = "Asia/Calcutta"  # Olson name OTM uses for IST
ROLES = {"NLTL": "Contracted lane carrier", "VLFR": "Return collections", "CSHL": "Return collections"}
RATE_OFFERING = RATE_CARD["id"]


def gid(xid: str) -> str:
    return f"{DOMAIN}.{xid}"


def xid_of(g: str | None) -> str | None:
    return g.split(".", 1)[1] if g and "." in g else g


def dtt(d: datetime | None) -> dict | None:
    """dateTimeType: {"value": ISO 8601 with the location's offset, "timezone": Olson name}."""
    from sim.vendors.otm.demo import IST

    return None if d is None else {"value": d.astimezone(IST).isoformat(timespec="seconds"), "timezone": TZ}


def money(v: float, cur: str = "INR") -> dict:
    return {"value": float(v), "currency": cur}


def amount(v: float, unit: str) -> dict:
    return {"value": float(v), "unit": unit}


def lane_xid(a: str, b: str) -> str:
    return f"{a}>{b}"


def rate_geo_xid(a: str, b: str) -> str:
    return f"{RATE_OFFERING}_{a}>{b}"


def status(type_: str, value: str) -> dict:
    return {"statusTypeGid": gid(type_), "statusValueGid": gid(value), "domainName": DOMAIN}


def refnum(prefix: str, qual: str, value) -> dict:
    return {f"{prefix}RefnumQualGid": gid(qual), f"{prefix}RefnumValue": str(value), "domainName": DOMAIN}


# ------------------------------------------------------------------ reference data
def _locations() -> list[dict]:
    out = []
    for code, loc in LOCS.items():
        role = {"Warehouse": "DC", "Repair centre": "REPAIR", "Customer site": "CUSTOMER", "Buyer hub": "CUSTOMER"}.get(
            loc["kind"], "VENDOR"
        )
        out.append(
            {
                "locationGid": gid(code),
                "locationXid": code,
                "locationName": loc.get("name"),
                "city": loc["city"],
                "countryCode3Gid": "IND",
                "lat": loc["lat"],
                "lon": loc["lon"],
                "timeZoneGid": TZ,
                "isTemporary": False,
                "isActive": True,
                "attribute1": loc["kind"],
                "attribute2": loc_facility(code),  # the Manhattan facility id (WH01, ST03), when it has one
                "attribute3": loc.get("site"),
                "roles": [{"locationRoleGid": role, "domainName": DOMAIN}],
                "domainName": DOMAIN,
            }
        )
    for scac, name in CARRIERS.items():
        out.append(
            {
                "locationGid": gid(scac),
                "locationXid": scac,
                "locationName": name,
                "city": None,
                "countryCode3Gid": "IND",
                "timeZoneGid": TZ,
                "isTemporary": False,
                "isActive": True,
                "roles": [{"locationRoleGid": "CARRIER", "domainName": DOMAIN}],
                "domainName": DOMAIN,
            }
        )
    return out


def _service_providers() -> list[dict]:
    return [
        {
            "servprovGid": gid(scac),
            "servprovXid": scac,
            "isActive": True,
            "isDispatchByRegion": False,
            "allowTender": True,
            "attribute1": ROLES[scac],
            "servprovAliases": [{"servprovAliasQualGid": "SCAC", "alias": scac, "domainName": DOMAIN}],
            "domainName": DOMAIN,
        }
        for scac in CARRIERS
    ]


def _rate_offering() -> dict:
    R = RATE_CARD
    return {
        "rateOfferingGid": gid(R["id"]),
        "rateOfferingXid": R["id"],
        "rateOfferingDesc": "Domestic road · returns and redeployment",
        "rateOfferingTypeGid": "TL",
        "servprovGid": gid("NLTL"),
        "transportModeGid": "TL",
        "currencyGid": "INR",
        "rateServiceGid": "LOOKUP",
        "rateDistanceGid": "LOOKUP ONLY",
        "effectiveDate": {"value": "2026-07-01T00:00:00+05:30", "timezone": TZ},
        "expirationDate": {"value": "2027-06-30T23:59:59+05:30", "timezone": TZ},
        "isActive": True,
        "attribute1": R["contract"],  # ASSUMPTION: the carrier contract number in a flexfield
        "attribute2": R["vehicle"],
        "attributeNumber1": R["perKm"],
        "attributeNumber2": R["load"],
        "attributeNumber3": R["min"],
        "attributeNumber4": R["docket"],
        "attributeNumber5": R["ptlMin"],
        "attributeNumber6": R["detFree"],
        "attributeNumber7": R["detUsd"],
        "domainName": DOMAIN,
    }


def lane_pairs() -> list[tuple[str, str]]:
    sites = [k for k, v in LOCS.items() if v["kind"] == "Customer site"]
    facilities = list(FAC_LOC.values())
    pairs = [(s, f) for s in sites for f in facilities]  # inbound returns
    pairs += [(f, d) for f in facilities for d in LOCS if d != f]  # every outbound move (K5, K7)
    return pairs


def _x_lane(a: str, b: str) -> dict:
    km = lane_km(a, b)
    return {
        "xLaneGid": gid(lane_xid(a, b)),
        "xLaneXid": lane_xid(a, b),
        "sourceLocationGid": gid(a),
        "destLocationGid": gid(b),
        "attributeNumber1": km,  # ASSUMPTION: lane distance (km) and transit (h) kept on the lane, as the demo pins them
        "attributeNumber2": transit_h(km),
        "attribute1": "measured" if (a, b) in LANE_KM or (b, a) in LANE_KM else "great-circle x 1.25",
        "domainName": DOMAIN,
    }


def _rate_geo(a: str, b: str) -> dict:
    R = RATE_CARD
    partner = b == "PTN-MAA"
    return {
        "rateGeoGid": gid(rate_geo_xid(a, b)),
        "rateGeoXid": rate_geo_xid(a, b),
        "rateGeoDesc": f"{a} to {b} · dedicated {R['vehicle']}",
        "rateOfferingGid": gid(R["id"]),
        "xLaneGid": gid(lane_xid(a, b)),
        "equipmentGroupProfileGid": gid("LCV_1.5T_TAILLIFT"),
        "minCost": money(R["min"]),
        "effectiveDate": {"value": "2026-07-01T00:00:00+05:30", "timezone": TZ},
        "expirationDate": {"value": "2027-06-30T23:59:59+05:30", "timezone": TZ},
        "isActive": True,
        "attribute1": "PARTNER" if partner else "FTL",  # partner lanes: the partner collects on its own vehicle
        "costs": [
            {
                "rateGeoCostSeq": 1,
                "chargeAmount": money(R["perKm"]),
                "chargeUnitUomCode": "KM",
                "chargeMultiplier": "SHIPMENT.LOADED_DISTANCE",
                "chargeAction": "A",
                "description": "Per loaded km",
            },
            {
                "rateGeoCostSeq": 2,
                "chargeAmount": money(R["load"]),
                "chargeMultiplier": "SHIPMENT",
                "chargeAction": "A",
                "description": "Loading",
            },
        ],
        "domainName": DOMAIN,
    }


# ------------------------------------------------------------------ shipments
def tracking(code: str, desc: str, at: datetime, loc: str, sgid: str, **extra) -> dict:
    return {
        "shipmentGid": sgid,
        "statusCodeGid": f"PUBLIC.{code}",
        "description": desc,
        "eventdate": dtt(at),
        "eventReceivedDate": dtt(at),
        "timeZoneGid": TZ,
        "locationGid": gid(loc),
        "responsiblePartyGid": "CARRIER",
        "domainName": DOMAIN,
    } | extra


def shipment_doc(
    xid: str,
    *,
    a: str,
    b: str,
    scac: str,
    kg: int,
    qty: int,
    etd: datetime,
    eta: datetime,
    refnums: dict[str, str],
    name: str,
    enroute: str,
    order_release: str | None = None,
) -> dict:
    lane = lane_cost(a, b, kg)
    sgid = gid(xid)
    return {
        "shipmentGid": sgid,
        "shipmentXid": xid,
        "shipmentName": name,
        "shipmentTypeGid": "TRANSPORT",
        "transportModeGid": "TL" if kg >= 150 else "LTL",
        "perspective": "B",
        "servprovGid": gid(scac),
        "rateOfferingGid": gid(RATE_OFFERING),
        "rateGeoGid": gid(rate_geo_xid(a, b)),
        "sourceLocationGid": gid(a),
        "destLocationGid": gid(b),
        "startTime": dtt(etd),
        "endTime": dtt(eta),
        "loadedDistance": amount(lane["km"], "KM"),
        "totalWeight": amount(kg, "KG"),
        "totalShipUnitCount": qty,
        "totalActualCost": money(lane["inr"]),
        "plannedCost": money(lane["inr"]),
        "isServprovFixed": True,
        "isRateGeoFixed": True,
        "attribute1": lane["mode"],
        "attribute2": lane["calc"],
        "refnums": [refnum("shipment", q, v) for q, v in refnums.items() if v is not None],
        "stops": [
            {"stopNum": 1, "locationGid": gid(a), "stopType": "P", "plannedArrival": dtt(etd), "plannedDeparture": dtt(etd)},
            {"stopNum": 2, "locationGid": gid(b), "stopType": "D", "plannedArrival": dtt(eta)},
        ],
        "statuses": [status("ENROUTE", f"ENROUTE_{enroute}"), status("SECURE RESOURCES", "SECURE RESOURCES_ACCEPTED")],
        "orderReleases": [{"orderReleaseGid": order_release}] if order_release else [],
        "domainName": DOMAIN,
    }


def load_xid(case_id: str) -> str:
    return f"LD-{20000 + case_no(case_id)}"


def _inbound(case, as_of: datetime) -> tuple[dict, list[dict], datetime, datetime]:
    f = case.facts
    L = return_logistics(f)
    lane = L["lane"]
    etd = at_ist(L["pickup"], 8)
    eta = max(etd + timedelta(hours=transit_h(lane["km"])), at_ist(L["eta"], 10))
    xid = load_xid(f.id)
    doc = shipment_doc(
        xid,
        a=lane["from"],
        b=lane["to"],
        scac=SCAC[L["carrier"]],
        kg=max(150, ex_kg(f)),
        qty=f.qty,
        etd=etd,
        eta=eta,
        refnums={
            "MOVE_TYPE": "RETURN_COLLECTION",
            "CASE_REF": f.id,
            "ITEM_ID": f.asset_id,
            "RMA": L["rma"],
            "ITEM_DESC": f"{f.product} · {f.mfr}",
        },
        name=f"Return collection {L['rma']}",
        enroute="COMPLETED",
    )
    doc["totalWeight"] = amount(ex_kg(f), "KG")  # actual weight; the dedicated LCV is charged from 150 kg
    for s in doc["stops"]:
        at = etd if s["stopType"] == "P" else eta
        s["actualArrival"] = dtt(at)
        s["actualDeparture"] = dtt(at) if s["stopType"] == "P" else None
    loc = LOCS[lane["to"]]
    events = [
        tracking("AF", "Departed pickup location", etd, lane["from"], doc["shipmentGid"]),
        tracking("X1", "Arrived at delivery location", eta, lane["to"], doc["shipmentGid"]),
        tracking(
            "D1",
            "Completed unloading at delivery location",
            eta,
            lane["to"],
            doc["shipmentGid"],
            externalEventReference=f"POD-{20000 + case_no(f.id)}",
            ssContactName=f"Receiving · {loc['name']}",
        ),
    ]
    booked = at_ist(L["auth"], 15)
    return doc, events, booked, min(eta, as_of)


# ------------------------------------------------------------------ load
def _obj(resource: str, gid_: str, xid: str, doc: dict, at: datetime, upd: datetime | None = None) -> dict:
    return {"resource": resource, "gid": gid_, "xid": xid, "doc": doc, "insert_date": at, "update_date": upd or at}


def load(conn: Connection, seed: Seed) -> dict[str, int]:
    as_of = seed.world.as_of
    ref_at = datetime(2026, 7, 1, 9, 0, tzinfo=as_of.tzinfo)
    rows = [_obj("locations", d["locationGid"], d["locationXid"], d, ref_at) for d in _locations()]
    rows += [_obj("serviceProviders", d["servprovGid"], d["servprovXid"], d, ref_at) for d in _service_providers()]
    ro = _rate_offering()
    rows.append(_obj("rateOfferings", ro["rateOfferingGid"], ro["rateOfferingXid"], ro, ref_at))
    for a, b in lane_pairs():
        x, g = _x_lane(a, b), _rate_geo(a, b)
        rows.append(_obj("xLanes", x["xLaneGid"], x["xLaneXid"], x, ref_at))
        rows.append(_obj("rateGeos", g["rateGeoGid"], g["rateGeoXid"], g, ref_at))
    events = []
    n = 0
    for case in seed.cases.values():
        doc, evs, booked, done = _inbound(case, as_of)
        rows.append(_obj("shipments", doc["shipmentGid"], doc["shipmentXid"], doc, booked, done))
        events += [{"shipment_gid": doc["shipmentGid"], "doc": e, "insert_date": done, "update_date": done} for e in evs]
        n += 1  # noqa: SIM113 - counter kept explicit
    conn.execute(insert(t.OBJECT), rows)
    conn.execute(insert(t.TRACKING_EVENT), events)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["resource"]] = counts.get(r["resource"], 0) + 1
    counts["trackingEvents"] = len(events)
    return counts


def create(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS otm"))
    t.metadata.create_all(conn)


def reset(conn: Connection, seed: Seed) -> dict[str, int]:
    t.metadata.drop_all(conn)
    create(conn)
    return load(conn, seed)


def ensure(conn: Connection, seed: Seed) -> None:
    create(conn)
    if conn.execute(text("SELECT count(*) FROM otm.object")).scalar_one() == 0:
        load(conn, seed)
