"""Plan 9, P9-9.17 (stories UC-18 and UC-25): an approved used-car decision is followed through per channel.

On a person's approval the route's steps (the pack's route instructions, part 5) go to the dealer system (`uc_dms`: retail
`recon_order`, `lot_transfer`, `listing`; dealer trade `dealer_trade`) or the auction platform (`uc_auction`: `consignment`,
`salvage_sale`), strictly in order. The clients are stubbed here: nothing calls the shared source-sim. A salvage sale to a buyer
that does not report to the national title database is refused by the gate (G-VEH-SALV) and by the writer. A route that is not
confirmed within its lead days reminds its owner in My work (I-20). A car with paired devices gets a person's checklist step
first (UC-25). Agents never approve (`decision.approve` is in forbidden.py).
Legal note: G-VEH-SALV and the infotainment step rest on research summaries; Kinective's Legal team reviews them before use.
"""

from datetime import timedelta
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.connectors.http import SourceError
from di.core import clock
from di.core.db import SessionLocal
from di.services.agents import chain
from di.services.cases import process
from di.services.instructions import follow_through, queue, send, writers
from di.services.modeler.gate_checks.vehicle import check_salvage_reporting
from di.services.modeler.gates import GateDef, catalogue
from di.services.modeler.pack import load_pack
from tests import ucfixtures as uc
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

REASON = "Salvage buyer must report to the national title database"
BUYERS = {"SB-1": True, "SB-2": False}


class _Reply:
    def __init__(self, doc: dict[str, Any]):
        self._doc = doc

    def json(self) -> dict[str, Any]:
        return self._doc


class Stub:
    """A source client that records its writes and answers like the mocks (a document with its id; 422 for a buyer that does not
    report)."""

    calls: ClassVar[list[tuple[str, dict[str, Any], dict[str, str]]]] = []
    ids: ClassVar[dict[str, str]] = {
        "recon-orders": "orderId", "transfers": "transferId", "listings": "listingId", "dealer-trades": "dealerTradeId",
        "consignments": "consignmentId", "salvage-sales": "salvageSaleId",
    }  # fmt: skip

    def __init__(self, source: str):
        self.source = source

    def request(self, method: str, path: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        assert method == "POST" and json is not None
        kind = path.rsplit("/", 1)[1]
        if kind == "salvage-sales" and not BUYERS.get(json["buyerId"]):
            raise SourceError("client", "buyer_not_reporting", 422)
        Stub.calls.append((kind, json, headers or {}))
        return _Reply({self.ids[kind]: f"{kind[:3].upper()}-{len(Stub.calls):04d}", **json})

    def get_json(self, path: str, params: dict[str, Any] | None = None):
        assert path.endswith("/partner-bids")
        return {"items": [{"partner": "Partner A", "amount": 20900}, {"partner": "Partner B", "amount": 21300}]}

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    uc.start()
    Stub.calls = []
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    monkeypatch.setattr(queue, "enabled", lambda: True)
    monkeypatch.setattr(send, "_refusal", lambda *a: None)  # the sources' access is the Phase 0 rule's, not this task's
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item WHERE type = :t"), {"t": follow_through.TYPE})
        s.commit()
    uc.finish()


def _open(n: int, like: int | None = None, buyer: str | None = None, brand: str | None = None, paired: bool = False, **over: Any):
    """Sample UC-S<n> on file and opened as a case; `buyer` makes the best salvage bid theirs, `brand` gives the title a brand,
    `paired` an inspection that found paired devices."""
    uc.write_car(n, like, **over)
    recs = uc.records(n, like, **over)
    if buyer:
        for b, reports in BUYERS.items():
            uc.write("uc_auction", "buyers", {"buyerId": b, "name": b, "salvage": True, "titleDbReporting": reports})
        a = recs["uc_auction"][1]
        uc.write("uc_auction", "vin_auction", a | {"bestBid": a["bestBid"] | {"buyerId": buyer}})
    if brand:
        uc.write("uc_title", "titles", recs["uc_title"][1] | {"brand": brand, "brandSource": "state"})
    if paired:
        uc.write("uc_insp", "inspections", recs["uc_insp"][1] | {"pairedDevices": True})
    miles = recs["uc_lease"][1]["odometerAtReturn"]
    body = {"org_unit_id": uc.ORG, "template_key": "used_cars", "asset_key": uc.vin_key(uc.ORG, uc.vin(n)), "reason": "lease_end",
            "facts": {"vin": uc.vin(n), "mileage": miles, "return_date": "2026-10-03"}}  # fmt: skip
    return uc.get(uc.ok(call("case.open", body, "planner-a"))["case_id"])


def _approve(c: dict[str, Any], plan: str | None = None) -> dict[str, Any]:
    body = {"case_id": c["id"], "reviewed": True, "rationale": "Follow the numbers."}
    r = call(
        "decision.approve" if plan is None else "decision.override", body | ({} if plan is None else {"route": plan}), "approver"
    )
    assert r["ok"], r
    return uc.get(c["id"])


def _rows(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = "SELECT id, step, kind, system, status, simulated, doc_ref FROM instruction WHERE case_id = :c ORDER BY step"
        return [dict(r) for r in s.execute(text(q), {"c": cid}).mappings()]


def _run(cid: str, steps: int) -> list[str]:
    """Send each step as the worker does, the next one once the one before is confirmed: what each send returned."""
    out = []
    for n in range(steps):
        rows = _rows(cid)
        assert len(rows) == n + 1, rows  # step n is queued exactly when step n - 1 was acknowledged
        out.append(send.send(rows[n]["id"]))
    return out


def _item(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        q = "SELECT * FROM work_item WHERE case_id = :c AND type = :t"
        return dict(s.execute(text(q), {"c": cid, "t": follow_through.TYPE}).mappings().one())


def test_uc_18_retail_sends_three_steps():
    c = _open(1, brand="rebuilt")
    assert c["recommendation"]["id"] == "retail:LOT-S" and c["recommendation"]["disclosures"] == ["Title brand: rebuilt"]
    done = _approve(c)
    assert [s["k"] for s in done["exec"]["steps"]] == ["recon_order", "lot_transfer", "listing"]
    assert [r["kind"] for r in _rows(c["id"])] == ["recon_order"]  # only the first goes out on approval
    assert _run(c["id"], 3) == ["sent", "sent", "sent"]
    rows = _rows(c["id"])
    assert [(r["kind"], r["system"], r["status"]) for r in rows] == [(k, "uc_dms", "acknowledged") for k in
                                                                    ("recon_order", "lot_transfer", "listing")]  # fmt: skip
    assert [k for k, _, _ in Stub.calls] == ["recon-orders", "transfers", "listings"]
    (_, recon, hdr), (_, transfer, _), (_, listing, _) = Stub.calls
    assert recon["vin"] == uc.vin(1) and recon["estimate"] == 1200
    assert hdr["Idempotency-Key"].endswith(".0.recon_order")
    assert (transfer["fromLot"], transfer["toLot"]) == (
        "LOT-N",
        "LOT-S",
    )  # the lot nearest the return centre, then the chosen one
    sale = next(t["amt"] for t in c["recommendation"]["terms"] if t["kind"] == "sale")
    assert listing == {"vin": uc.vin(1), "lotId": "LOT-S", "price": sale, "disclosures": ["Title brand: rebuilt"]}
    after = uc.get(c["id"])  # each confirmation is recorded on the case, and the last one closes the case
    assert [s["ack"]["ref"] for s in after["exec"]["steps"]] == [r["doc_ref"] for r in rows] and after["stage"] == "closed"
    assert _item(c["id"])["status"] == "done" and _item(c["id"])["outcome"] == f"Confirmed: {rows[2]['doc_ref']}"


def test_uc_18_auction_consignment_with_title():
    c = _open(1)
    done = _approve(c, "Wholesale auction")
    assert [s["k"] for s in done["exec"]["steps"]] == ["consignment"]  # a one-step route
    assert _run(c["id"], 1) == ["sent"]
    ((kind, body, _),) = Stub.calls
    assert kind == "consignments" and body["vin"] == uc.vin(1)
    assert body["titleRef"] == f"TITLE-{uc.vin(1)}" and body["disclosures"] == []
    assert body["saleDate"] == (clock.now().date() + timedelta(days=6)).isoformat()  # the next sale of the car's site, 6 days on
    assert [(r["system"], r["status"]) for r in _rows(c["id"])] == [("uc_auction", "acknowledged")]
    assert uc.get(c["id"])["stage"] == "closed"


def test_uc_18_dealer_trade_books_the_best_partner_bid():
    c = _open(1)
    _approve(c, "Dealer trade")
    assert _run(c["id"], 1) == ["sent"]
    ((kind, body, _),) = Stub.calls
    assert kind == "dealer-trades" and (body["partner"], body["price"]) == ("Partner B", 21300)
    assert body["titleRef"] == f"TITLE-{uc.vin(1)}"


def test_uc_18_salvage_only_to_reporting_buyer():
    blocked = _open(8, buyer="SB-2")  # the best bid is from a buyer that does not report
    salvage = next(r for r in blocked["routes"] if r["id"] == "salvage")
    assert salvage["excluded"] and salvage["failReason"].endswith(REASON) and blocked["recommendation"]["id"] != "salvage"
    chosen = {**blocked, "chosen": salvage}
    ins = {"idem_key": "APR-X.0.salvage_sale", "kind": "salvage_sale"}
    with SessionLocal() as s, pytest.raises(writers.Refused, match=REASON):  # the writer refuses it too: nothing is sent
        writers.salvage_sale(s, ins, chosen, {})
    assert Stub.calls == []
    uc.finish()
    uc.start()
    ok = _open(8, buyer="SB-1")  # a reporting buyer
    assert ok["recommendation"]["id"] == "salvage"
    _approve(ok)
    assert _run(ok["id"], 1) == ["sent"]
    ((kind, body, _),) = Stub.calls
    assert (kind, body) == ("salvage-sales", {"vin": uc.vin(8), "buyerId": "SB-1"})


def test_uc_18_salvage_gate_reads_the_buyers_reporting_status():
    pack = load_pack("used_cars")
    gate: GateDef = catalogue()["G-VEH-SALV"].model_copy(update={"params": {"routes": ["salvage"]}})
    no = check_salvage_reporting({"vendor": {"buyer_id": "SB-2", "title_db_reporting": False}}, pack, gate)
    assert no is not None and not no.passed and no.reason == REASON and no.effect.routes == ("salvage",)
    assert no.effect.kind == "block"
    assert check_salvage_reporting({"vendor": {"buyer_id": "SB-1", "title_db_reporting": True}}, pack, gate) is None
    assert check_salvage_reporting({"vendor": {"buyer_id": "SB-9"}}, pack, gate) is None  # nothing said yet: the evidence decides
    assert check_salvage_reporting({}, pack, gate) is None


def test_uc_18_late_confirmation_reminds_owner(monkeypatch):
    c = _open(1)
    queue_off = _approve(c)  # nothing is confirmed: the first step is queued and no system has answered
    assert queue_off["stage"] == "approved"
    item = _item(c["id"])
    assert (item["kind"], item["owner_role"], item["status"], item["escalated_at"]) == ("step", "Planner", "open", None)
    assert item["title"] == f"Confirm Retail lot for {c['id']} within 7 days"
    start = clock.now()
    assert item["due_at"] == start + timedelta(days=7)
    monkeypatch.setattr(process.clock, "now", lambda: start + timedelta(days=6))
    with SessionLocal() as s:
        assert process.on_sla(s, item["id"]) == "not_due"
        s.commit()
    monkeypatch.setattr(process.clock, "now", lambda: start + timedelta(days=8))
    with SessionLocal() as s:
        assert process.on_sla(s, item["id"]) == "escalated"  # the reminder: still the lot manager's, now more urgent
        assert process.on_sla(s, item["id"]) == "not_due"  # and only once
        s.commit()
        n = s.execute(text("SELECT count(*) FROM action_journal WHERE action = 'work.escalate' AND case_id = :c"), {"c": c["id"]})
        assert n.scalar_one() == 1
    after = _item(c["id"])
    assert after["owner_role"] == "Planner" and after["status"] == "open" and after["escalated_at"] is not None
    assert after["priority"] == item["priority"] - process.ESCALATION_PRIORITY


def test_uc_18_a_new_approval_replaces_the_timer():
    c = _open(1)
    _approve(c)
    first = _item(c["id"])["id"]
    with SessionLocal() as s:
        follow_through.open_timer(s, uc.get(c["id"]))
        s.commit()
        rows = s.execute(
            text("SELECT id, status FROM work_item WHERE case_id = :c AND type = 'UC-CONFIRM' ORDER BY id"), {"c": c["id"]}
        )
        got = [r.status for r in rows]
    assert got == ["done", "open"] and first


def test_uc_18_agent_cannot_approve_so_nothing_is_sent():
    c = _open(1)
    body = {"case_id": c["id"], "reviewed": True, "rationale": "Within the margin."}
    hdr = h("approver") | {"X-Circularity-Preparer": chain.AGENT_IDS["disposition"]}
    r = client.post("/api/actions/decision.approve", json=body, headers=hdr)
    assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required"
    assert _rows(c["id"]) == [] and Stub.calls == []
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM work_item WHERE type = 'UC-CONFIRM'")).scalar_one() == 0


def test_uc_25_infotainment_reset_before_release():
    paired = _open(15, like=1, paired=True)
    assert all(r["steps"][0] == "infotainment_reset" for r in paired["routes"])  # first on every channel
    done = _approve(paired)
    assert [s["k"] for s in done["exec"]["steps"]] == ["infotainment_reset", "recon_order", "lot_transfer", "listing"]
    assert _run(paired["id"], 1) == ["simulated"]  # a person's checklist step: no system write
    assert Stub.calls == []
    plain = _open(1)
    assert all("infotainment_reset" not in r["steps"] for r in plain["routes"])
    assert [s["k"] for s in _approve(plain)["exec"]["steps"]] == ["recon_order", "lot_transfer", "listing"]
