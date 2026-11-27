"""Plan 9, P9-6.11 (story DV-07): wholesale lots of received devices sold to the best approved bid. A lot groups devices routed to
`wholesale` by model and grade within the lot cap (GR-D4); the best bid is computed, net of fees and logistics a unit, from the
bids of buyers on the approved-buyers market table (GR-D12, I-15), never by a language model; a person (or the standing policy at
or under GR-D10's $25,000, I-11) accepts it with `lot.approve`: the person who built or proposed the lot cannot, no agent can, and
another tenant cannot see it (R21). Nothing here writes language, so there is no model call: every figure and word is computed
or fixed wording.

The tests seed their own lots and bids (lot refs `LOT-T-*`, bid ids `BID-T-*`) and never touch the mock's LOT-W-0001 rows.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.repositories import device_lots, device_market
from di.repositories import market_tables as tables_repo
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, HELD_FOR_PERSON, forbidden, held_for_person
from di.services.cases import store
from di.services.modeler import tables
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import device_lots as lots
from di.services.modeler.valuers.device_lots import Bid, LotCandidate
from tests import starting
from tests.helpers import call, client, h

ORG = "Customer A"
# the mock's LOT-W-0001, per unit: (amount, fees, logistics); B05 bids the most gross and is unverified, B02 is the best net
MOCK = {"B01": (316, 6, 4), "B02": (324, 8, 6), "B03": (312, 6, 5), "B04": (320, 9, 7), "B05": (340, 12, 8), "B06": (310, 5, 6)}
APPROVED = {"B01", "B02", "B03", "B04", "B06"}
AGENT = {"X-Circularity-Preparer": "gap", "X-Circularity-Confirmed": "true"}


def _bids(terms: dict[str, tuple[float, float, float]] = MOCK) -> list[Bid]:
    return [Bid(f"BID-T-{n}", code, *t) for n, (code, t) in enumerate(terms.items(), 1)]


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM device_lot_member"))
        conn.execute(text("DELETE FROM device_lot"))
        conn.execute(text("DELETE FROM device_bid WHERE bid_id LIKE 'BID-T-%'"))
        conn.execute(text("DELETE FROM device_tradein WHERE trade_in_id LIKE 'TI-T-%'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _seed(lot_id: str = "L-T-1", ref: str = "LOT-T-0001", *, units: int = 100, status: str = "bidding", org: str = ORG,
          created_by: str = "planner-a", proposed_by: str | None = None, terms: dict | None = None) -> str:  # fmt: skip
    """A lot row with bids on it (`terms`: buyer -> (amount, fees, logistics) a unit; None: the mock's six)."""
    when = clock.now() - timedelta(days=1)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO device_lot (id, org_unit_id, lot_ref, model, grade, units, status, created_by, proposed_by) "
                "VALUES (:i, :o, :r, 'Galaxy S23', 'C', :u, :st, :cb, :pb)"
            ),
            {"i": lot_id, "o": org, "r": ref, "u": units, "st": status, "cb": created_by, "pb": proposed_by},
        )
        for n, (code, (amount, fees, logistics)) in enumerate((MOCK if terms is None else terms).items(), 1):
            conn.execute(
                text(
                    "INSERT INTO device_bid (bid_id, lot_ref, buyer_code, amount, fees, logistics, received_at) "
                    "VALUES (:b, :r, :c, :a, :f, :l, :t)"
                ),
                {"b": f"BID-T-{lot_id}-{n}", "r": ref, "c": code, "a": amount, "f": fees, "l": logistics, "t": when},
            )
        if (
            status == "proposed"
        ):  # a proposed lot names the bid it was proposed on and its value (the best approved net, as propose does)
            bids = [Bid(f"BID-T-{lot_id}-{n}", c, *t) for n, (c, t) in enumerate((MOCK if terms is None else terms).items(), 1)]
            best = lots.rank_bids(bids, APPROVED).best
            if best is not None:
                conn.execute(
                    text("UPDATE device_lot SET best_bid_id = :b, value_usd = :v WHERE id = :i"),
                    {"b": best.bid_id, "v": lots.lot_value(best.net, units), "i": lot_id},
                )
    return lot_id


def _lot(lot_id: str = "L-T-1") -> dict:
    with SessionLocal() as s:
        r = device_lots.get(s, lot_id)
    assert r is not None
    return {"status": r.status, "value": r.value_usd, "best": r.best_bid_id, "by": r.approved_by, "reason": r.reason,
            "proposed_by": r.proposed_by}  # fmt: skip


def _policy(max_value: int = 25000, owner: str = "approver") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO standing_policy (id, pack, org_unit_id, name, ver, status, rules, owner, maker, checker, "
                "approved_at) "
                "VALUES ('SP-T-1', 'device', :o, 'Small wholesale lots', 1, 'active', CAST(:r AS jsonb), :ow, "
                "'admin', 'approver', now())"
            ),
            {"o": ORG, "r": json.dumps({"max_value": max_value, "min_confidence": 0.5}), "ow": owner},
        )


# ------------------------------------------------------------------ the lots and the best bid (pure)
def test_dv_07_lots_by_model_and_grade_within_cap():
    at = datetime(2026, 9, 1, tzinfo=UTC)
    devices = [LotCandidate(f"RT-{n}", "Galaxy S23", "C", at + timedelta(minutes=n)) for n in range(1150)]
    devices += [LotCandidate("RT-X1", "Galaxy S23", "B", at), LotCandidate("RT-X2", "iPhone 14", "C", at)]
    made = lots.build_lots(devices, 500)
    mine = [x for x in made if (x.model, x.grade) == ("Galaxy S23", "C")]
    assert [x.units for x in mine] == [500, 500, 150]
    assert mine[0].case_ids[0] == "RT-0" and mine[1].case_ids[0] == "RT-500" and mine[2].case_ids[-1] == "RT-1149"  # oldest first
    assert sorted((x.model, x.grade, x.units) for x in made if x not in mine) == [("Galaxy S23", "B", 1), ("iPhone 14", "C", 1)]
    for x in made:  # no lot mixes models or grades
        assert len({(d.model, d.grade) for d in devices if d.case_id in x.case_ids}) == 1


def test_dv_07_only_approved_bids():
    r = lots.rank_bids(_bids(), APPROVED)
    assert r.best is not None and r.best.buyer_code == "B02" and r.best.net == 310
    assert [b.buyer_code for b in r.ranked] == ["B02", "B01", "B04", "B03", "B06"]  # 310, 306, 304, 301, 299
    assert [(d.buyer_code, d.reason) for d in r.dropped] == [("B05", "Buyer B05 is not an approved wholesale buyer")]
    assert lots.best_bid(_bids(), APPROVED) == r.best
    assert lots.best_bid(_bids(), set()) is None and lots.best_bid([], APPROVED) is None
    top = lots.best_bid(_bids({"B05": (340, 12, 8)}), APPROVED)
    assert top is None  # the highest gross is never chosen when its buyer is not approved
    assert lots.lot_value(310.0, 100) == 31000.0


def test_dv_07_ranking_is_by_net_and_ties_go_to_the_earlier_bid():
    r = lots.rank_bids(
        [Bid("BID-2", "B02", 300, 5, 5), Bid("BID-1", "B01", 300, 5, 5), Bid("BID-3", "B03", 400, 90, 5)], APPROVED
    )
    assert [b.bid_id for b in r.ranked] == ["BID-3", "BID-1", "BID-2"]  # 305, then the tie by id


def test_dv_07_the_approved_buyers_are_a_market_table_and_gr_d10_gr_d12_are_in_the_pack():
    pack = load_pack("device")
    spec = tables.market_spec("device")
    assert spec is not None and spec.has("approved_buyers") and spec.table("approved_buyers").kind == "rate_card"
    with SessionLocal() as s:
        tables_repo.ensure_seeded(s, "device")
        row = tables_repo.effective(s, ORG, "device", spec.flow, "US", "approved_buyers", clock.now().date())
        s.commit()
    assert row is not None
    assert {k for k, v in tables.rate_card(row).values.items() if v > 0} == APPROVED
    g = {x.id: x for x in pack.guardrails}
    assert g["GR-D10"].owner == "Commercial manager" and g["GR-D10"].param is not None
    assert (g["GR-D10"].param.field, g["GR-D10"].param.value) == ("max_value_usd", 25000)
    assert g["GR-D12"].type == "Compliance" and g["GR-D12"].locked


# ------------------------------------------------------------------ the actions
def test_dv_07_lot_over_25k_waits_for_commercial_manager():
    _seed()
    r = call("lot.propose", {"lot_id": "L-T-1"}, "planner.a")
    assert r["ok"] is True, r
    out = r["output"]
    assert out["status"] == "proposed" and out["value_usd"] == 31000 and out["approved_by_policy"] is False
    assert out["waits_for"] == {"role": "Approver", "owner": "Commercial manager", "reason": out["waits_for"]["reason"]}
    assert "$31,000" in out["waits_for"]["reason"] and "$25,000" in out["waits_for"]["reason"]
    assert out["best_bid"]["buyer_code"] == "B02" and out["best_bid"]["net"] == 310
    assert [d["buyer_code"] for d in out["dropped"]] == ["B05"]
    assert _lot()["status"] == "proposed" and _lot()["best"] == "BID-T-L-T-1-2"
    _policy()  # a standing policy in force does not reach $31,000: a person approves it
    again = call("lot.approve", {"lot_id": "L-T-1"}, "approver")
    assert again["ok"] is True and _lot()["by"] == "approver"


def test_dv_07_lot_at_or_under_25k_is_approved_by_the_standing_policy():
    _seed("L-T-2", "LOT-T-0002", units=80, terms={"B01": (310, 5, 5)})  # net 300 a unit: $24,000
    # no standing policy in force: a person decides it, as over the limit
    held = call("lot.propose", {"lot_id": "L-T-2"}, "planner.a")["output"]
    assert held["status"] == "proposed" and held["value_usd"] == 24000 and held["approved_by_policy"] is False
    assert held["waits_for"]["owner"] == "Commercial manager"
    _seed("L-T-3", "LOT-T-0003", units=80, terms={"B01": (310, 5, 5)})
    _policy()
    r = call("lot.propose", {"lot_id": "L-T-3"}, "planner.a")
    assert r["ok"] is True, r
    out = r["output"]
    assert out["status"] == "approved" and out["approved_by_policy"] is True and out["value_usd"] == 24000
    assert "approved by policy SP-T-1 v1, owner approver" in out["log"]
    assert _lot("L-T-3")["by"] == "policy SP-T-1 v1"
    # a policy that does not reach the value does not approve it
    with engine.begin() as conn:
        conn.execute(text("UPDATE standing_policy SET rules = jsonb_set(rules, '{max_value}', '20000')"))
    _seed("L-T-4", "LOT-T-0004", units=80, terms={"B01": (310, 5, 5)})
    assert call("lot.propose", {"lot_id": "L-T-4"}, "planner.a")["output"]["status"] == "proposed"


def test_dv_07_no_approved_bid_is_not_proposed():
    _seed(terms={"B05": (340, 12, 8)})  # the only bid is from an unverified buyer
    r = call("lot.propose", {"lot_id": "L-T-1"}, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "B05" in r["error"]["message"]
    assert _lot()["status"] == "bidding"


def test_dv_07_build_lots_from_open_wholesale_cases():
    cid = _wholesale_case("D-T-1")
    r = call("lot.build", {"org_unit_id": ORG}, "planner.a")
    assert r["ok"] is True, r
    (made,) = [x for x in r["output"]["lots"] if cid in x["case_ids"]]
    assert (made["model"], made["grade"], made["units"], made["status"]) == ("iPhone 14", "B", 1, "bidding")
    assert call("lot.build", {"org_unit_id": ORG}, "planner.a")["output"]["lots"] == []  # already in a lot
    wrong = call("lot.propose", {"lot_id": made["id"]}, "planner.a")  # no bids yet
    assert wrong["ok"] is False and wrong["error"]["code"] == "conflict"
    assert [x["id"] for x in call("lot.list", {}, "planner.a")["output"]["lots"]] == [made["id"]]


def test_dv_07_approve_approves_the_member_cases_and_reject_needs_a_reason():
    cid = _wholesale_case("D-T-2")
    lot = _seed("L-T-5", "LOT-T-0005", units=1, proposed_by="admin", status="proposed")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO device_lot_member (lot_id, case_id) VALUES (:l, :c)"), {"l": lot, "c": cid})
    r = call("lot.approve", {"lot_id": lot}, "approver")
    assert r["ok"] is True, r
    assert _lot(lot)["status"] == "approved" and _lot(lot)["by"] == "approver"
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None and c["stage"] == "approved" and c["approval"]["by"] == "Approver"
    assert c["exec"]["steps"][0]["k"] == "reserve" and [x["k"] for x in c["exec"]["steps"]] == [
        "reserve",
        "sale",
        "ship",
        "fulfil",
        "receipt",
        "credit",  # the customer credit memo (P9-13.4)
    ]  # the sale plan
    again = call("lot.approve", {"lot_id": lot}, "approver")
    assert again["ok"] is False and again["error"]["code"] == "conflict"
    _seed("L-T-6", "LOT-T-0006", proposed_by="admin", status="proposed")
    short = call("lot.reject", {"lot_id": "L-T-6", "reason": "no"}, "approver")
    assert short["ok"] is False and short["error"]["code"] == "validation_error"
    ok = call("lot.reject", {"lot_id": "L-T-6", "reason": "Buyer pool too thin this week"}, "approver")
    assert (
        ok["ok"] is True and _lot("L-T-6")["status"] == "rejected" and _lot("L-T-6")["reason"] == "Buyer pool too thin this week"
    )


def test_dv_07_the_valuer_reads_the_best_open_approved_bid_per_unit():
    _seed("L-T-7", "LOT-T-0007", units=100)  # a lot of Galaxy S23 grade C in bidding, the mock's six bids
    with SessionLocal() as s:
        net = device_lots.best_net_per_unit(s, "Galaxy S23", "C", clock.now().date(), ORG)
        none = device_lots.best_net_per_unit(s, "iPhone 14", "A", clock.now().date(), ORG)
    assert net == 310.0 and none is None


def test_dv_07_listing_the_bids_is_as_of():
    _seed("L-T-8", "LOT-T-0008")
    with SessionLocal() as s:
        assert len(device_market.open_bids(s, "LOT-T-0008", clock.now().date())) == 6
        assert device_market.open_bids(s, "LOT-T-0008", clock.now().date() - timedelta(days=10)) == []


# ------------------------------------------------------------------ R21: a lot is a new approvable object
def test_device_lot_maker_cannot_approve():
    _seed("L-T-9", "LOT-T-0009", created_by="admin", proposed_by="planner-a", status="proposed")
    built = call("lot.approve", {"lot_id": "L-T-9"}, "admin")  # the builder
    assert built["ok"] is False and built["error"]["code"] == "conflict" and "cannot approve" in built["error"]["message"]
    _seed("L-T-10", "LOT-T-0010", created_by="planner-a", proposed_by="admin", status="proposed")
    proposed = call("lot.approve", {"lot_id": "L-T-10"}, "admin")  # the proposer
    assert (
        proposed["ok"] is False and proposed["error"]["code"] == "conflict" and "cannot approve" in proposed["error"]["message"]
    )
    assert _lot("L-T-9")["status"] == "proposed" and _lot("L-T-10")["status"] == "proposed"
    assert call("lot.approve", {"lot_id": "L-T-10"}, "approver")["ok"] is True  # someone else may


def test_device_lot_agent_cannot_approve():
    assert forbidden("lot.approve") and forbidden("lot.reject")
    assert "lot.approve" in FORBIDDEN_ACTIONS and "lot.reject" in FORBIDDEN_ACTIONS
    assert held_for_person("lot.propose") and "lot.propose" in HELD_FOR_PERSON and not forbidden("lot.build")
    _seed(status="proposed", proposed_by="admin")
    for action, body in (
        ("lot.approve", {"lot_id": "L-T-1"}),
        ("lot.reject", {"lot_id": "L-T-1", "reason": "An agent decides this"}),
    ):
        r = client.post(f"/api/actions/{action}", json=body, headers=h("approver") | AGENT).json()
        assert r["ok"] is False, action
    assert _lot()["status"] == "proposed"


def test_device_lot_agent_proposal_is_held_for_a_person():
    _seed()
    r = client.post(
        "/api/actions/lot.propose", json={"lot_id": "L-T-1"}, headers=h("planner.a") | {"X-Circularity-Preparer": "coordinator"}
    ).json()
    assert r["ok"] is True and "held" in r["output"]  # a proposal waits for a person, never runs for the agent
    assert _lot()["status"] == "bidding"


def test_device_lot_tenant_boundary():
    _seed("L-T-11", "LOT-T-0011", status="proposed", proposed_by="admin")
    _seed("L-T-12", "LOT-T-0012")
    for action, body in (("lot.propose", {"lot_id": "L-T-12"}), ("lot.approve", {"lot_id": "L-T-11"}),
                         ("lot.reject", {"lot_id": "L-T-11", "reason": "Not for another tenant to reject"})):  # fmt: skip
        r = call(action, body, "planner.b")  # a planner of another tenant
        assert r["ok"] is False and r["error"]["code"] in ("tenant_boundary", "forbidden", "out_of_scope"), (action, r)
    assert _lot("L-T-11")["status"] == "proposed" and _lot("L-T-12")["status"] == "bidding"
    seen = call("lot.list", {}, "planner.b")["output"]["lots"]
    assert [x for x in seen if x["id"] in ("L-T-11", "L-T-12")] == []
    assert call("lot.build", {"org_unit_id": ORG}, "planner.b")["error"]["code"] in ("tenant_boundary", "forbidden")
    mine = call("lot.list", {}, "planner.a")["output"]["lots"]
    assert {x["id"] for x in mine} >= {"L-T-11", "L-T-12"}


def test_device_lot_needs_the_permissions():
    _seed(status="proposed", proposed_by="admin")
    assert call("lot.propose", {"lot_id": "L-T-1"}, "finance")["error"]["code"] == "out_of_scope"  # no manageLots
    assert call("lot.build", {"org_unit_id": ORG}, "finance")["error"]["code"] == "out_of_scope"
    assert call("lot.approve", {"lot_id": "L-T-1"}, "planner.a")["error"]["code"] in ("out_of_scope", "limit_exceeded")


def test_device_lot_over_the_approvers_limit_escalates(monkeypatch):
    from di.services.actions import device_lots as lot_actions

    _seed(status="proposed", proposed_by="admin")
    with engine.begin() as conn:
        conn.execute(text("UPDATE device_lot SET value_usd = 31000 WHERE id = 'L-T-1'"))
    monkeypatch.setattr(lot_actions, "limit_for", lambda *_: 20000.0)  # an approver whose limit is below the lot's value
    r = call("lot.approve", {"lot_id": "L-T-1"}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "limit_exceeded"
    assert _lot()["status"] == "proposed"


def _wholesale_case(case_id: str) -> str:
    """A received device's case of Customer A, awaiting approval, whose recommendation is the wholesale route."""
    from di.connectors.adapters import device_lab as lab
    from di.services.canonical import store as canonical
    from di.services.canonical.store import Fact
    from di.services.device import intake as device_intake
    from tests.device_registry import seed_registry

    n = int(case_id[-1])
    imei = f"3599900000{n:05d}"
    when = (clock.now() - timedelta(days=5)).isoformat()
    seed_registry(imei)
    with SessionLocal() as s:
        canonical.apply(
            s,
            "dvlab",
            [
                Fact("condition", f"IMEI:{imei}", "battery_health_pct", 90),
                Fact("condition", f"IMEI:{imei}", "cosmetic_grade", "B"),
            ],
        )
        lab.land_tradein(
            s,
            {
                "tradeInId": f"TI-T-{n}", "imei": imei,
                "sku": {"brand": "Apple", "model": "iPhone 14", "storageGb": 128, "colour": "Blue", "carrierLock": "unlocked"},
                "quote": {"declaredGrade": "B", "amount": 410, "currency": "USD", "quotedAt": when},
                "partner": "P01", "batchId": None, "bulk": False, "receivedAt": when, "payoutAmount": 410,
            },
            ORG,
        )  # fmt: skip
        s.commit()
    with SessionLocal() as s:
        (cid,) = device_intake.open_pending(s, ORG)
        c = store.get(s, cid, for_update=True)
        assert c is not None
        c["recommendation"] = next(r for r in c["routes"] if r["id"] == "wholesale")
        c["routes"] = [c["recommendation"] if r["id"] == "wholesale" else r for r in c["routes"]]
        c["recommendation"]["excluded"] = False
        c["stage"], c["blocked"], c["submitted"] = "awaiting_approval", None, None
        c.pop("approvalHolds", None)
        store.save(s, c)
        s.commit()
    return cid


# ------------------------------------------------------------------ the phase 6 review (P9-6 fixes)
def _member_lot(case_id: str, lot: str = "L-T-5", **kw) -> str:
    _seed(lot, "LOT-T-0005", units=1, proposed_by="admin", status="proposed", **kw)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO device_lot_member (lot_id, case_id) VALUES (:l, :c)"), {"l": lot, "c": case_id})
    return lot


def _edit_case(cid: str, fn) -> None:
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        assert c is not None
        fn(c)
        store.save(s, c)
        s.commit()


def _stage(cid: str) -> str:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c["stage"]


def test_dv_07_f1_lot_approve_refuses_a_member_no_longer_on_wholesale():
    cid = _wholesale_case("D-T-3")
    lot = _member_lot(cid)
    _edit_case(cid, lambda c: c["recommendation"].update(id="buynow"))  # re-valued after the lot was built
    r = call("lot.approve", {"lot_id": lot}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and cid in r["error"]["message"], r
    assert _lot(lot)["status"] == "proposed" and _stage(cid) == "awaiting_approval"


def test_dv_07_f1_lot_approve_refuses_a_blocked_or_held_member():
    cid = _wholesale_case("D-T-4")
    lot = _member_lot(cid)
    _edit_case(cid, lambda c: c.update(blocked={"reason": "Evidence is missing"}))
    r = call("lot.approve", {"lot_id": lot}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict", r
    _edit_case(cid, lambda c: c.update(blocked=None, gateHold={"gate": "G-DEV-LOCK", "reason": "held"}))
    r = call("lot.approve", {"lot_id": lot}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict", r
    assert _lot(lot)["status"] == "proposed" and _stage(cid) == "awaiting_approval"


def test_dv_07_f1_lot_approve_keeps_the_decision_guards():
    cid = _wholesale_case("D-T-5")
    lot = _member_lot(cid)
    _edit_case(cid, lambda c: c.update(submitted={"byId": "approver", "by": "Approver", "at": "x"}))  # no self-approval
    r = call("lot.approve", {"lot_id": lot}, "approver")
    assert r["ok"] is False, r
    assert _lot(lot)["status"] == "proposed" and _stage(cid) == "awaiting_approval"


def test_dv_07_f1_the_policy_does_not_approve_a_revalued_member():
    cid = _wholesale_case("D-T-6")
    _seed("L-T-5", "LOT-T-0005", units=1, terms={"B01": (310, 5, 5)})
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO device_lot_member (lot_id, case_id) VALUES ('L-T-5', :c)"), {"c": cid})
    _policy()
    _edit_case(cid, lambda c: c["recommendation"].update(id="auction"))
    r = call("lot.propose", {"lot_id": "L-T-5"}, "planner.a")
    assert r["ok"] is True and r["output"]["status"] == "proposed" and r["output"]["approved_by_policy"] is False, r
    assert _stage(cid) == "awaiting_approval"


def test_dv_07_f1_an_approved_member_is_approved_on_the_wholesale_route():
    cid = _wholesale_case("D-T-7")
    lot = _member_lot(cid)
    assert call("lot.approve", {"lot_id": lot}, "approver")["ok"] is True
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None and c["chosen"]["id"] == "wholesale" and c["lotSale"]["lot_id"] == lot


def test_dv_07_f2_lot_build_takes_the_lock_before_it_reads_the_candidates():
    """Two builds of one org cannot both read the same open cases: the second waits for the first to finish."""
    import threading

    _wholesale_case("D-T-8")
    out: list[dict] = []
    holder = SessionLocal()
    holder.execute(text("SELECT pg_advisory_xact_lock(hashtext('device_lot.build'))"))
    t = threading.Thread(target=lambda: out.append(call("lot.build", {"org_unit_id": ORG}, "planner.a")))
    t.start()
    t.join(3)
    waiting = t.is_alive()
    holder.commit()
    holder.close()
    t.join(60)
    assert waiting, "lot.build read the candidates without taking the build lock"
    assert not t.is_alive() and out and out[0]["ok"] is True, out


def test_dv_07_f4_the_best_bid_is_of_the_cases_own_org():
    _seed("L-T-7", "LOT-T-0007", org="Customer B")
    today = clock.now().date()
    with SessionLocal() as s:
        assert device_lots.best_net_per_unit(s, "Galaxy S23", "C", today, "Customer B") == 310.0
        assert device_lots.best_net_per_unit(s, "Galaxy S23", "C", today, ORG) is None
        from di.services.device import inputs

        mine = {"imei": "1", "model": "Galaxy S23", "grade": "C", "org": ORG}
        assert inputs.bid_per_unit(s, mine, today) is None
        assert inputs.bid_per_unit(s, mine | {"org": "Customer B"}, today) == 310.0
        assert inputs.bid_per_unit(s, {k: v for k, v in mine.items() if k != "org"}, today) is None  # no owner, no bid


def test_dv_07_f5_approve_refuses_when_the_proposed_bid_is_gone():
    _seed()
    assert call("lot.propose", {"lot_id": "L-T-1"}, "planner.a")["ok"] is True
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM device_bid WHERE bid_id = (SELECT best_bid_id FROM device_lot WHERE id = 'L-T-1')"))
    r = call("lot.approve", {"lot_id": "L-T-1"}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict" and "bid" in r["error"]["message"], r
    assert _lot()["status"] == "proposed"
