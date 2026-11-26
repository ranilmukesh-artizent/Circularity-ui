"""P9-13.6 (story NS-CORE-02): the core's credit follows its acceptance and is matched against the ERP.

The accepted core's credit is the deposit times the acceptance share (`core_credit`, P9-12.8: full 100 %, partial 50 %, none 0).
It is posted by the X-16 settlement (writer `credit`, di.services.execution.settlement), a Finance-owned step: nothing posts
until the step is sent, and an agent can never resolve a mismatch (`settlement.resolve` is forbidden to agents). The posted
amount read back from the ERP is compared with the case amount; a difference opens one I-20 item for Finance and keeps the case
`executing`. The ERP client is stubbed (the shared source-sim is not called). Synthetic data. Credit terms are commercial and
need review by Kinective's Legal team before they are relied on.
"""

import json
from decimal import Decimal
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import store
from di.services.execution import settlement
from di.services.execution.steps import close_kinds
from di.services.instructions import writers
from di.services.modeler.pack import load_pack
from tests.test_ns_core import CRACKED, FULL, PARTIAL, _core, _open, fresh  # noqa: F401 - `fresh` is the fixture

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

PACK = "auto_core"


def _case(core: dict[str, Any]) -> dict[str, Any]:
    return {"id": "CORE-X", "template": PACK, "customer": "Dealer D-02", "core": core, "exec": {"ref": "APR-9"}}


def test_ns_core_02_credit_from_acceptance():
    pack = load_pack(PACK)
    assert pack.close.credit_settlement and close_kinds(pack, {"id": "reman"}) == ["credit"]
    partial = settlement.credit_amount(_case(PARTIAL | {"deposit": 180}), pack)
    assert partial is not None and partial.amount == Decimal("90.00") and partial.basis == "core_acceptance"
    full = settlement.credit_amount(_case(FULL | {"deposit": 180}), pack)
    assert full is not None and full.amount == Decimal("180.00")
    none = settlement.credit_amount(_case(CRACKED | {"deposit": 180}), pack)
    assert none is not None and none.amount == Decimal("0.00")
    assert settlement.credit_amount({"id": "x", "template": PACK}, pack) is None  # no core: nothing is assumed


class Stub:
    posted: ClassVar[list[dict[str, Any]]] = []
    erp_amount: float | None = None

    def __init__(self, source_id: str):
        self.source_id = source_id

    def request(self, method, path, json=None, headers=None):
        Stub.posted.append(json)
        amount = Stub.erp_amount if Stub.erp_amount is not None else json["amount"]
        return type("R", (), {"json": lambda self: {"creditMemo": "CM-0001", "amount": amount, "currency": json["currency"]}})()

    def close(self):
        pass


def test_ns_core_02_posts_the_partial_credit(fresh, monkeypatch):  # noqa: F811
    Stub.posted, Stub.erp_amount = [], None
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    cid = _open("CORE-AST-1", PARTIAL | {"deposit": 180})
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        c["exec"] = {"ref": "APR-9"}
        sent = writers.credit(s, {"idem_key": "k1"}, c, {})
    assert Stub.posted[0]["amount"] == 90.0 and sent.detail["credit"]["erp_amount"] == 90.0
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None and "credit" not in (c.get("finance") or {})  # sending is not matching: record() does that


def test_ns_core_02_a_core_with_no_credit_posts_nothing(fresh, monkeypatch):  # noqa: F811
    Stub.posted = []
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    cid = _open("CORE-AST-2", CRACKED | {"deposit": 180})
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        c["exec"] = {"ref": "APR-9"}
        with pytest.raises(writers.NotApplicable):
            writers.credit(s, {"idem_key": "k2"}, c, {})
    assert Stub.posted == []


def test_ns_core_02_erp_mismatch_opens_exception(fresh):  # noqa: F811
    cid = _open("CORE-AST-3", PARTIAL | {"deposit": 180})
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        c["exec"] = {"ref": "APR-9"}
        got = {"memo": "CM-0001", "amount": 90.0, "erp_amount": 80.0, "currency": "USD", "basis": "core_acceptance"}
        s.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, detail, status) "
                "VALUES (:c, 'APR-9', 0, 'credit', 'erp', 'k3', '[]'::jsonb, CAST(:d AS jsonb), 'acknowledged')"
            ),
            {"c": cid, "d": json.dumps({"credit": got})},
        )
        assert settlement.record(s, c, 0) is False
        assert settlement.waiting(c)
        assert settlement.record(s, c, 0) is False  # a second look opens no second item
        rows = s.execute(
            text("SELECT owner_role, cause FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"),
            {"c": cid, "t": settlement.EXCEPTION},
        ).all()
        s.rollback()
    assert len(rows) == 1 and rows[0][0] == "Finance" and "90.00" in rows[0][1] and "80.00" in rows[0][1]


def test_ns_core_02_agent_cannot_resolve():
    from di.services.agents.forbidden import forbidden

    assert forbidden("settlement.resolve")  # a person at Finance accepts the ERP's amount or sends the credit again
