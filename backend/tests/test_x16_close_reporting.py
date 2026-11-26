"""Plan 9, P9-13.5 (story X-16): a case of a pack that names reporting gates closes only with the facility's evidence.

G-REP-2 (a recycle or exit route) needs a treatment code, G-REP-1 (an org unit flagged `csrd_scope`) needs mass and material.
Without them the last acknowledgement leaves the case `executing`, the last step `waiting_evidence` and one `reporting_evidence`
item; `case.attachReporting` closes it. The spec's medical-rental recycle case is a used-car salvage case here (the sample cars
of `ucfixtures` are the cheapest way to a recycle route with the stubbed clients; the pack rule is the same for every pack).
The clients are stubbed: nothing calls the shared source-sim. Compliance text: pending review by Kinective's Legal team.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal
from di.services.actions import reporting as act
from di.services.execution import reporting
from di.services.instructions import queue, send, writers
from di.services.modeler.pack import PackClose, load_pack, pack_keys
from tests import ucfixtures as uc
from tests.helpers import call
from tests.test_uc_follow_through import Stub as UcStub
from tests.test_uc_follow_through import _approve, _open, _run
from tests.test_x13_asset_retirement import Stub

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    uc.start()
    Stub.calls, Stub.docs = [], {}
    UcStub.calls = Stub.calls
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    monkeypatch.setattr(queue, "enabled", lambda: True)
    monkeypatch.setattr(send, "_refusal", lambda *a: None)
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item WHERE type IN ('used_car_follow_through', 'reporting_evidence')"))
        s.commit()
    uc.finish()


def _csrd(on: bool = True) -> None:
    with SessionLocal() as s:
        state.put(s, act.COLLECTION, uc.ORG, {"csrd_scope": on})
        s.commit()


def _items(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = "SELECT type, status, owner_role FROM work_item WHERE case_id = :c AND type = 'reporting_evidence' ORDER BY id"
        return [dict(r) for r in s.execute(text(q), {"c": cid}).mappings()]


def _salvage_done() -> dict[str, Any]:
    c = _open(8, buyer="SB-1")
    done = _approve(c)
    _run(c["id"], len(done["exec"]["steps"]))
    return uc.get(c["id"])


def _attach(cid: str, **over: Any) -> dict[str, Any]:
    body = {"case_id": cid, "mass_kg": 42.5, "material": "steel", "treatment_code": "R4", "source_ref": "FAC-77"} | over
    return call("case.attachReporting", body, "admin")


def test_x_16_close_blocked_without_reporting_evidence():
    c = _salvage_done()
    assert c["stage"] == "executing" and c["exec"]["steps"][-1]["state"] == "waiting_evidence"
    assert "treatment code (G-REP-2)" in c["exec"]["steps"][-1]["waiting"]
    ((item),) = _items(c["id"])
    assert item["status"] == "open"


def test_x_16_close_when_evidence_arrives():
    c = _salvage_done()
    r = _attach(c["id"])
    assert r["ok"], r
    after = uc.get(c["id"])
    assert after["stage"] == "closed" and after["exec"]["steps"][-1]["state"] == "done"
    with SessionLocal() as s:
        why = s.execute(
            text("SELECT reason FROM case_stage_log WHERE case_id = :c AND to_stage = 'closed'"), {"c": c["id"]}
        ).scalar()
    assert why == "Reporting evidence received (FAC-77)"
    assert [i["status"] for i in _items(c["id"])] == ["done"]


def test_x_16_treatment_code_pattern():
    c = _salvage_done()
    r = _attach(c["id"], treatment_code="X9")
    assert not r["ok"] and r["error"]["code"] == "validation_error"
    assert uc.get(c["id"])["stage"] == "executing"
    assert _attach(c["id"], treatment_code="D10")["ok"]


def test_x_16_csrd_scope_requires_mass_and_material():
    _csrd()
    c = _open(1)  # a retail route: G-REP-2 does not apply
    _approve(c)
    _run(c["id"], 4)
    after = uc.get(c["id"])
    assert after["stage"] == "executing"
    w = after["exec"]["steps"][-1]["waiting"]
    assert "mass in kilograms (G-REP-1)" in w and "material (G-REP-1)" in w and "treatment code" not in w
    assert _attach(c["id"])["ok"] and uc.get(c["id"])["stage"] == "closed"


def test_x_16_no_reporting_gate_closes_as_before():
    c = _open(1)  # a retail route, no csrd_scope on the org
    _approve(c)
    _run(c["id"], 4)
    assert uc.get(c["id"])["stage"] == "closed" and not _items(c["id"])
    pack = load_pack("used_cars").model_copy(update={"close": PackClose()})
    assert reporting.close_check({"chosen": {"id": "salvage"}}, pack, {"csrd_scope": True}) == []


def test_x_16_industrial_close_unchanged():
    assert load_pack("industrial").close.reporting == []
    for key in pack_keys():
        assert all(g in ("G-REP-1", "G-REP-2") for g in load_pack(key).close.reporting)
    with SessionLocal() as s:
        assert act.reporting_missing(s, {"id": "RT-1048", "template": "industrial", "owner": "Customer A"}) == []
        assert act.reporting_missing(s, {"id": "RT-1048"}) == []
