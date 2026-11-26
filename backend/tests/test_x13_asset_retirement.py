"""Plan 9, P9-13.1 (story X-13): a pack that owns its fixed assets retires or transfers the asset in the ERP when an approved
route closes. The platform sends the posting and stores the ERP's gain or loss; it never computes it. The industrial demo,
the tool fleet and the device pack are untouched (`close.fixed_asset` is off for them).

The ERP client is stubbed here: nothing calls the shared source-sim (`source-sim/tests/test_s4_assets.py` tests the mock).
"""

from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.execution.steps import STEP_TPL, close_kinds, ex_kinds
from di.services.instructions import queue, send, writers
from di.services.modeler.pack import load_pack, pack_keys
from tests import ucfixtures as uc
from tests.test_uc_follow_through import Stub as UcStub
from tests.test_uc_follow_through import _approve, _open, _rows, _run

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

BOOK = 18000


class Stub(UcStub):
    """The dealer-system stub of the used-car tests, plus the ERP's fixed-asset services: a retirement answers the proceeds
    against the book value with the gain or loss as the ERP computes it; one document per external reference."""

    docs: ClassVar[dict[str, dict[str, Any]]] = {}

    def request(self, method, path, json=None, headers=None):
        if "fixedasset" not in path:
            return super().request(method, path, json, headers)
        UcStub.calls.append((path.rsplit("/", 1)[1], json, headers or {}))
        ref = json["externalReference"]
        if ref not in Stub.docs:
            doc = {"assetDocument": f"FA-{len(Stub.docs) + 1:04d}", "assetNumber": "100001", "postingDate": "2026-10-20"}
            if path.endswith("fixedassetretirement"):
                doc |= {"proceeds": json["proceeds"], "bookValue": BOOK, "gainLoss": json["proceeds"] - BOOK, "currency": "USD"}
            else:
                doc |= {"toLocation": json["toLocation"]}
            Stub.docs[ref] = doc
        return type("R", (), {"json": lambda self: Stub.docs[ref]})()


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
        s.execute(text("DELETE FROM work_item WHERE type = 'used_car_follow_through'"))
        s.commit()
    uc.finish()


def _retire_calls() -> list[tuple[str, dict[str, Any], dict[str, str]]]:
    return [c for c in Stub.calls if c[0] in ("fixedassetretirement", "fixedassettransfer")]


def test_x_13_resale_triggers_retirement_with_proceeds():
    c = _open(1)
    sale = sum(t["amt"] for t in c["recommendation"]["terms"] if t["kind"] == "sale")
    done = _approve(c)
    kinds = [s["k"] for s in done["exec"]["steps"]]
    assert kinds == ["recon_order", "lot_transfer", "listing", "retire"]
    _run(c["id"], 4)
    ((kind, body, hdr),) = _retire_calls()
    assert kind == "fixedassetretirement" and body["proceeds"] == sale
    assert body["externalReference"] == done["exec"]["ref"] and hdr["Idempotency-Key"].endswith(".3.retire")


def test_x_13_salvage_and_retire_trigger_retirement():
    pack = load_pack("used_cars")
    assert close_kinds(pack, {"id": "salvage"}) == ["retire"] and close_kinds(pack, {"id": "auction"}) == ["retire"]
    assert close_kinds(load_pack("medical_rental"), {"id": "retire:REQ-1"}) == ["retire"]
    assert close_kinds(load_pack("medical_rental"), {"id": "refurbish"}) == []  # the asset stays on the books


def test_x_13_redeploy_triggers_transfer():
    pack = load_pack("telecom_network")
    assert close_kinds(pack, {"id": "redeploy:SITE-3"}) == ["transfer"]
    assert close_kinds(pack, {"id": "resell"}) == ["retire"] and close_kinds(pack, {"id": "spare"}) == []
    c = {
        "id": "RT-1",
        "assetId": "tn:SN-0001",
        "serial": "SN-0001",
        "exec": {"ref": "APR-1"},
        "chosen": {"dest": {"site": "SITE-3"}},
    }
    ins = {"idem_key": "APR-1.2.transfer", "approval_ref": "APR-1", "step": 2, "kind": "transfer"}
    with SessionLocal() as s:
        sent = writers.WRITERS["transfer"](s, ins, c, {})
    ((_, body, _),) = _retire_calls()
    assert body["toLocation"] == "SITE-3" and sent.detail["asset"]["kind"] == "transfer"


def test_x_13_erp_gain_loss_stored():
    c = _open(1)
    done = _approve(c)
    _run(c["id"], 4)
    after = uc.get(c["id"])
    a = after["finance"]["asset"]
    assert a["kind"] == "retire" and a["doc"].startswith("FA-") and a["currency"] == "USD"
    assert a["book_value"] == BOOK and a["gain_loss"] == a["proceeds"] - BOOK  # the ERP's answer, stored as given
    assert after["stage"] == "closed" and after["exec"]["ref"] == done["exec"]["ref"]


def test_x_13_retirement_idempotent_on_resend():
    c = _open(1)
    _approve(c)
    _run(c["id"], 4)
    row = next(r for r in _rows(c["id"]) if r["kind"] == "retire")
    first = dict(Stub.docs)
    assert send.send(row["id"], resend=True) in ("sent", "skipped")
    assert Stub.docs == first and len(Stub.docs) == 1  # the same external reference answers the first document


def test_x_13_industrial_plan_unchanged():
    for rid, tpl in STEP_TPL.items():
        kinds = ex_kinds({"id": rid})
        assert kinds == tpl or rid == "resale"
        assert "retire" not in kinds and "transfer" not in kinds
    assert not load_pack("industrial").close.fixed_asset


def test_x_13_tool_fleet_and_device_unaffected():
    for key in pack_keys():
        pack = load_pack(key)
        if key in ("tool_fleet", "device", "industrial"):
            assert not pack.close.fixed_asset
            assert all(close_kinds(pack, {"id": r.id}) == [] and r.asset_effect == "none" for r in pack.routes)
