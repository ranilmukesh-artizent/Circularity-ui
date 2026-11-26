"""Plan 9, P9-9.8 (stories UC-06 and UC-24): the title finance gate G-VEH-TITLE and the title brand gate G-VEH-BRAND.

A lien, an unconfirmed trade-in payoff or a title that is not clear fails every sale channel and holds the car for the title
desk (`EX-UC-LIEN`); only a person closes the exception, and only once the lien's release is on file. A title brand is
disclosed on every route; flood and salvage brands also block retail. The facts are written by the real adapters' mapping on
literal records (no source-sim). Legal note: the lists of brands are the pack's data; Kinective's Legal team reviews them.
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
from di.services.actions.registry import ACTIONS
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, vin_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from di.services.engine.routes import mk_route
from di.services.modeler.gates import GateEffect, GateResult, apply_disclosures, apply_gate_results, evaluate_gates
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, client, h

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "used_cars.json"
TITLE = "Clear title, no open finance"
CHANNELS = ("retail", "auction", "dealer_trade", "salvage")
OLD = "2026-10-07T09:00:00+00:00"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


def _lease(n: int) -> dict[str, Any]:
    return {
        "leaseId": f"LS-{n:04d}", "vin": vin(n), "lesseeRef": "L-0001", "leaseEnd": "2026-10-03", "residualValue": 14000,
        "contractMileage": 36000, "odometerAtReturn": 38000, "odometerLastService": 31000, "odometerStatementRef": f"OS-{n:04d}",
        "odometerNotActual": False, "modelYear": 2021, "segment": "suv", "powertrain": "petrol", "returnCenter": "RC-East",
        "sellerFleetSize": 0, "status": "returned", "updatedAt": "2026-10-07T08:04:00+00:00", "org_unit_id": ORG,
    }  # fmt: skip


def _title(n: int, **over: Any) -> dict[str, Any]:
    """A title document as the title service serves it (the mock's shape): clear, no brand, no lien."""
    return {"vin": vin(n), "titleStatus": "clear", "brand": None, "brandSource": None, "liens": [], "checkedAt": OLD,
            "org_unit_id": ORG} | over  # fmt: skip


LIEN = {"lienId": "LN-0003", "holderRef": "H-004", "amount": 8200, "released": False, "releaseRef": None, "releasedAt": None}
RELEASED = LIEN | {"released": True, "releaseRef": "LR-000003", "releasedAt": "2026-10-09T09:00:00+00:00"}
TRADE = {
    "tradeId": "TI-0062", "vin": vin(62), "tradeAllowance": 9000, "payoffAmount": 5400, "payoffConfirmed": False,
    "mileage": 52000, "modelYear": 2019, "segment": "sedan", "powertrain": "petrol", "org_unit_id": ORG,
}  # fmt: skip


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
    doc["version"] = "1.9.1"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("uc_lease", "uc_dms", "uc_title"):
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


def _evidence(n: int) -> None:
    """The odometer statement and the VIN recall result on file (other gates; so that only the title gates decide)."""
    key = vin_key(ORG, vin(n))
    for t in ("odometer_statement", "vin_recall", "reporting_status"):
        row = {"asset_key": key, "type": t, "result": "pass", "ref": "R-1", "at": OLD, "value": {}}
        with SessionLocal() as s:
            canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, t), f, v) for f, v in row.items()])
            s.commit()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _open(n: int, reason: str = "lease_end") -> dict[str, Any]:
    body = {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": vin_key(ORG, vin(n)), "reason": reason,
            "facts": {"vin": vin(n), "mileage": 38000, "return_date": "2026-10-03"}}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _car(n: int, title: dict[str, Any], reason: str = "lease_end") -> dict[str, Any]:
    """A car with its lease (or trade-in), its other evidence and its title on file, opened as a case."""
    if reason == "lease_end":
        _write("uc_lease", "lease_returns", _lease(n))
    _write("uc_title", "titles", title)
    _evidence(n)
    return _open(n, reason)


def _gate(c: dict[str, Any], gate_id: str) -> dict[str, Any]:
    return next(g for g in c["gates"] if g["id"] == gate_id)


def _route(c: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in c["routes"] if r["id"] == rid)


def _failed(c: dict[str, Any]) -> dict[str, str | None]:
    """The reason each channel is failed by the gates of the case, applied to routes the valuer has left eligible (the pack
    has no value lines before P9-9.10, so its own routes are excluded for that): None for a channel no gate fails."""
    pack = load_pack("used_cars")
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": []}) for r in pack.routes]
    apply_gate_results(routes, evaluate_gates(c, pack))
    return {r["id"]: (r["failReason"] if r["excluded"] else None) for r in routes}


def _items(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text(
                "SELECT id, status, owner_role, action, outcome FROM work_item "
                "WHERE case_id = :c AND type = 'EX-UC-LIEN' ORDER BY id"
            ),
            {"c": cid},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]


def _release() -> None:
    """The lender releases the lien: the title service's next sync carries it."""
    _write("uc_title", "titles", _title(3, liens=[RELEASED], checkedAt="2026-10-09T09:00:00+00:00"))


def _recheck() -> None:
    with SessionLocal() as s:
        jobs = s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
    for p in jobs:
        worker.HANDLERS["case.gateRecheck"](p)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def test_uc_06_lien_blocks_every_sale_channel():
    c = _car(3, _title(3, titleStatus="lien", liens=[LIEN]))
    gate = _gate(c, "G-VEH-TITLE")
    assert gate["passed"] is False and gate["hold"] is True and gate["missing"] == ["Lien release"]
    assert sorted(gate["routes"]) == sorted(CHANNELS)
    assert {r["id"] for r in c["routes"]} == set(CHANNELS)
    assert _failed(c) == dict.fromkeys(CHANNELS, f"{TITLE}: {TITLE}")  # all four channels: "<gate name>: <reason>"
    assert c["gateHold"] is not None and c["recommendation"] is None
    (item,) = _items(c["id"])
    assert (item["status"], item["owner_role"]) == ("open", "Approver")
    assert item["action"] == "Hold the car; customer care requests the lien release"


def test_uc_06_a_title_search_not_on_file_holds_the_car():
    _write("uc_lease", "lease_returns", _lease(7))
    c = _open(7)
    gate = _gate(c, "G-VEH-TITLE")
    assert gate["passed"] is False and gate["missing"] == ["Title and lien search"] and c["gateHold"] is not None
    assert len(_items(c["id"])) == 1


def test_uc_06_only_a_person_with_release_clears():
    c = _car(3, _title(3, titleStatus="lien", liens=[LIEN]))
    (item,) = _items(c["id"])
    # a person resolving it without the release is refused
    no = call("work.resolve", {"item_id": item["id"], "outcome": "Customer says it is paid"}, "approver")
    assert (
        no["ok"] is False and no["error"]["code"] == "evidence_missing" and no["error"]["message"] == "Lien release not on file"
    )
    assert _items(c["id"])[0]["status"] == "open"
    # an agent-prepared resolve is refused, with or without the release
    assert forbidden("work.resolve") and ACTIONS["work.resolve"].risk == "act"
    hdr = h("approver") | {"X-Circularity-Preparer": "coordinator", "X-Circularity-Confirmed": "true"}
    agent = client.post("/api/actions/work.resolve", json={"item_id": item["id"], "outcome": "Released"}, headers=hdr).json()
    assert agent["ok"] is False and agent["error"]["code"] != "evidence_missing"
    assert _items(c["id"])[0]["status"] == "open"
    # the release arrives: the gate passes, the car is released and the exception closes on its own
    _release()
    with SessionLocal() as s:
        queued = (
            s.execute(text("SELECT dedupe_key FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
        )
    assert queued == [f"case.gateRecheck:{vin_key(ORG, vin(3))}"]
    _recheck()
    got = _get(c["id"])
    assert _gate(got, "G-VEH-TITLE")["passed"] is True and got["gateHold"] is None
    (done,) = _items(c["id"])
    assert done["status"] == "done" and done["outcome"] == "Lien released (LR-000003)"
    assert got.get("approval") is None  # released, not approved: a person still decides
    assert _failed(got) == dict.fromkeys(CHANNELS)


def test_uc_06_a_person_resolves_once_the_release_is_on_file():
    c = _car(3, _title(3, titleStatus="lien", liens=[LIEN]))
    (item,) = _items(c["id"])
    _release()  # on file, the recheck job not yet run
    ok = call("work.resolve", {"item_id": item["id"], "outcome": "Lien released, title clear"}, "approver")
    assert ok.get("ok") is True, ok
    assert _items(c["id"])[0]["status"] == "done"


def test_uc_06_trade_in_payoff_unconfirmed_blocks():
    _write("uc_dms", "trade_ins", TRADE)
    c = _car(62, _title(62), "trade_in")
    gate = _gate(c, "G-VEH-TITLE")
    assert gate["passed"] is False and gate["reason"] == "Payoff of the customer's loan not confirmed"
    assert set(_failed(c).values()) == {f"{TITLE}: Payoff of the customer's loan not confirmed"}
    assert len(_items(c["id"])) == 1
    # the dealer confirms the payoff: the car is released
    _write("uc_dms", "trade_ins", TRADE | {"payoffConfirmed": True})
    _recheck()
    assert _gate(_get(c["id"]), "G-VEH-TITLE")["passed"] is True


def test_uc_06_clear_title_passes_and_a_confirmed_trade_in_passes():
    c = _car(1, _title(1))
    assert _gate(c, "G-VEH-TITLE")["passed"] is True and c.get("gateHold") is None and _items(c["id"]) == []
    assert _failed(c) == dict.fromkeys(CHANNELS)


def test_uc_24_brand_disclosed_on_every_route():
    c = _car(22, _title(22, brand="rebuilt", brandSource="national title database"))
    assert all(_route(c, r)["disclosures"] == ["Title brand: rebuilt"] for r in CHANNELS)
    gate = _gate(c, "G-VEH-BRAND")
    assert gate["passed"] is True and gate["kind"] == "disclose" and gate["reason"] == "Title brand: rebuilt"
    assert c.get("gateHold") is None and _failed(c) == dict.fromkeys(CHANNELS)  # a brand to disclose holds and excludes nothing


def test_uc_24_flood_brand_blocks_retail():
    c = _car(21, _title(21, brand="flood", brandSource="state title"))
    failed = _failed(c)
    assert failed["retail"] == "Title brand disclosed: Title brand flood: retail blocked by pack"
    assert [k for k, v in failed.items() if v is None] == ["auction", "dealer_trade", "salvage"]
    assert _route(c, "auction")["disclosures"] == ["Title brand: flood"] and _route(c, "retail")["disclosures"] == [
        "Title brand: flood"
    ]
    gate = _gate(c, "G-VEH-BRAND")
    assert gate["passed"] is False and gate["routes"] == ["retail"] and gate["hold"] is False


def test_uc_24_no_brand_no_disclosure():
    c = _car(1, _title(1))
    assert all("disclosures" not in r for r in c["routes"]) and "G-VEH-BRAND" not in [g["id"] for g in c["gates"]]


def test_uc_24_case_screen_carries_the_disclosures():
    c = _car(22, _title(22, brand="rebuilt"))
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    assert r.status_code == 200
    assert all(x["disclosures"] == ["Title brand: rebuilt"] for x in r.json()["case"]["routes"])


def test_uc_06_checks_are_pure_on_a_case_record():
    pack = load_pack("used_cars")
    at = "2026-10-07T09:00:00+00:00"

    def case(value: dict[str, Any] | None, brand: str | None = None) -> dict[str, Any]:
        recs = [{"type": "title_status", "source": "uc_title", "at": at, "result": "pass", "value": value}] if value else []
        if brand:
            recs.append({"type": "title_brand", "source": "uc_title", "at": at, "result": "pass", "value": {"brand": brand}})
        return {"cls": "car_ice", "evidenceRecords": recs} | ({"title": {"brand": brand}} if brand else {})

    clear = {"title_status": "clear", "lien_open": False}
    got = {r.gate_id: r for r in evaluate_gates(case(clear), pack)}
    assert got["G-VEH-TITLE"].passed
    for bad, why in (
        (clear | {"title_status": "lien", "lien_open": True}, TITLE),
        (clear | {"lien_open": True}, TITLE),
        (clear | {"return_kind": "trade_in", "payoff_confirmed": False}, "Payoff of the customer's loan not confirmed"),
        (clear | {"return_kind": "trade_in", "payoff_confirmed": None}, "Payoff of the customer's loan not confirmed"),
    ):
        r = {x.gate_id: x for x in evaluate_gates(case(bad), pack)}["G-VEH-TITLE"]
        assert (r.passed, r.reason, r.evidence_missing, r.effect.hold) == (False, why, ("lien_release",), True), bad
        assert set(r.effect.routes) == set(CHANNELS)
    none = {x.gate_id: x for x in evaluate_gates(case(None), pack)}["G-VEH-TITLE"]
    assert not none.passed and none.evidence_missing == ("title_status",)
    paid = {x.gate_id: x for x in evaluate_gates(case(clear | {"return_kind": "trade_in", "payoff_confirmed": True}), pack)}
    assert paid["G-VEH-TITLE"].passed
    # a brand outside both lists is not disclosed
    other = {x.gate_id: x for x in evaluate_gates(case(clear, "lemon"), pack)}["G-VEH-BRAND"]
    assert other.passed and other.disclosures == ()


def test_uc_24_disclosures_do_not_exclude_or_rank():
    routes = [{"id": "retail", "excluded": False}, {"id": "auction", "excluded": False}]
    res = GateResult(
        "G-VEH-BRAND", True, GateEffect("disclose", (), False, None), (), "Title brand: rebuilt", ("Title brand: rebuilt",)
    )
    apply_gate_results(routes, [res])  # type: ignore[arg-type]
    apply_disclosures(routes, [res, res])  # type: ignore[arg-type]
    assert all(r["excluded"] is False and r["disclosures"] == ["Title brand: rebuilt"] for r in routes)
    plain = [{"id": "retail", "excluded": False}]
    apply_disclosures(plain, [])  # type: ignore[arg-type]
    assert "disclosures" not in plain[0]
