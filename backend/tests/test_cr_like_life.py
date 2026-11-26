"""Plan 9, P9-5.3 (story CR-03): like-life units matched and reserved once.

A swapped tool gets the unit whose remaining life is closest to the median of the tools kept; a unit is promised once across
every open contract and the returns queue (`di.services.engine.like_life`, `di.services.cases.tool_queue.refresh_match`, the
planner of I-5, never a language model: there is no model step here, so no `AgentLoop` and no model tests belong to this task,
R16). A reservation is written only on approval (P9-5.5); `unit_reservations.hold` is the write. The refurbished stock is
replaced by the test's own units (the canonical `stock_unit` rows of a synced stack are not read), and the queue tests use
`no_synced_demand`.
"""

from datetime import date

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import unit_reservations
from di.services.actions.registry import ActionError
from di.services.canonical import store as canonical
from di.services.cases import intake, refresh_intake, tool_queue
from di.services.engine import like_life
from di.services.modeler.valuers.contract_refresh import ToolAction
from tests import starting
from tests.helpers import call, tool_case_facts

pytestmark = pytest.mark.usefixtures("no_synced_demand")

ORG = "tool-fleet-ll"
CLASS = "CMH"


def _act(serial: str, action: str, rul: int) -> ToolAction:
    return ToolAction(serial, CLASS, action, "", rul, "High", None, None)  # type: ignore[arg-type]


def _unit(uid: str, rul: int, source: str = "stock") -> like_life.Unit:
    return like_life.Unit(uid, CLASS, rul, source)


def _need(case: str, target: int = 60, serial: str = "S1") -> like_life.Need:
    return like_life.Need(f"{case}:{serial}", case, CLASS, target)


# ------------------------------------------------------------------ the pure match
def test_cr_03_closest_to_fleet_median():
    actions = [_act("K1", "keep", 55), _act("K2", "keep", 60), _act("K3", "keep", 62), _act("X", "swap", 21)]
    assert like_life.target(actions) == 60
    r = like_life.match([_need("RF-1", 60)], [_unit("RU-41", 41), _unit("RU-58", 58), _unit("RU-77", 77)], frozenset())
    assert r.assign == {"RF-1:S1": "RU-58"} and r.unmatched == []


def test_cr_03_target_ignores_swaps_and_upgrades():
    assert (
        like_life.target([_act("K1", "keep", 70), _act("K2", "keep", 50), _act("X", "swap", 10), _act("Y", "upgrade", 99)]) == 50
    )
    assert like_life.target([_act("X", "swap", 10)]) == 100


def test_cr_03_minimum_total_distance_not_first_come():
    # alone, RF-1 (58) would take RU-60; with RF-2 (62) the total is smaller when RF-1 takes RU-40 (18 + 2, not 2 + 22)
    r = like_life.match([_need("RF-1", 58), _need("RF-2", 62)], [_unit("RU-60", 60), _unit("RU-40", 40)], frozenset())
    assert r.assign == {"RF-1:S1": "RU-40", "RF-2:S1": "RU-60"}


def test_cr_03_unit_never_promised_twice_across_contracts():
    r = like_life.match([_need("RF-1"), _need("RF-2")], [_unit("RU-58", 58)], frozenset())
    assert r.assign == {"RF-1:S1": "RU-58"}  # equal needs: the first case id wins, as every caller sees them in that order
    assert r.unmatched == ["RF-2:S1"]
    assert r.why["RF-2:S1"] == "RU-58 (58%) goes to RF-1, which it fits better"


def test_cr_03_stock_before_returns_on_a_tie():
    r = like_life.match([_need("RF-1")], [_unit("RT-9", 58, "return"), _unit("RU-1", 58, "stock")], frozenset())
    assert r.assign == {"RF-1:S1": "RU-1"}


def test_cr_03_only_the_same_class():
    other = like_life.Unit("RU-X", "CRH", 60, "stock")
    r = like_life.match([_need("RF-1")], [other], frozenset())
    assert r.unmatched == ["RF-1:S1"] and r.why["RF-1:S1"] == "no CMH unit in refurbished stock or planned from returns"


def test_cr_03_reserved_unit_not_offered():
    r = like_life.match([_need("RF-1")], [_unit("RU-58", 58), _unit("RU-77", 77)], frozenset({"RU-58"}))
    assert r.assign == {"RF-1:S1": "RU-77"}
    r = like_life.match([_need("RF-1")], [_unit("RU-58", 58)], frozenset({"RU-58"}))
    assert r.unmatched == ["RF-1:S1"] and r.why["RF-1:S1"] == "every CMH unit is reserved"


# ------------------------------------------------------------------ the reservation
def _release() -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM unit_reservation WHERE unit_id LIKE 'LL-%' OR org_unit_id = :o"), {"o": ORG})


@pytest.fixture
def reservations():
    _release()
    yield
    _release()


def test_unit_reservation_unique_held(reservations):
    with SessionLocal() as s:
        unit_reservations.hold(s, "LL-1", "RF-1", "RF-1:S1", "approver", "workspace")
        s.commit()
    with SessionLocal() as s:
        with pytest.raises(ActionError) as e:
            unit_reservations.hold(s, "LL-1", "RF-2", "RF-2:S1", "approver", "workspace")
        assert e.value.code == "conflict" and e.value.message == "LL-1 is already reserved for RF-1"
        s.rollback()


def test_cr_03_a_held_reservation_is_read_as_reserved(reservations):
    with SessionLocal() as s:
        unit_reservations.hold(s, "LL-2", "RF-1", "RF-1:S1", "approver", "workspace")
        s.commit()
    with SessionLocal() as s:
        reserved = unit_reservations.held(s, "workspace")
        assert "LL-2" in reserved and "LL-2" not in unit_reservations.held(s, ORG)
    assert like_life.match([_need("RF-1")], [_unit("LL-2", 60)], reserved).assign == {}


def test_unit_reservation_released_unit_can_be_held_again(reservations):
    with SessionLocal() as s:
        unit_reservations.hold(s, "LL-3", "RF-1", "RF-1:S1", "approver", "workspace")
        s.execute(text("UPDATE unit_reservation SET status = 'released' WHERE unit_id = 'LL-3'"))
        unit_reservations.hold(s, "LL-3", "RF-2", "RF-2:S1", "approver", "workspace")
        s.commit()


# ------------------------------------------------------------------ across the org's refresh cases and returns queue
def _contract(cid: str, serials: dict[str, int]) -> list[canonical.Fact]:
    c = {"contract_id": cid, "customer": "Brightline Mechanical", "market": "US", "start_date": "2024-01-05",
         "end_date": "2027-01-05", "term_months": 36, "status": "active"}  # fmt: skip
    out = [canonical.Fact("contract", cid, k, v, resource="contracts") for k, v in c.items()]
    for serial, months in serials.items():
        f = {"contract_id": cid, "serial": serial, "tool_class": CLASS, "model": "CMH-12 Pro", "fee_month": 55.0,
             "months_on_contract": months, "status": "on_contract", "line_id": "FL-" + serial}  # fmt: skip
        out += [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in f.items()]
    return out


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract', 'contract_line', 'condition')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line', 'condition')"))
        conn.execute(text("DELETE FROM job WHERE kind IN ('refresh.scan', 'work.sla', 'case.replan')"))
        conn.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM work_item WHERE org_unit_id = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM unit_reservation WHERE org_unit_id = :o"), {"o": ORG})


def _stock(monkeypatch, units: list[tuple[str, int]]) -> None:
    monkeypatch.setattr(unit_reservations, "stock", lambda s: [{"id": u, "cls": CLASS, "rul": r, "grade": "A"} for u, r in units])


@pytest.fixture
def world():
    starting.reset()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet LL"}, "admin")["ok"]
    _forget()
    yield
    _forget()
    starting.reset()


def _scan(*contracts: tuple[str, dict[str, int]]) -> list[str]:
    with SessionLocal() as s:
        for cid, serials in contracts:
            canonical.apply(s, "fleet", _contract(cid, serials))
        s.commit()
    with SessionLocal() as s:
        ids = refresh_intake.scan(s, ORG, date(2026, 10, 7))
        s.commit()
    return sorted(ids)


def test_cr_03_two_contracts_one_unit_reserve_it_once(world, monkeypatch):
    # each contract has one old tool (41 months: swap) and one new one (5 months: keep)
    ids = _scan(("FC-LL-1", {"LL-A0": 41, "LL-A1": 5}), ("FC-LL-2", {"LL-B0": 41, "LL-B1": 5}))
    assert len(ids) == 2
    _stock(monkeypatch, [("RU-7001", 58)])
    with SessionLocal() as s:
        m = tool_queue.refresh_match(s, ORG)
    got = [r for rows in m.values() for r in rows]
    assert len(got) == 2
    winners = [r for r in got if r["unit_id"] == "RU-7001"]
    losers = [r for r in got if r["unit_id"] is None]
    assert len(winners) == 1 and len(losers) == 1
    assert [r["unit_id"] for r in m[ids[0]]] == ["RU-7001"] and winners[0]["source"] == "stock"  # the first case id wins a tie
    assert ids[0] in losers[0]["why"] and "RU-7001" in losers[0]["why"]
    # a unit held for the winner is offered to no one, the loser's case included
    with SessionLocal() as s:
        unit_reservations.hold(s, "RU-7001", ids[0], winners[0]["need_id"], "approver", ORG)
        s.commit()
    with SessionLocal() as s:
        m2 = tool_queue.refresh_match(s, ORG)
    assert [r["unit_id"] for rows in m2.values() for r in rows] == [None, None]


def test_cr_03_unit_never_promised_twice_with_returns_queue(world, monkeypatch):
    (case,) = _scan(("FC-LL-3", {"LL-C0": 41, "LL-C1": 5}))
    _stock(monkeypatch, [])
    pool = {"kind": "proj", "id": "TPR-LL", "who": "Atlanta tool pool", "site": "Atlanta", "need": 60, "rental": 1500,
            "quote": "PR-LL", "what": "Tool pool request TPR-LL", "when": "raised 29 Oct"}  # fmt: skip
    facts = tool_case_facts(
        "RT-LL1", {"cls": CLASS, "grade": "A", "ft": "Repair center", "site": "Houston", "rul": 62, "dem": {"proj": pool}}
    )
    graded = (("grade", "A"), ("test_result", "pass"), ("graded_at", "2026-10-01T00:00:00Z"), ("inspection_ref", "INS-LL"))
    with SessionLocal() as s:
        canonical.apply(s, "repairlog", [canonical.Fact("condition", "RT-LL1", k, v) for k, v in graded])
        rid = intake.open_case(
            s,
            {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": "RT-LL1", "reason": "manual", "facts": facts},
            "system",
        )["id"]
        s.commit()
    with SessionLocal() as s:
        (row,) = tool_queue.refresh_match(s, ORG)[case]
    # the return is planned for the pool request or for the refresh swap, never both
    by_swap = row["unit_id"] == rid
    assert by_swap != ("planned for" in (row["why"] or "")), row
    if by_swap:
        assert row["source"] == "return" and row["rul"] in (62, 82)  # as it is, or refurbished (+20 points)
