"""Plan 9, P9-10.11 (gap found by P9-10.10; registry entry I-21): a live telecom case is valued on the canonical records alone.

The telecom valuer needs the market, demand and spares facts of its unit (`market.new_price`, `market.broker_bids`,
`demand.use_probability`, `demand.need_6m`, the open site demand, `spares.gap`, `asset.weight_kg`, `asset.firmware`). Nothing put
them on a case, so every route of a stored case was "not valued, inputs missing". `cases/telecom_facts` lays the unit's canonical
`asset`, `condition`, `market`, `demand` and spares records on the case when `decide_case` has a session. These tests open a case
from facts the adapters wrote (their real `map`, on literal records, no source-sim) and nothing else, and read its routes.
Legal note: the export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before reliance.
"""

import copy
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import serial_key
from di.services.cases import intake, telecom_facts
from di.services.cases import store as cases
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
PACK_FILE = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "telecom_network.json"
PARAMS = load_pack("telecom_network").valuer.params["params"]
MODEL = "RRU-4410"
CELLS = ("%:SN-TN-%", f"{ORG}:%", "shared:%", MODEL, "SD-%", "SPARE-%")


def sn(n: int) -> str:
    return f"SN-TN-{n:04d}"


def cent(x: float | Decimal) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _clean() -> None:
    with engine.begin() as conn:
        for t in ("agent_run_step", "agent_run", "agent_proposal", "pack_version", "customer_overlay"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        for p in CELLS:
            conn.execute(text("DELETE FROM provenance WHERE model <> 'part' AND key LIKE :p"), {"p": p})
            conn.execute(text("DELETE FROM canonical WHERE model <> 'part' AND key LIKE :p"), {"p": p})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK_FILE.read_text(encoding="utf-8")))
    doc["version"] = "1.9.2"  # the shipped pack, published as the org's
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("tn_inv", "tn_decom", "tn_bench", "tn_spares", "tn_broker"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _unit(n: int, site: str = "SITE-101", model: str = MODEL, firmware: str = "3.1.2") -> dict[str, Any]:
    """The unit as the tracker, the inventory and the bench wrote it: removed, in the inventory, wiped, weighed."""
    job = {"jobId": "RJ-01", "siteId": site, "removedAt": "2026-10-04T08:00:00+00:00", "programme": "5G refresh",
           "serial": sn(n), "model": model, "org_unit_id": ORG}  # fmt: skip
    _write("tn_decom", "removal_jobs", job)
    _write("tn_inv", "elements", {
        "serial": sn(n), "model": model, "partNumber": "PN-4410-02", "hwRevision": "B2", "firmware": firmware,
        "manufacturer": "MFR-B", "site": site, "siteKind": "edge", "region": "North", "status": "removed",
        "exportClassInferred": None, "exportClassConfirmed": None, "org_unit_id": ORG,
    })  # fmt: skip
    _write("tn_bench", "results", {
        "serial": sn(n), "tests": {"passed": 18, "total": 18}, "firmware": firmware, "firmwareLatest": "3.2",
        "wipe": {"status": "verified", "attempts": 1, "scope": ["configuration", "credentials", "keys", "logs"],
                 "verifiedAt": "2026-10-03T09:00:00Z", "certificateRef": f"WC-{n:04d}"},
        "boards": [], "weightKg": 9.5, "battery": None, "org_unit_id": ORG,
    })  # fmt: skip
    return job


def _market(need_north: int = 2) -> None:
    """What spares planning, the broker and the tracker serve: catalogue price, the North cell (target 3, one unit in stock),
    the six-month need, a bid, and the open site demand SD-112 for the model."""
    _write("tn_spares", "catalogue", {"model": MODEL, "newPrice": 9800, "generation": "4", "org_unit_id": ORG})
    cell = {"region": "North", "model": MODEL, "org_unit_id": ORG}
    _write("tn_spares", "targets", cell | {"target": 3, "useProbability12m": 0.55})
    _write("tn_spares", "forecast6m", cell | {"need": need_north})
    _write("tn_spares", "stock", {"serial": "SPARE-1", "model": MODEL, "region": "North", "idleDays": 40, "org_unit_id": ORG})
    _write("tn_broker", "bids", {"model": MODEL, "bids": [{"bidId": "B-1", "unitPrice": 3400, "qty": 1}]})
    _write("tn_decom", "site_demand", {"demandId": "SD-112", "siteId": "SITE-112", "model": MODEL, "minFirmwareMajor": None,
                                       "needBy": "2026-11-15", "region": "North"})  # fmt: skip


def _open(job: dict[str, Any]) -> dict[str, Any]:
    facts = {"serial": job["serial"], "model": job["model"], "site": job["siteId"], "removed_at": job["removedAt"],
             "removal_job": job["jobId"], "programme": job["programme"]}  # fmt: skip
    body = {"org_unit_id": ORG, "template_key": "telecom_network", "asset_key": serial_key(ORG, job["serial"]),
            "reason": "decommission", "facts": facts}  # fmt: skip
    with SessionLocal() as s:
        c = cases.get(s, _ok(call("case.open", body, "planner-a"))["case_id"])
    assert c is not None
    return c


def _route(c: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in c["routes"] if r["id"] == rid)


def test_tn_11_live_case_is_valued_from_canonical_facts_only():
    job = _unit(1)
    _market()
    c = _open(job)
    assert "valuer" not in c or not any(
        k.startswith(("market", "demand", "spares")) for k in c["valuer"]
    )  # opened with the event's
    cost = {k: Decimal(str(PARAMS[k])) for k in ("test_cost", "logistics_per_unit", "install_job", "refurb_cost", "recycle_fee")}
    redeploy, spare, resell = (_route(c, r) for r in ("redeploy", "spare", "resell"))
    assert redeploy["excluded"] is False and redeploy["net"] == cent(
        9800 - cost["test_cost"] - cost["logistics_per_unit"] - cost["install_job"]
    )
    hold = Decimal(str(PARAMS["spare_holding_per_month"])) * int(PARAMS["spare_horizon_months"])
    assert spare["net"] == cent(Decimal("9800") * Decimal("0.55") - cost["refurb_cost"] - hold - cost["logistics_per_unit"])
    assert resell["excluded"] is True and "within 6 months" in str(resell["failReason"])  # the model is needed in North
    recycle = _route(c, "recycle")  # the bench's weight: 9.5 kg
    assert recycle["net"] == cent(
        Decimal("9.5") * Decimal(str(PARAMS["material_per_kg"])) - cost["recycle_fee"] - cost["logistics_per_unit"]
    )
    assert c["recommendation"]["id"] == "redeploy" and c["recommendation"]["dest"]["demand"] == "SD-112"
    reasons = [(r["id"], str(r["failReason"])) for r in c["routes"]]
    gone = [(rid, why) for rid, why in reasons if "missing" in why and "input" in why]
    assert gone == []  # no route is "not valued: input missing"


def test_tn_11_resale_is_valued_when_no_region_needs_the_model():
    job = _unit(3, model="RRU-4410")
    _market(need_north=0)
    _write("tn_decom", "site_demand", {"demandId": "SD-112", "siteId": "SITE-112", "model": "OTHER-1", "minFirmwareMajor": None,
                                       "needBy": "2026-11-15", "region": "North"})  # no open demand for this model  # fmt: skip
    c = _open(job)
    resell = _route(c, "resell")
    assert resell["excluded"] is False and resell["net"] > 0
    assert _route(c, "redeploy")["excluded"] is True and "No open site demand" in str(_route(c, "redeploy")["failReason"])


def test_tn_11_two_units_one_demand_the_second_goes_to_the_spares_gap():
    first, second = _unit(1), _unit(2)
    _market()
    c1 = _open(first)
    c2 = _open(second)
    assert c1["recommendation"]["id"] == "redeploy"
    assert c2["recommendation"]["id"] == "spare"  # the demand is filled once; North is two units short of its spares target
    assert "Site demand SD-112 filled by SN-TN-0001" in str(_route(c2, "redeploy")["failReason"])


def test_tn_11_the_gatherer_names_what_it_laid_on():
    job = _unit(1, firmware="5.2")
    _market()
    with SessionLocal() as s:
        facts = telecom_facts.gather(s, {"assetId": serial_key(ORG, job["serial"]), "owner": ORG, "network": {"model": MODEL}})
    assert facts["market"]["new_price"] == 9800 and facts["market"]["broker_bids"][0]["unitPrice"] == 3400
    assert facts["demand"]["use_probability"] == {"North": 0.55} and facts["demand"]["need_6m"] == {"North": 2}
    assert (facts["demand"]["open_site_demand"], facts["demand"]["id"], facts["demand"]["site"]) == (True, "SD-112", "SITE-112")
    assert facts["spares"] == {"gap": 2, "region_below_target": "North"}  # target 3, one unit in the pool
    assert facts["asset"]["weight_kg"] == 9.5 and facts["asset"]["firmware"] == "5.2"
    assert facts["condition"]["bench_passed"] == 18
    with SessionLocal() as s:  # a unit the store does not know gets nothing (no fact is made up)
        assert telecom_facts.gather(s, {"assetId": serial_key(ORG, "SN-TN-9999"), "owner": ORG}) == {}
    assert intake.UNIT_TEMPLATE == "telecom_network"
