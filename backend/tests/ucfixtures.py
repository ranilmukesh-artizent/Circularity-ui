"""The used-car samples UC-S1 to UC-S8 as the real adapters write them (plan 9, P9-9.11; no source-sim): a lease return, its
title, inspection and recall check, and the market the dealer system, the pricing guide and the auction platform serve for the
car. Shared by `test_uc_routing.py` and `test_used_cars_paths.py`. Every record goes through the adapter's own `map`."""

import copy
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, vin_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "used_cars.json"
NOW = "2026-10-07T09:00:00+00:00"  # the pinned clock
SOURCES = ("uc_lease", "uc_title", "uc_insp", "uc_recall", "uc_dms", "uc_price", "uc_auction")
CAMPAIGN = {"campaignId": "SYN-24V-001", "component": "Fuel pump relay", "summary": "s", "remedyAvailable": True}
LIEN = {"lienId": "LN-0003", "holderRef": "H-004", "amount": 8200, "released": False, "releaseRef": None, "releasedAt": None}

# what differs from UC-S1 (the clean petrol SUV: 38,000 miles, score 4, recon 1,200, book value 19,500)
SAMPLES: dict[int, dict[str, Any]] = {
    1: {}, 2: {"recall": True}, 3: {"lien": True}, 4: {"miles": 61240, "photo": 61240, "last_service": 46240},
    5: {"miles": 133000, "photo": 133000, "last_service": 133000},
    6: {"powertrain": "ev", "segment": "ev_crossover", "battery": 74},
    7: {"recon": 2800},
    8: {"score": 1, "recon": 16500, "lots": ("LOT-C",), "guide": 21000, "salvage": 3900, "wholesale": None, "bid": None},
}  # fmt: skip
LOTS = {  # lot -> (distance miles, average price, days to sale, comparables, spread)
    "LOT-N": (12, 23600, 34, 12, 1500), "LOT-C": (40, 24000, 21, 22, 1300), "LOT-S": (95, 24300, 15, 18, 1200),
}  # fmt: skip


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM work_item WHERE type = 'AP-UC-RECON'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYNUC%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


def start(version: str = "1.9.3") -> None:
    """The starting state, the shipped pack published as the org's, and the seven sources registered."""
    starting.reset()
    clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = version
    pid = ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    ok(call("pack.submit", {"id": pid}, "admin"))
    ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in SOURCES:
            extra.register(s, sid, ORG)
        s.commit()


def finish() -> None:
    clean()
    starting.reset()


def write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def records(n: int, like: int | None = None, **over: Any) -> dict[str, Any]:
    """The records of sample UC-S<n> by source, as each system serves them (`over` changes a sample's own settings)."""
    o = {"miles": 38000, "photo": 38000, "last_service": 38000, "recon": 1200, "score": 4, "powertrain": "petrol",
         "segment": "suv", "battery": None, "wholesale": 21500, "bid": 20900,
         "lots": tuple(LOTS), "guide": 24000, "salvage": 2100, "recall": False,
         "lien": False} | SAMPLES[like or n] | over  # fmt: skip
    lease = {
        "leaseId": f"LS-{n:04d}", "vin": vin(n), "lesseeRef": "L-0001", "leaseEnd": "2026-10-03", "residualValue": 19500,
        "contractMileage": 36000, "odometerAtReturn": o["miles"], "odometerLastService": o["last_service"],
        "odometerStatementRef": f"OS-{n:04d}", "odometerNotActual": False, "modelYear": 2022, "segment": o["segment"],
        "powertrain": o["powertrain"], "returnCenter": "RC-East", "sellerFleetSize": 0, "status": "returned",
        "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
    }  # fmt: skip
    title = {"vin": vin(n), "titleStatus": "lien" if o["lien"] else "clear", "brand": None, "brandSource": None,
             "liens": [LIEN] if o["lien"] else [], "checkedAt": NOW, "org_unit_id": ORG}  # fmt: skip
    insp = {
        "inspectionId": f"IN-{n:04d}", "vin": vin(n), "status": "complete", "conditionScore": o["score"],
        "odometerPhotoReading": o["photo"], "reconEstimate": o["recon"], "batterySoh": o["battery"],
        "completedAt": "2026-10-06T10:00:00+00:00", "org_unit_id": ORG,
    }  # fmt: skip
    recall = {"vin": vin(n), "checkedAt": NOW, "openRecalls": [CAMPAIGN] if o["recall"] else [], "remedied": [],
              "org_unit_id": ORG}  # fmt: skip
    market = {
        "vin": vin(n), "segment": o["segment"], "mileage": o["miles"], "band": "0-40k", "org_unit_id": ORG,
        "lots": {
            lot: {"distanceMiles": d, "avgPrice": 21000 if n == 8 else p, "avgDaysToSale": days, "count": c, "spread": sp}
            for lot, (d, p, days, c, sp) in LOTS.items() if lot in o["lots"]
        },
        "bids": [{"bidId": "PB-0001", "vin": vin(n), "partner": "Partner A", "amount": o["bid"]}] if o["bid"] else [],
    }  # fmt: skip
    price = {"vin": vin(n), "retail": o["guide"], "wholesale": o["wholesale"], "org_unit_id": ORG}
    auction = {"vin": vin(n), "org_unit_id": ORG, "returnCenter": "RC-East", "nextSaleDays": 6, "sellFee": 325,
               "transport": 120, "bestBid": {"amount": o["salvage"], "buyerId": "B-001"}}  # fmt: skip
    return {"uc_lease": ("lease_returns", lease), "uc_title": ("titles", title), "uc_insp": ("inspections", insp),
            "uc_recall": ("recalls", recall), "uc_dms": ("vin_market", market), "uc_price": ("values", price),
            "uc_auction": ("vin_auction", auction)}  # fmt: skip


def write_car(n: int, like: int | None = None, **over: Any) -> None:
    for source, (resource, payload) in records(n, like, **over).items():
        write(source, resource, payload)
    key = vin_key(ORG, vin(n))  # the buyer's reporting status (G-VEH-SALV) is on file for every sample
    row = {"asset_key": key, "type": "reporting_status", "result": "pass", "ref": "R-1", "at": NOW, "value": {}}
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, "reporting_status"), f, v) for f, v in row.items()])
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def open_car(n: int, like: int | None = None, **over: Any) -> dict[str, Any]:
    """Sample UC-S<n> on file in every system and opened as a case, as the planner does (`case.open`)."""
    write_car(n, like, **over)
    miles = records(n, like, **over)["uc_lease"][1]["odometerAtReturn"]
    body = {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": vin_key(ORG, vin(n)), "reason": "lease_end",
            "facts": {"vin": vin(n), "mileage": miles, "return_date": "2026-10-03"}}  # fmt: skip
    return get(ok(call("case.open", body, "planner-a"))["case_id"])


def get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def items(cid: str, type_: str = "AP-UC-RECON") -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text(
                "SELECT id, kind, status, owner_role, title, cause, action, outcome FROM work_item "
                "WHERE case_id = :c AND type = :t ORDER BY id"
            ),
            {"c": cid, "t": type_},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]
