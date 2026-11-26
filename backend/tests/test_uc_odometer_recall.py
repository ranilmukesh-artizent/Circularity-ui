"""Plan 9, P9-9.9 (stories UC-07 and UC-08): the odometer gate G-VEH-ODO, the open recall gate G-VEH-RECALL and the action
`evidence.refresh` that re-runs a stale recall check.

An odometer photo that differs from the lease system's record by more than the pack's tolerance holds the car for a second
inspection (`EX-UC-ODO`); a reading that is not the actual mileage is disclosed on every channel. An open recall blocks
retail until it is remedied (auction and dealer trade carry the disclosure); a rental fleet may not sell it on any channel. A
recall check older than 30 days is re-run by `evidence.refresh`, which only a person with `openCases` or an agent acting for
one may call; it reads the recall database through the adapter's `lookup` (a stub client here: no source-sim). The facts are
written by the real adapters' mapping on literal records. Legal note: the tolerance, the exempt years and the fleet size are
the pack's data; Kinective's Legal team reviews the gates (49 CFR 580, 49 U.S.C. 30120(i)) before they are relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.actions import evidence_refresh
from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import agent_mode
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, vin_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from di.services.engine.routes import mk_route
from di.services.modeler.gates import apply_gate_results, evaluate_gates
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers.fleet_evidence import NOW_KEY
from tests import starting
from tests.helpers import call, client, h

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "used_cars.json"
CHANNELS = ("retail", "auction", "dealer_trade", "salvage")
NOW = "2026-10-07T09:00:00+00:00"  # the pinned clock
STALE = "2026-09-06T09:00:00+00:00"  # 31 days before it
ODO = "Odometer verified and disclosed"
RECALL = "No retail with an open recall"
NOT_ACTUAL = "Odometer reading is not the actual mileage"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _lease(n: int, **over: Any) -> dict[str, Any]:
    return {
        "leaseId": f"LS-{n:04d}", "vin": vin(n), "lesseeRef": "L-0001", "leaseEnd": "2026-10-03", "residualValue": 14000,
        "contractMileage": 36000, "odometerAtReturn": 38000, "odometerLastService": 38000, "odometerStatementRef": f"OS-{n:04d}",
        "odometerNotActual": False, "modelYear": 2021, "segment": "suv", "powertrain": "petrol", "returnCenter": "RC-East",
        "sellerFleetSize": 0, "status": "returned", "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
    } | over  # fmt: skip


def _title(n: int) -> dict[str, Any]:
    return {"vin": vin(n), "titleStatus": "clear", "brand": None, "brandSource": None, "liens": [], "checkedAt": STALE,
            "org_unit_id": ORG}  # fmt: skip


def _insp(n: int, reading: int | None) -> dict[str, Any]:
    return {
        "inspectionId": f"IN-{n:04d}", "vin": vin(n), "status": "complete", "conditionScore": 4, "odometerPhotoReading": reading,
        "reconEstimate": 1200, "completedAt": "2026-10-06T10:00:00+00:00", "org_unit_id": ORG,
    }  # fmt: skip


CAMPAIGN = {"campaignId": "SYN-24V-001", "component": "Fuel pump relay", "summary": "s", "remedyAvailable": True}


def _recall_doc(n: int, checked: str = NOW, open_: list | None = None, remedied: list | None = None) -> dict[str, Any]:
    return {"vin": vin(n), "checkedAt": checked, "openRecalls": open_ or [], "remedied": remedied or [], "org_unit_id": ORG}


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYNUC%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYNUC%"})


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.2"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("uc_lease", "uc_title", "uc_insp", "uc_recall"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _car(
    n: int, *, lease: dict[str, Any] | None = None, reading: int | None = None, recall: dict[str, Any] | None = None
) -> dict:
    """A lease return with a clear title, its inspection (when it has a photo reading) and its recall check on file, opened as
    a case. The recall check is fresh and clean unless `recall` says otherwise."""
    _write("uc_lease", "lease_returns", _lease(n) | (lease or {}))
    _write("uc_title", "titles", _title(n))
    if reading is not None:
        _write("uc_insp", "inspections", _insp(n, reading))
    _write("uc_recall", "recalls", recall if recall is not None else _recall_doc(n))
    key = vin_key(ORG, vin(n))  # the buyer reporting status (the salvage gate, not under test) is on file
    row = {"asset_key": key, "type": "reporting_status", "result": "pass", "ref": "R-1", "at": STALE, "value": {}}
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, "reporting_status"), f, v) for f, v in row.items()])
        s.commit()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()
    body = {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": vin_key(ORG, vin(n)), "reason": "lease_end",
            "facts": {"vin": vin(n), "mileage": 38000, "return_date": "2026-10-03"}}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _gate(c: dict[str, Any], gate_id: str) -> dict[str, Any]:
    return next(g for g in c["gates"] if g["id"] == gate_id)


def _route(c: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in c["routes"] if r["id"] == rid)


def _failed(c: dict[str, Any]) -> dict[str, str | None]:
    """The reason each channel is failed by the gates of the case (the pack has no value lines before P9-9.10, so its own
    routes are excluded for that): None for a channel no gate fails."""
    pack = load_pack("used_cars")
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": []}) for r in pack.routes]
    apply_gate_results(routes, evaluate_gates(c | {NOW_KEY: NOW}, pack))
    return {r["id"]: (r["failReason"] if r["excluded"] else None) for r in routes}


def _items(cid: str, type_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT id, status, owner_role, action FROM work_item WHERE case_id = :c AND type = :t ORDER BY id"),
            {"c": cid, "t": type_id},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]


def test_uc_07_odometer_mismatch_holds_pricing():
    c = _car(4, lease={"odometerLastService": 46240}, reading=61240)
    gate = _gate(c, "G-VEH-ODO")
    assert gate["passed"] is False and gate["hold"] is True and sorted(gate["routes"]) == sorted(CHANNELS)
    assert gate["reason"] == "Odometer photo reading 61,240 does not match the lease record 46,240 (tolerance 500 miles)"
    assert c["gateHold"] is not None and c["gateHold"]["gates"] == ["G-VEH-ODO"] and c["recommendation"] is None
    assert all(v and v.startswith(f"{ODO}: ") for v in _failed(c).values())  # no route is valued
    (item,) = _items(c["id"], "EX-UC-ODO")
    assert (item["status"], item["owner_role"], item["action"]) == (
        "open",
        "Warehouse Manager",
        "Second inspection before pricing",
    )
    shown = next(e for e in gate["evidence"] if e["type"] == "odometer_statement")
    assert shown["value"]["ref"] == "OS-0004"  # the lessee's statement is in the evidence


def test_uc_07_a_second_inspection_that_agrees_releases_the_car():
    c = _car(4, lease={"odometerLastService": 46240}, reading=61240)
    _write("uc_insp", "inspections", _insp(4, 46300))  # within the tolerance of 500 miles
    with SessionLocal() as s:
        queued = (
            s.execute(text("SELECT dedupe_key FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
        )
    assert queued == [f"case.gateRecheck:{vin_key(ORG, vin(4))}"]
    worker.HANDLERS["case.gateRecheck"]({"asset_key": vin_key(ORG, vin(4))})
    got = _get(c["id"])
    assert _gate(got, "G-VEH-ODO")["passed"] is True and got.get("gateHold") is None
    assert _items(c["id"], "EX-UC-ODO")[0]["status"] == "done"


def test_uc_07_a_reading_within_the_tolerance_passes():
    c = _car(4, lease={"odometerLastService": 46240}, reading=46740)
    assert _gate(c, "G-VEH-ODO")["passed"] is True and c.get("gateHold") is None and _items(c["id"], "EX-UC-ODO") == []


def test_uc_07_not_actual_mileage_disclosed():
    c = _car(11, lease={"odometerNotActual": True}, reading=38000)
    assert all(_route(c, r)["disclosures"] == [NOT_ACTUAL] for r in CHANNELS)
    gate = _gate(c, "G-VEH-ODO")
    assert gate["passed"] is True and gate["kind"] == "disclose" and gate["reason"] == NOT_ACTUAL
    assert c.get("gateHold") is None and _failed(c) == dict.fromkeys(CHANNELS)


def test_uc_07_exempt_old_car():
    c = _car(9, lease={"modelYear": 2009, "odometerStatementRef": None, "odometerLastService": 10000}, reading=90000)
    gate = _gate(c, "G-VEH-ODO")
    assert gate["passed"] is True and gate["reason"] == "Odometer disclosure exempt" and c.get("gateHold") is None


def test_uc_07_a_lease_return_without_the_statement_needs_it():
    c = _car(5, lease={"odometerStatementRef": None})
    gate = _gate(c, "G-VEH-ODO")
    assert (gate["passed"], gate["kind"], gate["hold"], gate["missing"]) == (False, "require_step", False, ["Odometer statement"])
    assert c.get("gateHold") is None and _failed(c) == dict.fromkeys(CHANNELS)  # a missing statement is asked for, not a hold


def test_uc_08_open_recall_blocks_retail_only():
    c = _car(2, recall=_recall_doc(2, open_=[CAMPAIGN]))
    gate = _gate(c, "G-VEH-RECALL")
    assert gate["passed"] is False and gate["routes"] == ["retail"] and gate["hold"] is False
    failed = _failed(c)
    assert failed["retail"] == f"{RECALL}: Open recall: no retail until remedied"
    assert [k for k, v in failed.items() if v is None] == ["auction", "dealer_trade", "salvage"]
    for r in ("auction", "dealer_trade"):
        assert _route(c, r)["disclosures"] == ["Open recall disclosed: SYN-24V-001"]
    assert c.get("gateHold") is None
    assert any(e["type"] == "vin_recall" and e["at"] == NOW for e in gate["evidence"])  # the check date is shown


def test_uc_08_a_remedied_recall_does_not_block():
    done = [{"campaignId": "SYN-24V-001", "remedyRef": "RR-0002", "remediedAt": "2026-09-01"}]
    c = _car(2, recall=_recall_doc(2, remedied=done))
    assert _gate(c, "G-VEH-RECALL")["passed"] is True and _failed(c) == dict.fromkeys(CHANNELS)
    assert all("disclosures" not in r for r in c["routes"])


def test_uc_08_one_campaign_remedied_another_still_open_fails_naming_the_open_one():
    second = CAMPAIGN | {"campaignId": "SYN-25V-002", "component": "Brake hose"}
    done = [{"campaignId": "SYN-24V-001", "remedyRef": "RR-0002", "remediedAt": "2026-09-01"}]
    c = _car(2, recall=_recall_doc(2, open_=[second], remedied=done))  # a remedy ref is on file, but for the other campaign
    gate = _gate(c, "G-VEH-RECALL")
    assert gate["passed"] is False and gate["routes"] == ["retail"]
    assert _failed(c)["retail"] == f"{RECALL}: Open recall: no retail until remedied"
    assert _route(c, "auction")["disclosures"] == ["Open recall disclosed: SYN-25V-002"]  # the open campaign, not the remedied
    both = [CAMPAIGN, second]  # the same campaign open and remedied counts as remedied
    ok = _car(3, recall=_recall_doc(3, open_=both, remedied=done))
    assert _route(ok, "auction")["disclosures"] == ["Open recall disclosed: SYN-25V-002"]
    all_done = [*done, {"campaignId": "SYN-25V-002", "remedyRef": "RR-0003", "remediedAt": "2026-09-02"}]
    clear = _car(4, recall=_recall_doc(4, open_=both, remedied=all_done))
    assert _gate(clear, "G-VEH-RECALL")["passed"] is True and _failed(clear) == dict.fromkeys(CHANNELS)


def test_uc_08_rental_fleet_blocks_all_sale():
    c = _car(50, lease={"sellerFleetSize": 40}, recall=_recall_doc(50, open_=[CAMPAIGN]))
    msg = "Open recall: a rental fleet of 35 or more may not sell until remedied"
    assert _failed(c) == dict.fromkeys(CHANNELS, f"{RECALL}: {msg}")
    assert sorted(_gate(c, "G-VEH-RECALL")["routes"]) == sorted(CHANNELS)
    quiet = _car(51, lease={"sellerFleetSize": 40})  # a big fleet without an open recall sells
    assert _gate(quiet, "G-VEH-RECALL")["passed"] is True


def test_uc_08_stale_check_is_rerun(monkeypatch):
    c = _car(2, recall=_recall_doc(2, checked=STALE, open_=[CAMPAIGN]))
    gate = _gate(c, "G-VEH-RECALL")
    assert gate["passed"] is False and gate["missing"] == ["Recall check"] and gate["missingTypes"] == ["recall_check"]
    assert gate["reason"] == "Recall check older than 30 days; re-run" and gate["routes"] == [] and c.get("gateHold") is None
    seen: list[str] = []

    class Stub:
        def get_json(self, path: str, **_kw: Any) -> dict[str, Any]:
            seen.append(path)
            return _recall_doc(2, checked=NOW, open_=[CAMPAIGN]) | {"org_unit_id": None}

    monkeypatch.setattr(evidence_refresh, "client_for", lambda *_a, **_k: Stub())
    hdr = h("planner-a") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post(
        "/api/actions/evidence.refresh", json={"case_id": c["id"], "evidence_type": "recall_check"}, headers=hdr
    ).json()
    out = _ok(r)
    assert seen == [f"/recalls/vin/{vin(2)}"] and out == {"case_id": c["id"], "evidence_type": "recall_check", "checked_at": NOW}
    got = _get(c["id"])
    again = _gate(got, "G-VEH-RECALL")
    assert again["missing"] == [] and again["routes"] == ["retail"] and "Open recall: no retail" in again["reason"]
    with SessionLocal() as s:
        facts = canonical.get(s, "condition", vin_key(ORG, vin(2)))
    assert facts is not None and facts["data"]["recall_checked_at"] == NOW


def test_evidence_refresh_refuses_unsupported_type():
    c = _car(2)
    r = call("evidence.refresh", {"case_id": c["id"], "evidence_type": "title_brand"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "not_supported"
    r = call("evidence.refresh", {"case_id": c["id"], "evidence_type": "no_such_type"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "not_supported"


def test_evidence_refresh_never_changes_an_approved_decision():
    c = _car(2)
    c["stage"] = "approved"
    with SessionLocal() as s:
        cases.save(s, c)
        s.commit()
    r = call("evidence.refresh", {"case_id": c["id"], "evidence_type": "recall_check"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "decided"


def test_evidence_refresh_needs_open_cases_and_agents_may_prepare_it():
    c = _car(2)
    no = call("evidence.refresh", {"case_id": c["id"], "evidence_type": "recall_check"}, "approver")
    assert no["ok"] is False and no["error"]["code"] != "not_supported"
    a = ACTIONS["evidence.refresh"]
    assert (a.risk, a.perm, a.scope) == ("act", "openCases", "case") and agent_mode(a) == "yes" and not forbidden(a.id)


def test_uc_07_uc_08_checks_are_pure_on_a_case_record():
    pack = load_pack("used_cars")

    def run(case: dict[str, Any]) -> dict[str, Any]:
        return {r.gate_id: r for r in evaluate_gates({"cls": "car_ice", NOW_KEY: NOW} | case, pack)}

    odo = run({"odometer": {"model_year": 2021, "return_kind": "lease_end", "statement_ref": "OS-1", "photo_reading": 20000,
                            "lease_record": 19000}})["G-VEH-ODO"]  # fmt: skip
    assert not odo.passed and odo.effect.hold and odo.evidence_missing == ()
    old = run({"odometer": {"model_year": 2010, "return_kind": "lease_end", "photo_reading": 1, "lease_record": 99999}})
    assert old["G-VEH-ODO"].passed and old["G-VEH-ODO"].reason == "Odometer disclosure exempt"
    trade = run({"odometer": {"model_year": 2019, "return_kind": "trade_in"}})["G-VEH-ODO"]
    assert trade.passed  # only a lease return needs the lessee's statement
    fresh = run({"recall": {"checked_at": NOW, "open": False, "campaigns": [], "remedy_ref": None}})["G-VEH-RECALL"]
    assert fresh.passed
    day30 = run({"recall": {"checked_at": "2026-09-07T09:00:00+00:00", "open": False}})["G-VEH-RECALL"]
    assert day30.passed  # exactly 30 days old is still current
    none = run({})["G-VEH-RECALL"]
    assert not none.passed and none.evidence_missing == ("recall_check",)
    noclock = {r.gate_id: r for r in evaluate_gates({"recall": {"checked_at": STALE, "open": False}}, pack)}["G-VEH-RECALL"]
    assert noclock.passed  # a case read with no clock is not judged stale
