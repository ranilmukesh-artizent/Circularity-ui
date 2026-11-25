"""Plan 9, P9-4.6 (story SD-04): the three options of a ticket (fix, covered swap, upgrade) on the case a ticket opens.

The valuer's formulas are worked in test_valuer_service_desk.py; this file drives the whole path: the estimate (P9-4.4), the
approved market tables (P9-4.2), the refurbished stock and the past offers (P9-4.1) gathered by
`di.services.service_desk.inputs`, `decide_case` (I-6) dispatching the ticket to the service-desk valuer, the approval holds
that I-10 and I-11 read, and the case page.
No model step (R16): no model tests. No new action, so nothing joins FORBIDDEN_ACTIONS.

It starts and ends with the demo reset.
"""

import json
import math
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import service_tickets
from di.services.actions.standing_policy import _guardrail_holds
from di.services.agents.forbidden import forbidden
from di.services.cases import intake, store
from di.services.modeler.valuers.tool_fleet import CLS
from di.services.service_desk import intake as sd
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "tool-fleet-a"
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract_line', 'contract', 'recall')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract_line', 'contract', 'recall')"))
        for t in ("service_ticket", "repair_history", "refurb_unit", "upgrade_offer"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean()


def _line(serial="CRH-46042", cls="CRH", age=18, cover="fleet") -> dict:
    return {
        "serial": serial,
        "model_class": cls,
        "age_months": age,
        "fault_code": "MOT",
        "fault_text": "Runs hot",
        "cover_type": cover,
        "cover_until": "2027-06-30",
    }


def _ticket(number: str, lines: list[dict], account="ACC-US-0042") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
                "loaner_promised, opened_at, source) VALUES (:n, :o, :a, 'US', 'Austin', NULL, CAST(:l AS jsonb), "
                "'Site manager', false, '2026-10-07T09:00:00+00:00', 'sdesk')"
            ),
            {"n": number, "o": ORG, "a": account, "l": json.dumps(lines)},
        )
    for x in lines:
        tool_case_facts(x["serial"], {"cls": x["model_class"]})


def _history(n: int = 60, hours: float = 2.0) -> None:
    rows = [{"id": f"RH-{i}", "closed": date(2023, 10, 7) + timedelta(days=i * 5), "days": 4 + i % 3} for i in range(n)]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, "
                "labour_hours, test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES (:id, :org, NULL, "
                "'CRH', 18, 'MOT', 'US', CAST('[{\"PART_NUMBER\": \"CRH-0\", \"QUANTITY\": 1}]' AS jsonb), :h, false, :days, 0, "
                "'USD', :closed, 'rephist')"
            ),
            [{"org": ORG, "h": hours, **r} for r in rows],
        )


def _stock(n: int, cls: str = "CRH") -> None:
    with engine.begin() as conn:
        for i in range(n):
            conn.execute(
                text(
                    "INSERT INTO refurb_unit (serial, org_unit_id, model_class, grade, market, released_on) "
                    "VALUES (:s, :o, :c, 'A', 'US', '2026-09-01')"
                ),
                {"s": f"R-{cls}-{i}", "o": ORG, "c": cls},
            )


def _open(number: str) -> dict:
    with SessionLocal() as s:
        row = next(t for t in service_tickets.pending(s, ORG) if t.number == number)
        c = sd.open_from_ticket(s, row, "system")
        s.commit()
    with SessionLocal() as s:
        return store.get(s, c["id"])


def _opts(c: dict, line: int = 0) -> dict[str, dict]:
    return {o["k"]: o for o in c["serviceDesk"]["lines"][line]["options"]}


def test_sd_04_options_on_the_case_and_every_line_cites_its_table():
    _history()
    _stock(2)
    _ticket("CS0010042", [_line()])
    c = _open("CS0010042")
    o = _opts(c)
    assert set(o) == {"fix", "swap", "upgrade"} and all(x["eligible"] for x in o.values())  # fleet cover CRH, 50% of life
    assert o["fix"]["days"] == 5 and o["fix"]["customer_price"] == 0 and o["swap"]["days"] == 2 and o["upgrade"]["days"] == 3
    cites = {v["cites"] for x in o.values() for v in x["lines"]}
    assert {"US terms v1", "US labour rates v1", "US cover terms v1", "US credit rules v1"} <= cites
    assert any(x.startswith("US parts prices v") for x in cites)
    assert [r["id"] for r in c["routes"]] == ["fix", "swap", "upgrade"]
    assert c["serviceDesk"]["lines"][0]["best"] == max(o.values(), key=lambda x: x["expected_margin"])["k"]


def test_sd_04_swap_waits_for_stock_and_cover():
    _history()
    _ticket("CS0010042", [_line()])
    swap = _opts(_open("CS0010042"))["swap"]
    assert not swap["eligible"] and swap["why"] == f"No refurbished {CLS['CRH']['name']} in stock"
    _ticket("CS0010043", [_line("CRH-46043", cover="none")])
    _stock(1)
    o = _opts(_open("CS0010043"))
    assert o["swap"]["why"] == "Covered swap is not allowed: No cover" and o["fix"]["customer_price"] > 0


def test_sd_04_account_shift_moves_the_take_up_after_ten_offers():
    _history()
    _ticket("CS0010042", [_line()])
    base = _opts(_open("CS0010042"))["upgrade"]["take_up"]
    rows = [{"id": f"UO-{i}", "acc": i < 10, "a": "ACC-US-0042" if i < 12 else "ACC-OTHER"} for i in range(24)]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO upgrade_offer (id, org_unit_id, account, market, model_class, offered_on, credit_pct, "
                "credit_amount, currency, accepted, source) "
                "VALUES (:id, :o, :a, 'US', 'CRH', '2026-03-01', 0.2, 100, 'USD', :acc, 'sdesk')"
            ),
            [{"o": ORG, **r} for r in rows],
        )
    _ticket("CS0010044", [_line("CRH-46044")])
    up = _opts(_open("CS0010044"))["upgrade"]["take_up"]
    k, n, base_share = 10, 12, 10 / 24  # the account took 10 of its 12 offers; the market 10 of 24
    shift = math.log(((k + 1) / (n + 2)) / (1 - (k + 1) / (n + 2))) - math.log(base_share / (1 - base_share))
    expect = 1 / (1 + math.exp(-(-3.2 + shift + 9.0 * 0.2)))
    assert up != base and abs(up - expect) < 1e-3


def test_sd_04_a_fix_over_600_usd_holds_for_the_fleet_manager_and_i11_reads_it():
    _history(hours=18.0)  # 18 h at $58 plus parts, well over $600
    _ticket("CS0010042", [_line(age=10, cover="none")])  # no cover, 28% of life: the fix is the only option
    c = _open("CS0010042")
    o = _opts(c)
    assert o["fix"]["cost"] > 600 and not o["swap"]["eligible"] and not o["upgrade"]["eligible"]
    assert [x["id"] for x in c["approvalHolds"]] == ["GR-14"] and c["approvalHolds"][0]["owner"] == "Fleet manager"
    assert _guardrail_holds(c) == ["GR-14"]  # the standing policy (I-11) sees the hold the pipeline's policy (I-10) reads


def test_sd_04_gr_s3_a_stale_cited_table_holds_the_case():
    _history()
    _ticket("CS0010042", [_line()])
    c = _open("CS0010042")
    with SessionLocal() as s:
        case = store.get(s, c["id"])
        case["serviceDesk"]["lines"][0]["estimate"]["lines"][0]["cites"] = "US parts prices v1"
        intake.revalue(s, case)
        store.save(s, case)
        s.commit()
        holds = case.get("approvalHolds") or []
    assert [x["id"] for x in holds] == ["GR-S3"]
    assert holds[0]["reason"] == "Prices must come from the market's current approved table (GR-S3)"


def test_sd_04_the_case_page_shows_options_and_the_approval_owner():
    _history()
    _stock(1)
    _ticket("CS0010042", [_line()])
    c = _open("CS0010042")
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    v = r.json()["case"]["serviceDesk"]
    assert {o["k"] for o in v["lines"][0]["options"]} == {"fix", "swap", "upgrade"}
    assert "approval" in v and v["approval"]["owner"]


def test_sd_04_agents_still_cannot_approve_what_the_options_recommend():
    assert forbidden("decision.approve") and forbidden("decision.override")
