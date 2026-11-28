"""Plan 9 P9-9.20 (story UC-23): a sold used car is closed against its forecast, and a lease return's residual gain or loss and
the lessee's charges are held for Finance.

UC-S1 (VIN ...001: 38,000 miles on a 36,000-mile contract, book value 19,500) is approved for retail at LOT-S (forecast net
21,489.50 on 24,300 in 15 days), then sold; the sale arrives as the dealer system's adapter writes it (`outcome.*` facts).
`close_case` keeps the sale against the forecast on the case and prepares each amount as an agent's `usedCar.post`, which
the hold policy holds as a proposal. Nothing leaves di until a person (Finance) accepts it. The writers run against a stub
client, as in test_uc_follow_through."""

from decimal import Decimal
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import close_used_cars
from di.services.cases.close_used_cars import AGENT, amounts, close_case, excess_rate
from di.services.instructions import queue, send, writers
from di.services.modeler.pack import load_pack
from tests import ucfixtures as uc
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

WEAR = [
    {"label": "Paint and panel, rear door", "amount": 700, "excessWear": True},
    {"label": "Tyres", "amount": 500, "excessWear": False},
]
S4_REPLY = (
    "<r><AccountingDocument>0100000042</AccountingDocument><CompanyCode>1000</CompanyCode><FiscalYear>2026</FiscalYear>"
    "<MaximumLogItemSeverityCode>1</MaximumLogItemSeverityCode></r>"
)


class _Reply:
    def __init__(self, doc: dict[str, Any] | None = None, content: bytes = b""):
        self._doc, self.content = doc, content

    def json(self) -> dict[str, Any]:
        return self._doc or {}


class Stub:
    """A source client that records its writes: the lease system answers a charge with its id, S/4HANA a posted document."""

    calls: ClassVar[list[tuple[str, Any, dict[str, str]]]] = []

    def __init__(self, source: str):
        self.source = source

    def request(
        self, method: str, path: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None, content=None
    ):
        assert method == "POST"
        if self.source == "erp":
            Stub.calls.append(("journal", (content or b"").decode(), headers or {}))
            return _Reply(content=S4_REPLY.encode())
        assert path == "/charges", path  # relative to the lease adapter's base path, which the real client puts in front
        Stub.calls.append((path.rsplit("/", 1)[1], json, headers or {}))
        return _Reply({"chargeId": f"CH-{len(Stub.calls):04d}", **(json or {})})

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def fresh():
    uc.start()
    Stub.calls = []
    yield
    uc.finish()


def _open(wear: bool = False) -> dict[str, Any]:
    """UC-S1 on file, its inspection with the recon lines when `wear`, opened and approved as the planner and approver do."""
    uc.write_car(1)
    if wear:
        uc.write("uc_insp", "inspections", uc.records(1)["uc_insp"][1] | {"reconLines": WEAR})
    miles = uc.records(1)["uc_lease"][1]["odometerAtReturn"]
    body = {"org_unit_id": uc.ORG, "template_key": "used_cars", "asset_key": uc.vin_key(uc.ORG, uc.vin(1)), "reason": "lease_end",
            "facts": {"vin": uc.vin(1), "mileage": miles, "return_date": "2026-10-03"}}  # fmt: skip
    c = uc.get(uc.ok(call("case.open", body, "planner-a"))["case_id"])
    assert c["recommendation"]["id"] == "retail:LOT-S" and c["recommendation"]["net"] == 21489.50
    r = call("decision.approve", {"case_id": c["id"], "reviewed": True, "rationale": "Follow the numbers."}, "approver")
    assert r["ok"], r
    return uc.get(c["id"])


def _sell(price: float = 24300, days: int = 15) -> None:
    """The dealer system reports the listing sold, as its adapter writes it."""
    sale = {"listingId": "LST-0001", "vin": uc.vin(1), "lotId": "LOT-S", "price": price, "listedAt": "2026-10-07T09:00:00+00:00",
            "soldAt": "2026-10-22T09:00:00+00:00", "daysToSale": days, "org_unit_id": uc.ORG}  # fmt: skip
    uc.write("uc_dms", "sales", sale)


def _close(cid: str, ctx=None):
    with SessionLocal() as s:
        r = close_case(s, cid, ctx)
        s.commit()
    return r


def _held(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT id, agent, action, status, input FROM agent_proposal WHERE case_id = :c ORDER BY id"), {"c": cid}
        ).mappings()
        return [dict(r) for r in rows]


def _of(cid: str, kind: str) -> list[dict[str, Any]]:
    return [p for p in _held(cid) if p["input"]["kind"] == kind]


def test_uc_23_sale_recorded_against_forecast():
    c = _open()
    r = _close(c["id"])
    assert r.status == "waiting_for_sale" and "close" not in uc.get(c["id"]) and _held(c["id"]) == []  # nothing before a sale
    _sell()
    r = _close(c["id"])
    assert r.status == "closed"
    sale = uc.get(c["id"])["close"]["sale"]
    assert (sale["sale_price"], sale["days_to_sale"], sale["forecast_net"], sale["forecast_days"]) == (24300, 15, 21489.50, 15)
    assert (sale["price_error"], sale["days_error"], sale["net_error"], sale["realised_net"]) == (0.0, 0, 0.0, 21489.50)
    assert sale["route"] == "retail:LOT-S" and sale["sold_at"].startswith("2026-10-22")
    assert "outcome" not in uc.get(c["id"])  # confirming an outcome is a person's: only the sale is kept


def test_uc_23_error_recorded_when_the_sale_differs():
    c = _open()
    _sell(price=23000, days=20)  # 1,300 under the lot's average price, five days slower (38 a day of holding cost)
    r = _close(c["id"])
    sale = uc.get(c["id"])["close"]["sale"]
    assert (sale["price_error"], sale["days_error"], sale["net_error"], sale["realised_net"]) == (-1300.0, 5, -1490.0, 19999.50)
    assert r.gain_loss == 499.50  # 19,999.50 less the book value 19,500


def test_uc_23_lease_gain_loss_to_finance():
    c = _open()
    _sell()
    r = _close(c["id"])
    assert r.gain_loss == 1989.50  # realised net 21,489.50 less the residual 19,500
    (p,) = _of(c["id"], "residual")
    assert p["action"] == "usedCar.post" and p["status"] == "pending" and p["agent"] == AGENT
    assert p["input"]["amount"] == 1989.50 and p["input"]["case_id"] == c["id"] and p["input"]["label"] == "Residual gain"
    assert "close" in uc.get(c["id"]) and "posted" not in uc.get(c["id"])["close"]  # held: nothing is posted yet
    assert [(x["kind"], x["state"]) for x in r.posts if x["kind"] == "residual"] == [("residual", "held")]


def test_uc_23_lessee_charges():
    c = _open(wear=True)
    _sell()
    r = _close(c["id"])
    assert r.charges == {"excess_mileage": 400.0, "excess_wear": 700.0}  # 2,000 miles x 0.20; the one excessWear line
    mileage, wear = _of(c["id"], "excess_mileage"), _of(c["id"], "excess_wear")
    assert [p["input"]["amount"] for p in mileage + wear] == [400.0, 700.0] and len(mileage) == len(wear) == 1
    assert all(p["status"] == "pending" for p in mileage + wear)
    assert len(_held(c["id"])) == 3  # the residual and the two charges, each its own proposal


def test_uc_23_no_charge_without_excess():
    c = _open()
    uc.write("uc_lease", "lease_returns", uc.records(1)["uc_lease"][1] | {"contractMileage": 45000})  # miles under the contract
    _sell()
    r = _close(c["id"])
    assert r.charges == {} and [p["input"]["kind"] for p in _held(c["id"])] == ["residual"]


def test_uc_23_agent_cannot_accept():
    c = _open()
    _sell()
    _close(c["id"])
    (p,) = _of(c["id"], "residual")
    hdr = h("finance") | {"X-Circularity-Preparer": AGENT}
    r = client.post("/api/actions/proposal.accept", json={"id": p["id"]}, headers=hdr).json()
    assert r["ok"] is False and r["error"]["code"] in ("approval_required", "out_of_scope"), r
    assert _of(c["id"], "residual")[0]["status"] == "pending" and "posted" not in uc.get(c["id"])["close"]


def test_uc_23_finance_accepts_and_it_is_posted_once():
    c = _open(wear=True)
    _sell()
    _close(c["id"])
    (p,) = _of(c["id"], "residual")
    out = uc.ok(call("proposal.accept", {"id": p["id"]}, "finance"))
    assert out["status"] == "accepted" and out["output"]["amount"] == 1989.50
    posted = uc.get(c["id"])["close"]["posted"]
    assert list(posted) == ["residual"] and posted["residual"]["amount"] == 1989.50 and posted["residual"]["by"] == "finance"
    again = _close(c["id"])  # a second close prepares nothing new for the amounts it already holds or posted
    assert [x["state"] for x in again.posts] == ["exists", "exists", "exists"] and len(_held(c["id"])) == 3
    dup = client.post("/api/actions/usedCar.post", json=p["input"], headers=h("finance")).json()
    assert dup["ok"] is False and dup["error"]["code"] == "duplicate"


def test_uc_23_close_by_an_agent_holds_every_post():
    c = _open(wear=True)
    _sell()
    hdr = h("finance") | {"X-Circularity-Preparer": AGENT}
    r = client.post("/api/actions/usedCar.close", json={"case_id": c["id"]}, headers=hdr).json()
    assert r["ok"], r
    assert [(x["kind"], x["state"]) for x in r["output"]["posts"]] == [
        ("residual", "held"),
        ("excess_mileage", "held"),
        ("excess_wear", "held"),
    ]
    assert {p["status"] for p in _held(c["id"])} == {"pending"} and "posted" not in uc.get(c["id"])["close"]


def test_uc_23_close_needs_an_approved_decision_and_a_used_car():
    uc.write_car(1)
    body = {"org_unit_id": uc.ORG, "template_key": "used_cars", "asset_key": uc.vin_key(uc.ORG, uc.vin(1)), "reason": "lease_end",
            "facts": {"vin": uc.vin(1), "mileage": 38000, "return_date": "2026-10-03"}}  # fmt: skip
    cid = uc.ok(call("case.open", body, "planner-a"))["case_id"]
    _sell()
    assert _close(cid).status == "not_approved" and _held(cid) == []  # opened, not approved
    assert _close("RT-1048").status == "not_applicable"  # an industrial case is left alone
    missing = client.post("/api/actions/usedCar.close", json={"case_id": "NOPE-1"}, headers=h("finance")).json()
    assert missing["ok"] is False


def test_uc_23_a_trade_in_has_no_residual_and_no_charges():
    pack = load_pack("used_cars")
    facts = {"asset": {"return_kind": "trade_in", "book_value": 15000, "mileage_at_return": 90000, "contract_mileage": 30000}}
    assert amounts(facts, pack, Decimal(16000)) == {}  # a trade-in has no lease to settle
    assert float(excess_rate(pack)) == 0.2


def test_uc_23_accepted_posts_are_sent_to_the_systems(monkeypatch):
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    monkeypatch.setattr(close_used_cars, "sending", lambda: True)
    monkeypatch.setattr(send, "_refusal", lambda *a: None)
    c = _open()
    _sell()
    _close(c["id"])
    for kind in ("residual", "excess_mileage"):
        uc.ok(call("proposal.accept", {"id": _of(c["id"], kind)[0]["id"]}, "finance"))
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT id, kind, system, step, status, approval_ref FROM instruction WHERE case_id = :c ORDER BY step"),
            {"c": c["id"]},
        ).mappings().all()  # fmt: skip
    close_rows = [r for r in rows if r["approval_ref"].startswith("CLOSE-")]
    assert [(r["kind"], r["system"]) for r in close_rows] == [("residual", "erp"), ("lessee_charge", "uc_lease")]
    assert all(queue.SYSTEM_OF[k] == system for k, system in close_used_cars.INSTRUCTION.values())  # one table of systems
    assert {k for k, _ in close_used_cars.INSTRUCTION.values()} <= queue.OFF_PLAN
    assert [send.send(r["id"]) for r in close_rows] == ["sent", "sent"]
    (journal, charge) = Stub.calls
    assert journal[0] == "journal" and "0048200000" in journal[1] and "-1989.50" in journal[1] and "1989.50" in journal[1]
    assert "0021100000" in journal[1] and f"Residual {c['id']}"[:25] in journal[1]
    assert charge[0] == "charges" and charge[1] == {"leaseId": "LS-0001", "kind": "excess_mileage", "amount": 400.0}
    assert charge[2]["Idempotency-Key"].startswith(f"CLOSE.{c['id']}.excess_mileage.")
    with SessionLocal() as s:
        done = s.execute(text("SELECT kind, status, doc_ref FROM instruction WHERE approval_ref = :r ORDER BY step"),
                         {"r": f"CLOSE-{c['id']}"}).mappings().all()  # fmt: skip
    assert [(r["kind"], r["status"]) for r in done] == [("residual", "acknowledged"), ("lessee_charge", "acknowledged")]
    assert done[0]["doc_ref"] == "0100000042" and done[1]["doc_ref"].startswith("CH-")
