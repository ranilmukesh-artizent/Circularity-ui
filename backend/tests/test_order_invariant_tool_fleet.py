"""P9-5.8 (R20, Review Focus 3, stories CR-02, CR-03 and CR-04) for a contract refresh the order is: the gates (GR-07 on the
contract, the safety recall check G-TOOL-REC on each tool), then the market's tool table, the like-life match, the pricing, and
the holds (GR-C1, GR-C2) last. A tool under an active replace recall is never kept nor matched as a like-life unit (a gate runs
before the table, whatever a lever says); an open charge on the contract blocks the proposal before any pricing. Every test
starts and ends with the demo reset."""

import pytest

from di.core.db import SessionLocal
from di.services.cases import store
from di.services.modeler.valuers import contract_refresh
from tests import refreshkit as rk
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def fresh():
    yield
    rk.forget()
    starting.reset()


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _panel(cid: str) -> dict:
    r = client.get(f"/api/screens/refresh/{cid}", headers=h("admin"))
    assert r.status_code == 200, r.text
    return r.json()


def _reeval(cid: str) -> None:
    rk.reeval(cid)


def test_order_invariant_refresh_recalled_tool_is_swapped_never_kept(monkeypatch):
    cid = rk.world(monkeypatch, only=["FC-30125"])["FC-30125"]
    assert {t["serial"]: t["action"] for t in _panel(cid)["tools"]}["CMH-R1"] == "keep"  # 30 months of 48: the table keeps it
    rk.notice(rk.REPLACE)
    _reeval(cid)
    tools = {t["serial"]: t for t in _panel(cid)["tools"]}
    assert tools["CMH-R1"]["action"] == "swap" and "RC-2026-P58" in tools["CMH-R1"]["reason"]  # the recall is named
    assert tools["CMH-R2"]["action"] == "keep"
    for levers in ({"swap_threshold": 10}, {"upgrades": False}, {"swap_threshold": 10, "upgrades": False}):
        out = call("refresh.whatIf", {"case_id": cid, **levers}, "admin")["output"]  # gate before the table: no lever keeps it
        assert out["split"]["swap"] >= 1 and all(x["serial"] != "CMH-R1" for x in out["changed"]), (levers, out)
    for route in _case(cid)["refreshProposal"].values():  # every route sends the tool away, even "renew as it is"
        line = next(x for x in route["lines"] if x["serial"] == "CMH-R1")
        assert line["action"] in ("swap", "upgrade"), (route["route"], line)


def test_order_invariant_refresh_recalled_unit_is_never_matched(monkeypatch):
    stock = dict(rk.STOCK_RUL)
    cid = rk.world(monkeypatch, stock=stock, only=["FC-30125"])["FC-30125"]
    rk.notice(rk.REPLACE)
    _reeval(cid)
    target = _panel(cid)["match"][0]["target"]
    stock["CMH-R1"] = int(target)  # the closest fit in stock, and the very serial the recall names
    first = _panel(cid)["match"][0]
    assert first["unit_id"] != "CMH-R1", first  # the gate comes before the like-life table
    rk.notice(rk.REPLACE | {"recall_id": "RC-2026-P59", "serial_from": "CMH-R9", "serial_to": "CMH-R9"})
    stock.pop("CMH-R1")
    stock["CMH-R9"] = int(target)
    assert _panel(cid)["match"][0]["unit_id"] != "CMH-R9"


def test_order_invariant_refresh_contract_gate_blocks_before_pricing(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("a blocked contract must not be priced")

    monkeypatch.setattr(contract_refresh, "price", boom)
    cid = rk.world(monkeypatch, only=["FC-30125"], charge_on="CMH-R2")["FC-30125"]  # damage charge DC-5801 is open
    c = _case(cid)
    assert c["routes"] == [] and c.get("recommendation") is None and not c.get("refreshProposal")
    assert "G-CON-2" in str(c.get("refreshBlock")) and "DC-5801" in str(c.get("refreshBlock"))
    assert _panel(cid)["pricing"] is None
    out = call("refresh.whatIf", {"case_id": cid, "swap_threshold": 40}, "admin")
    assert out["ok"] is False and out["error"]["code"] == "not_found"


def test_order_invariant_refresh_holds_come_last(monkeypatch):
    cid = rk.world(monkeypatch, only=["FC-30125"])["FC-30125"]
    rk.notice(rk.REPLACE)
    _reeval(cid)
    c = _case(cid)
    assert [x["id"] for x in c["approvalHolds"]] == ["GR-C2"]  # priced with the recalled tool swapped, then held for a person
    best = c["recommendation"]["id"]
    assert c["routes"] and best and c["refreshProposal"][best]
    rk.forget()
    blocked = rk.world(monkeypatch, only=["FC-30125"], charge_on="CMH-R2")["FC-30125"]
    assert not _case(blocked).get("approvalHolds")  # a gate that blocks leaves nothing to hold
