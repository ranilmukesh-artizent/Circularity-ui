"""P9-12.5 (stories NS-RC-02, NS-RC-03): the rental fleet's damage recovery at close and its cross-branch transfer alert.

`close_rental_fleet.close_case` turns a check-in damage claim of at least the pack's `close.damage_charge_min` into an
agent-prepared customer charge (renter reference, amount, photos reference), held for Finance as a proposal (`proposal.accept`
is a person's, never an agent's). `AL-RF-XBRANCH`: a machine idle more than 30 days at one branch while another branch plans a
purchase of its class: an alert for the branch manager with a `transfer_branch` suggestion. Synthetic data throughout.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import held_for_person
from di.services.canonical import store as canonical
from di.services.canonical.schema import serial_key
from di.services.cases import close_rental_fleet as close
from di.services.cases import store as cases
from di.services.modeler.pack import load_pack
from tests import flowkit, starting
from tests.helpers import call
from tests.test_ns_rc_valuation import case_of

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
PACK_FILE = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "rental_fleet.json"


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        for like in (f"{ORG}:M-9%", f"{ORG}:M-0005"):
            conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": like})
            conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": like})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK_FILE.read_text(encoding="utf-8")))
    doc["version"] = "1.9.5"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        extra.register(s, "rf_rental", ORG)
        s.commit()
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _machine(mid: str, cls: str, branch: str, idle: int | None, plans: list | None = None, claims: list | None = None) -> None:
    row = {"machineId": mid, "assetClass": cls, "hours": 3000, "branch": branch, "ageYears": 4, "bookValue": 40000,
           "org_unit_id": ORG, "utilisation": 0.5, "price": 50000, "claims": claims or [], "plans": plans or [],
           "idleDays": idle}  # fmt: skip
    with SessionLocal() as s:
        canonical.apply(s, "rf_rental", ADAPTERS["rf_rental"].map(Record("machines", mid, row)))
        s.commit()


def _held(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT id, agent, action, status, input FROM agent_proposal WHERE case_id = :c ORDER BY id"), {"c": cid}
        )
        return [dict(r._mapping) for r in rows]


def _approved_case(sample: str, mid: str) -> str:
    """The sample's machine opened as a case and approved (the close reads an approved route)."""
    body = {"org_unit_id": ORG, "template_key": "rental_fleet", "asset_key": serial_key(ORG, mid), "reason": "rental_return",
            "facts": case_of(sample)}  # fmt: skip
    cid = _ok(call("case.open", body, "planner-a"))["case_id"]
    with SessionLocal() as s:
        c = cases.get(s, cid, for_update=True)
        assert c is not None
        c["exec"], c["chosen"] = {"ref": "APR-T-1", "steps": []}, {"id": "rerent"}
        cases.save(s, c)
        s.commit()
    return cid


def _close(cid: str) -> close.CloseResult:
    with SessionLocal() as s:
        r = close.close_case(s, cid)
        s.commit()
    return r


CLAIM = {"claimId": "DC-1", "renterRef": "R-0042", "amount": 2350, "photosRef": "PH-DC-1"}


def test_ns_rc_02_damage_claim_to_finance():
    _machine("M-0005", "telehandler", "BR-2", 5, claims=[CLAIM])
    cid = _approved_case("RF-S5", "M-0005")
    r = _close(cid)
    assert r.status == "closed" and [p["state"] for p in r.posts] == ["held"]
    (p,) = _held(cid)
    assert p["action"] == close.ACTION and p["status"] == "pending" and p["agent"] == close.AGENT
    assert p["input"]["amount"] == 2350.0 and p["input"]["renter_ref"] == "R-0042" and p["input"]["photos_ref"] == "PH-DC-1"
    assert p["input"]["claim_id"] == "DC-1" and p["input"]["case_id"] == cid
    assert len(_held(cid)) == 1 and [x["state"] for x in _close(cid).posts] == ["exists"]  # a second close asks nothing new
    assert held_for_person(close.ACTION)


def test_ns_rc_02_a_person_accepts_and_the_charge_is_recorded():
    _machine("M-0005", "telehandler", "BR-2", 5, claims=[CLAIM])
    cid = _approved_case("RF-S5", "M-0005")
    _close(cid)
    (p,) = _held(cid)
    _ok(call("proposal.accept", {"id": p["id"]}, "admin"))
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    posted = c["close"]["posted"]["damage_charge:DC-1"]
    assert (posted["amount"], posted["renter_ref"], posted["photos_ref"]) == (2350.0, "R-0042", "PH-DC-1")


def test_ns_rc_02_a_claim_under_the_minimum_is_not_charged():
    assert load_pack("rental_fleet").close.damage_charge_min == 100
    _machine("M-0005", "telehandler", "BR-2", 5, claims=[{**CLAIM, "amount": 99.5}])
    cid = _approved_case("RF-S5", "M-0005")
    r = _close(cid)
    assert r.status == "closed" and r.posts == [] and _held(cid) == []


def test_ns_rc_02_close_leaves_other_cases_alone():
    with SessionLocal() as s:
        assert close.close_case(s, "C-NONE").status == "not_applicable"


def _plan(branch: str, cls: str = "wheel_loader", qty: int = 1) -> dict[str, Any]:
    return {"branch": branch, "assetClass": cls, "qty": qty}


def _alerts() -> list[close.Alert]:
    with SessionLocal() as s:
        return close.alerts_for(s, [ORG], load_pack("rental_fleet"))


def test_ns_rc_03_idle_machine_transfer_suggested():
    _machine("M-9001", "wheel_loader", "BR-2", 44, plans=[_plan("BR-3")])
    (a,) = _alerts()
    assert (a.id, a.to_role, a.branch, a.to_branch) == ("AL-RF-XBRANCH", "Planner", "BR-2", "BR-3")
    assert a.text == "1 idle wheel_loader at BR-2; BR-3 plans to buy" and a.action == "Transfer to the branch buying new"
    assert [(t["machine_id"], t["route"], t["from"], t["to"], t["idle_days"]) for t in a.transfers] == [
        ("M-9001", "transfer_branch", "BR-2", "BR-3", 44)
    ]
    sug = close.rule_suggestion(load_pack("rental_fleet"))
    assert sug is not None and sug["id"] == "SR-RF-XBRANCH" and sug["rule"]["path"] == "transfer_branch"


def test_ns_rc_03_no_alert_without_idle_days_or_a_plan():
    _machine("M-9001", "wheel_loader", "BR-2", 30, plans=[_plan("BR-3")])  # 30 days is not more than 30
    _machine("M-9002", "wheel_loader", "BR-2", 60)  # no purchase plan elsewhere
    _machine("M-9003", "scissor_lift", "BR-2", 60, plans=[_plan("BR-3", "wheel_loader")])  # the plan is for another class
    assert _alerts() == []
