"""Plan 9, P9-4.4 (story SD-02): an estimate from similar past repairs on every line of a service-desk case.

The estimate is computed (di.services.models.cost, a pure model, never a language model); this file drives it from the table
`repair_history` and the market tables, through the case a ticket opens. The rows are seeded here as the `rephist` sync would
land them; the figures a test expects are worked again in the test from the same rows and the pack's rate cards. A draft books
one technician-check item per line for the Engineer role.

It starts and ends with the demo reset.
"""

import json
import statistics
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import service_tickets
from di.services.actions.registry import ACTIONS
from di.services.cases import store
from di.services.modeler.tables import market_spec
from di.services.models import cost
from di.services.service_desk import estimate as est
from di.services.service_desk import intake as sd
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

D = Decimal
ORG = "tool-fleet-a"
AS_OF = date(2026, 10, 7)


def _line(serial: str, cls: str, age: int, fault: str = "MOT") -> dict:
    return {"serial": serial, "model_class": cls, "age_months": age, "fault_code": fault, "fault_text": "Runs hot",
            "cover_type": "fleet", "cover_until": "2027-06-30"}  # fmt: skip


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM service_ticket"))
        conn.execute(text("DELETE FROM repair_history"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _ticket(number: str, lines: list[dict], market: str = "US") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
                "loaner_promised, opened_at, source) VALUES (:n, :o, 'ACC-US-0042', :m, 'Austin', NULL, CAST(:l AS jsonb), "
                "'Site manager', false, '2026-10-07T09:00:00+00:00', 'sdesk')"
            ),
            {"n": number, "o": ORG, "m": market, "l": json.dumps(lines)},
        )
    for x in lines:
        tool_case_facts(x["serial"], {"cls": x["model_class"]})


def _history(rows: list[dict]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, "
                "labour_hours, test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES (:id, :org, NULL, "
                ":cls, :age, :fault, :market, CAST(:parts AS jsonb), :hours, false, 5, 0, 'USD', :closed, 'rephist')"
            ),
            [{"org": ORG, "market": "US", "age": 18, "fault": "MOT", "cls": "CRH", "parts": [], "hours": 2.0,
              "closed": date(2026, 3, 1), **r} | {"parts": json.dumps(r.get("parts", []))} for r in rows],
        )  # fmt: skip


def _crh_rows(n: int, prefix: str = "T", **over: object) -> list[dict]:
    """n CRH MOT repairs of 13-24 months: one motor, a chuck on every sixth, 2.0 to 2.5 hours, closed in the 3 years."""
    out = []
    for i in range(n):
        parts = [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}] + ([{"PART_NUMBER": "CRH-2", "QUANTITY": 1}] if i % 6 == 0 else [])
        out.append({"id": f"RH-{prefix}{i}", "parts": parts, "hours": 2.0 + 0.25 * (i % 3),
                    "closed": date(2023, 10, 7) + timedelta(days=i * 5), **over})  # fmt: skip
    return out


def _open(number: str) -> dict:
    with SessionLocal() as s:
        row = next(t for t in service_tickets.pending(s, ORG) if t.number == number)
        c = sd.open_from_ticket(s, row, "system")
        s.commit()
    return c


def _items(case_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT kind, type, title, owner_role, status FROM work_item WHERE case_id = :c AND type = 'technician_check'"),
            {"c": case_id},
        )
        return [dict(r._mapping) for r in rows]


def _cents(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), ROUND_HALF_UP)


# ------------------------------------------------------------------ 186 matches
def test_sd_02_estimate_from_186_matches():
    spec = market_spec("tool_fleet")
    assert spec is not None
    prices = spec.table("parts").versions[1].values["US"]  # the October card, version 2
    motor, chuck = D(str(prices["CRH.Brushless motor"])), D(str(prices["CRH.Chuck assembly"]))
    rate = D(str(spec.table("labour").versions[0].values["US"]["per_hour"]))
    fee = D(str(spec.table("terms").versions[0].values["US"]["test_fee"]))
    rows = _crh_rows(180) + _crh_rows(6, prefix="S", org=None)  # six shared rows count too
    for i, r in enumerate(rows[180:]):
        r["closed"] = date(2025, 1, 1) + timedelta(days=i)
    noise = (
        _crh_rows(5, "O", org="other-org")  # another org's rows
        + _crh_rows(5, "F", closed=date(2026, 10, 8))  # closed after the ticket
        + _crh_rows(5, "P", closed=date(2023, 10, 6))  # closed before the 3 years
        + _crh_rows(5, "G", fault="GBX")  # another fault
        + _crh_rows(5, "C", cls="DCD")  # another class
        + _crh_rows(9, "A", age=40)  # another age band
    )
    _history(rows + noise)
    _ticket("CS0010042", [_line("CRH-46042", "CRH", 18)])
    c = _open("CS0010042")
    e = c["serviceDesk"]["lines"][0]["estimate"]
    assert e["n"] == 186 and e["key_used"] == "class_fault_age" and e["auto"] is True and e["currency"] == "USD"
    parts = [motor + (chuck if i % 6 == 0 else 0) for r in rows for i in [int(r["id"].split("-")[1][1:])]]
    hours = [D(str(r["hours"])) for r in rows]
    totals = sorted(p + hh * rate + fee for p, hh in zip(parts, hours, strict=True))
    q = statistics.quantiles(totals, n=10, method="inclusive")
    point = _cents(statistics.median(parts)) + _cents(statistics.median(hours) * rate) + fee
    assert (D(str(e["point"])), D(str(e["p10"])), D(str(e["p90"]))) == (point, _cents(q[0]), _cents(q[8]))
    assert [ln["label"] for ln in e["lines"]] == ["Parts", "Labour", "Test fee"]
    assert e["lines"][1]["cites"] == "US labour rates v1" and e["lines"][0]["cites"] == "US parts prices v2"
    assert e["confidence"] == 0.8 and e["item"] is None and not _items(c["id"])
    with SessionLocal() as s:  # kept on the case's line snapshot
        assert store.get(s, c["id"])["serviceDesk"]["lines"][0]["estimate"] == e


def test_sd_02_the_case_page_shows_the_estimate():
    _history(_crh_rows(60))
    _ticket("CS0010042", [_line("CRH-46042", "CRH", 18)])
    c = _open("CS0010042")
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    e = r.json()["case"]["serviceDesk"]["lines"][0]["estimate"]
    assert e["n"] == 60 and e["lines"][0]["cites"].startswith("US parts prices v")


# ------------------------------------------------------------------ drafts and the technician check
def test_sd_02_draft_under_50_requests_technician():
    _history(_crh_rows(37, "D", cls="DCD", fault="ELE", age=40))
    _ticket("CS0010043", [_line("DCD-46043", "DCD", 40, "ELE")])
    c = _open("CS0010043")
    e = c["serviceDesk"]["lines"][0]["estimate"]
    assert e["auto"] is False and e["reason"].startswith("37 similar repairs") and e["n"] == 37
    items = _items(c["id"])
    assert len(items) == 1 and items[0]["owner_role"] == "Engineer" and items[0]["kind"] == "needs_info"
    assert items[0]["title"] == "Technician check: post the fault for DCD-46043" and e["item"] is not None
    with SessionLocal() as s:  # evaluated again: no second item
        case = store.get(s, c["id"])
        est.estimate_line(s, case, case["serviceDesk"]["lines"][0], AS_OF)
        est.estimate_case(s, case, AS_OF)
        s.commit()
    assert len(_items(c["id"])) == 1


def test_sd_02_a_batch_books_one_check_per_line():
    _ticket("CS0010044", [_line("CRH-46050", "CRH", 18), _line("CRH-46051", "CRH", 19)])
    c = _open("CS0010044")  # no history at all
    lines = c["serviceDesk"]["lines"]
    assert [x["estimate"]["reason"] for x in lines] == ["No similar repair in 3 years"] * 2
    assert sorted(i["title"] for i in _items(c["id"])) == [
        "Technician check: post the fault for CRH-46050",
        "Technician check: post the fault for CRH-46051",
    ]


def test_sd_02_an_unclear_fault_is_a_draft():
    _history(_crh_rows(60))
    _ticket("CS0010045", [_line("CRH-46052", "CRH", 18, "")])
    c = _open("CS0010045")
    e = c["serviceDesk"]["lines"][0]["estimate"]
    assert e["auto"] is False and e["reason"].startswith("No fault code") and len(_items(c["id"])) == 1


def test_sd_02_a_market_without_cards_is_a_draft_not_a_failure():
    _ticket("CS0010046", [_line("CRH-46053", "CRH", 18)], market="XX")
    c = _open("CS0010046")
    e = c["serviceDesk"]["lines"][0]["estimate"]
    assert e["auto"] is False and e["reason"].startswith("No rate cards for market XX") and len(_items(c["id"])) == 1


# ------------------------------------------------------------------ the pack's parameters, no model, no new action
def test_sd_02_gr_s1_parameters_come_from_the_pack():
    p = est.gr_s1()
    assert (p.min_matches, p.max_width_share, p.window_years) == (50, D("0.30"), 3)


def test_sd_02_computed_not_modelled_and_no_new_action():
    for mod in (est, cost):
        src = Path(str(mod.__file__)).read_text(encoding="utf-8")
        assert "AgentLoop" not in src and "di.services.ask" not in src and "pydantic_ai" not in src
    assert not [a for a in ACTIONS if a.startswith(("estimate.", "repairCost."))]
