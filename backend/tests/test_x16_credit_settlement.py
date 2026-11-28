"""Plan 9, P9-13.4 (story X-16): a trade-in or upgrade credit is posted to the customer in the ERP and matched against what the
case decided. A credit that differs stays with Finance (an I-20 item) and the case stays `executing` until Finance accepts the
ERP's amount or sends the credit again. The industrial demo is untouched (no pack of it has `close.credit_settlement`).

The ERP client is stubbed here: nothing calls the shared source-sim (`source-sim/tests/test_s4_billing.py` tests the mock). The
used-car pack stands in for a pack with `close.credit_settlement` through an org version of it that switches the setting on.
"""

import copy
import json
from decimal import Decimal
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.cases import store
from di.services.execution import settlement
from di.services.execution.steps import STEP_TPL, close_kinds, ex_kinds
from di.services.instructions import queue, send, writers
from di.services.modeler.pack import load_pack, pack_keys
from tests import ucfixtures as uc
from tests.helpers import call, client, h
from tests.test_uc_follow_through import Stub as UcStub
from tests.test_uc_follow_through import _approve, _open, _run
from tests.test_x13_asset_retirement import Stub as AssetStub

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

TABLE = {"A": 100, "B": 80, "C": 55, "D": 20}
NOTE = "Checked the credit memo in the ERP."


class Stub(AssetStub):
    """The ERP's credit memo service on top of the asset stub: one memo per external reference, the posted amount the one asked
    unless `erp_amount` says the ERP posts another."""

    memos: ClassVar[dict[str, dict[str, Any]]] = {}
    erp_amount: ClassVar[float | None] = None

    def request(self, method, path, json=None, headers=None):
        if not path.endswith("creditmemo"):
            return super().request(method, path, json, headers)
        UcStub.calls.append(("creditmemo", json, headers or {}))
        ref = json["externalReference"]
        if ref not in Stub.memos:
            amount = Stub.erp_amount if Stub.erp_amount is not None else json["amount"]
            Stub.memos[ref] = {"creditMemo": f"CM-{len(Stub.memos) + 1:04d}", "amount": amount, "currency": json["currency"]}
        return type("R", (), {"json": lambda self: Stub.memos[ref]})()


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    doc = copy.deepcopy(json.loads(uc.PACK.read_text(encoding="utf-8")))
    doc["close"] = {**doc.get("close", {}), "credit_settlement": True, "credit_table": TABLE}
    patched = tmp_path / "used_cars.json"
    patched.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(uc, "PACK", patched)
    uc.start()
    Stub.calls, Stub.docs, Stub.memos, Stub.erp_amount = [], {}, {}, None
    UcStub.calls = Stub.calls
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    monkeypatch.setattr(queue, "enabled", lambda: True)
    monkeypatch.setattr(send, "_refusal", lambda *a: None)
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item WHERE type IN ('used_car_follow_through', :t)"), {"t": settlement.EXCEPTION})
        s.commit()
    uc.finish()


def _priced(n: int = 1) -> dict[str, Any]:
    """A used-car case approved with a trade-in on it: quote 200.00, declared A, received B."""
    c = _open(n)
    with SessionLocal() as s:
        row = store.get(s, c["id"], for_update=True)
        row |= {"quote": {"amount": 200.0, "currency": "USD"}, "declared_grade": "A", "received_grade": "B"}
        store.save(s, row)
        s.commit()
    return _approve(c)


def _memos() -> list[dict[str, Any]]:
    return [c[1] for c in Stub.calls if c[0] == "creditmemo"]


def test_x_16_credit_memo_from_decision_and_grade():
    done = _priced()
    kinds = [s["k"] for s in done["exec"]["steps"]]
    assert kinds[-2:] == ["retire", "credit"]
    _run(done["id"], 5)
    (body,) = _memos()
    assert body["amount"] == 160.0 and body["externalReference"] == done["exec"]["ref"]
    after = uc.get(done["id"])
    credit = after["finance"]["credit"]
    assert credit["amount"] == 160.0 and credit["erp_amount"] == 160.0 and credit["basis"] == "grade_table"
    assert credit["memo"].startswith("CM-") and after["stage"] == "closed"


def test_x_16_requote_used_when_present():
    pack = load_pack("device")
    assert pack.close.credit_settlement and pack.close.credit_table == TABLE
    case = {
        "valuer": {"imei": "35-1", "quote": {"amount": 200.0, "currency": "USD"}, "declared_grade": "A"},
        "payout": {"status": "adjusted", "quote": 200.0, "adjusted": 185.0, "table": "US payout rules v1"},
    }
    got = settlement.credit_amount(case, pack)
    assert got is not None and got.amount == Decimal("185.00") and got.basis == "requote"
    assert got.quote == Decimal("200.00") and got.requote_ref == "US payout rules v1"
    assert settlement.credit_amount({"valuer": {"imei": "35-1"}}, pack) is None  # no quote: nothing is assumed
    assert settlement.credit_amount(case, load_pack("industrial")) is None  # the pack has no credit settlement


def test_x_16_erp_mismatch_opens_exception():
    Stub.erp_amount = 150.0
    done = _priced()
    _run(done["id"], 5)
    after = uc.get(done["id"])
    assert after["stage"] == "executing" and after["finance"]["credit"]["status"] == "mismatch"
    with SessionLocal() as s:
        items = s.execute(
            text("SELECT owner_role, cause, action FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"),
            {"c": done["id"], "t": settlement.EXCEPTION},
        ).all()
    assert len(items) == 1 and items[0][0] == "Finance"
    assert "160.00" in items[0][1] and "150.00" in items[0][1] and "CM-" in items[0][1]
    assert items[0][2] == "Check the credit memo in the ERP; accept the ERP amount or send the credit again."


def test_x_16_resolve_accept_erp_closes():
    Stub.erp_amount = 150.0
    done = _priced()
    _run(done["id"], 5)
    short = call("settlement.resolve", {"case_id": done["id"], "resolution": "accept_erp", "note": "short"}, "finance")
    assert short["ok"] is False  # a note of at least 15 characters
    r = call("settlement.resolve", {"case_id": done["id"], "resolution": "accept_erp", "note": NOTE}, "finance")
    assert r["ok"], r
    after = uc.get(done["id"])
    assert after["finance"]["credit"]["realised"] == 150.0 and after["finance"]["credit"]["status"] == "accepted"
    assert after["stage"] == "closed"
    with SessionLocal() as s:
        assert not s.execute(
            text("SELECT 1 FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"),
            {"c": done["id"], "t": settlement.EXCEPTION},
        ).first()
    again = call("settlement.resolve", {"case_id": done["id"], "resolution": "accept_erp", "note": NOTE}, "finance")
    assert again["ok"] is False  # nothing is waiting any more


def test_p9_13_14_f2_accept_erp_keeps_reporting_check():
    """Review 13 F2 (X-16): accepting the ERP's amount closes only with the reporting evidence, as the last acknowledgement
    does. The org is in CSRD scope (G-REP-1) and nothing was attached: the case stays executing and waits for the evidence.
    To be reviewed by Kinective's Legal team before it is relied on."""
    from di.core import state
    from di.services.actions import reporting as rep

    Stub.erp_amount = 150.0
    with SessionLocal() as s:
        state.put(s, rep.COLLECTION, uc.ORG, {"csrd_scope": True})
        s.commit()
    try:
        done = _priced()
        _run(done["id"], 5)
        r = call("settlement.resolve", {"case_id": done["id"], "resolution": "accept_erp", "note": NOTE}, "finance")
        assert r["ok"], r
        after = uc.get(done["id"])
        assert after["finance"]["credit"]["status"] == "accepted"
        assert after["stage"] == "executing", after["stage"]
        assert after["exec"]["steps"][-1]["state"] == rep.WAITING
        assert "mass in kilograms (G-REP-1)" in after["exec"]["steps"][-1]["waiting"]
        body = {"case_id": done["id"], "mass_kg": 1.4, "material": "steel", "treatment_code": "R4", "source_ref": "FAC-1"}
        assert call("case.attachReporting", body, "admin")["ok"]
        assert uc.get(done["id"])["stage"] == "closed"
    finally:
        with SessionLocal() as s:
            state.put(s, rep.COLLECTION, uc.ORG, {"csrd_scope": False})
            s.execute(text("DELETE FROM work_item WHERE type = :t"), {"t": rep.TYPE})
            s.commit()


def test_x_16_resend_posts_under_the_same_key():
    Stub.erp_amount = 150.0
    done = _priced()
    _run(done["id"], 5)
    r = call("settlement.resolve", {"case_id": done["id"], "resolution": "resend", "note": NOTE}, "finance")
    assert r["ok"], r
    assert len(Stub.memos) == 1  # the ERP answers its first memo for the same reference
    assert uc.get(done["id"])["stage"] == "executing"


def test_x_16_agent_cannot_resolve_settlement():
    assert "settlement.resolve" in FORBIDDEN_ACTIONS and forbidden("settlement.resolve")
    Stub.erp_amount = 150.0
    done = _priced()
    _run(done["id"], 5)
    r = client.post(
        "/api/actions/settlement.resolve", json={"case_id": done["id"], "resolution": "accept_erp", "note": NOTE},
        headers=h("finance") | {"X-Circularity-Preparer": "gap", "X-Circularity-Confirmed": "true"},
    ).json()  # fmt: skip
    assert r["ok"] is False and r["error"]["code"] == "approval_required"
    assert uc.get(done["id"])["stage"] == "executing"


def test_x_16_industrial_unchanged():
    assert not load_pack("industrial").close.credit_settlement
    for rid in ("redeploy", "resale", "relase", "intparts", "extparts", "material", "exit", "hold"):
        assert "credit" not in ex_kinds({"id": rid}) and "credit" not in STEP_TPL[rid]
    for key in pack_keys():
        pack = load_pack(key)
        if key in ("industrial", "used_cars", "telecom_network", "medical_rental"):
            assert not pack.close.credit_settlement and all("credit" not in close_kinds(pack, {"id": r.id}) for r in pack.routes)
