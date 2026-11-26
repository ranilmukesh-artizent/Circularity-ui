"""Shared world of the contract refresh path and order tests (plan 9, P9-5.8): three fleet contracts in one org unit, a
refurbished stock and, on request, a safety recall notice. Used by `test_paths_agree_tool_fleet.py` and
`test_order_invariant_tool_fleet.py`. Every test that uses it starts and ends with the demo reset."""

from datetime import date
from typing import Any

from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import unit_reservations
from di.services.canonical import store as canonical
from di.services.cases import refresh_intake, tool_queue
from tests import starting
from tests.helpers import call

ORG = "tool-fleet-a"
TODAY = date(2026, 10, 7)
EOP = (date(2027, 3, 31), "TF-CRH2")  # parts of the CRH end before the next term does: upgrade
MONTHS = {"CMH-A1": 5, "CMH-A2": 14, "CMH-A3": 22, "CMH-A4": 28, "CMH-A5": 33, "CMH-A6": 41}
CONTRACTS: dict[str, tuple[str, list[tuple[str, str, int]]]] = {
    "FC-30117": ("Brightline Mechanical", [(s, "CMH", m) for s, m in MONTHS.items()] + [("CRH-A1", "CRH", 30)]),
    "FC-30121": ("Oakridge Tooling", [("CMH-B1", "CMH", 8), ("CMH-B2", "CMH", 30), ("CMH-B3", "CMH", 36)]),
    "FC-30125": ("Harbor Machining", [("CMH-R1", "CMH", 30), ("CMH-R2", "CMH", 30), ("CMH-R3", "CMH", 34)]),
}
REPLACE = {"recall_id": "RC-2026-P58", "tool_class": "CMH", "serial_from": "CMH-R1", "serial_to": "CMH-R1", "remedy": "replace",
           "affected_parts": ["Motor"], "status": "active"}  # fmt: skip
STOCK_RUL = {"RU-0": 50, "RU-1": 51, "RU-2": 52, "RU-3": 53, "RU-4": 54, "RU-5": 55, "RU-6": 56, "RU-7": 57}


def facts(contract_ids: list[str] | None = None, charge_on: str | None = None) -> list[canonical.Fact]:
    out: list[canonical.Fact] = []
    for cid, (customer, lines) in CONTRACTS.items():
        if contract_ids is not None and cid not in contract_ids:
            continue
        c = {"contract_id": cid, "customer": customer, "market": "US", "start_date": "2024-01-05", "end_date": "2027-01-05",
             "term_months": 36, "status": "active"}  # fmt: skip
        out += [canonical.Fact("contract", cid, k, v, resource="contracts") for k, v in c.items()]
        for serial, cls, months in lines:
            f = {"contract_id": cid, "serial": serial, "tool_class": cls, "model": f"{cls}-12 Pro", "fee_month": 55.0,
                 "months_on_contract": months, "status": "on_contract", "line_id": "FL-" + serial}  # fmt: skip
            if serial == charge_on:
                f |= {"damage_charge_open": True, "charge_ref": "DC-5801"}
            out += [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in f.items()]
    return out


def forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract', 'contract_line', 'recall')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line', 'recall')"))
        conn.execute(text("DELETE FROM job WHERE kind IN ('refresh.scan', 'work.sla', 'case.replan')"))
        conn.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM work_item WHERE org_unit_id = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM unit_reservation WHERE org_unit_id = :o"), {"o": ORG})


def notice(n: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "recall", [canonical.Fact("recall", n["recall_id"], k, v, resource="notices") for k, v in n.items()])
        s.commit()


def world(
    monkeypatch, stock: dict[str, int] | None = None, charge_on: str | None = None, only: list[str] | None = None
) -> dict[str, str]:
    """The org unit, the contracts and a refresh case for each; the case id by contract id. `stock` (unit id -> life left)
    may be changed by the test after this returns: the stub reads it on every call."""
    starting.reset()
    call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")  # once per test
    forget()
    units = STOCK_RUL if stock is None else stock
    monkeypatch.setattr(
        unit_reservations, "stock", lambda s: [{"id": k, "cls": "CMH", "rul": v, "grade": "A"} for k, v in units.items()]
    )
    real = tool_queue.plm.end_of_parts
    monkeypatch.setattr(tool_queue.plm, "end_of_parts", lambda s, o, k: EOP if k == "CRH" else real(s, o, k))
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts(only, charge_on))
        s.commit()
    with SessionLocal() as s:
        ids = refresh_intake.scan(s, ORG, TODAY)
        by = {}
        for i in ids:
            by[str(s.execute(text("SELECT data ->> 'contract_id' FROM case_record WHERE id = :i"), {"i": i}).scalar())] = i
        s.commit()
    assert sorted(by) == sorted(only or CONTRACTS), by
    return by


def reeval(cid: str) -> None:
    """Value the case again through the actions: submitted, declined back (the stage `case.reevaluate` starts from), then
    re-evaluated."""
    for action, data, who in (
        ("decision.submit", {}, "admin"),
        ("decision.decline", {"reason": "Check again."}, "admin"),
        ("case.reevaluate", {}, "admin"),
    ):
        r = call(action, {"case_id": cid, **data}, who)
        assert r["ok"], (action, r)
