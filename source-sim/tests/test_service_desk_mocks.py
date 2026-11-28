"""Plan 9, P9-4.1: the service desk mocks. ServiceNow gains the customer service case and upgrade offer tables; Oracle
Depot Repair gains `repair_history` and its read method `get_repair_history/`. All values are synthetic (account codes
only, no names). Each system is reset on its own."""

import json
from collections import Counter
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from sim.main import app
from sim.vendors.depot_repair import history

SN = "/servicenow/api/now/table"
SN_AUTH = ("di.integration", "Circularity-demo-sn-1")
Q = "/depot-repair/webservices/rest/xxcsdroquery"
DR_AUTH = ("DI_CONNECTOR", "repair-demo-password")


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.post("/_sim/reset", params={"system": "fsm"}).raise_for_status()
    c.post("/_sim/reset", params={"system": "repair"}).raise_for_status()
    return c


def sn_rows(client, table: str, **params) -> list[dict]:
    r = client.get(f"{SN}/{table}", auth=SN_AUTH, params={"sysparm_limit": 5000, **params})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def history_page(client, **params) -> dict:
    r = client.get(Q + "/get_repair_history/", auth=DR_AUTH, params=params)
    assert r.status_code == 200, r.text
    out = r.json()["OutputParameters"]
    assert out["X_RETURN_STATUS"] == "S", out
    return out


def items(out: dict) -> list[dict]:
    return out["X_REPAIR_HISTORY"]["X_REPAIR_HISTORY_ITEM"]


def test_repair_history_counts_match_samples():
    rows = history.generate(seed=26110)
    assert rows == history.generate(seed=26110)  # deterministic
    n = Counter((r["MODEL_CLASS"], r["FAULT_CODE"], history.age_band(r["AGE_MONTHS"])) for r in rows if r["REPAIR_TYPE"] == "Repair and Return")
    assert n[("CRH", "MOT", "13-24")] == 186
    assert n[("DCD", "ELE", "37+")] == 37
    assert all(date(2023, 10, 7) <= date.fromisoformat(r["DATE_CLOSED"][:10]) <= date(2026, 10, 6) for r in rows)
    refurb = Counter(r["MODEL_CLASS"] for r in rows if r["REPAIR_TYPE"] == "Refurbishment" and r["RELEASE_TO_SERVICE"] and not r["ISSUED"])
    assert refurb == {c: 30 for c in ("CMH", "BRK", "DCD", "CRH", "AGR", "LSR")}
    assert 5500 <= len(rows) <= 6500
    first = rows[0]
    assert first["REPAIR_NUMBER"].startswith("RH-") and {p["PART_NUMBER"] for r in rows for p in r["PARTS"]} >= {"CRH-0", "CRH-2"}
    assert history.fault_parts("CRH", "MOT") == [0]


def test_sample_cell_is_narrow_enough_to_price_without_a_technician():
    # CS0010042 (CRH, MOT, 18 months) is priced without a technician in the plan-9 demo: GR-S1 wants (p90 - p10) / point
    # <= 30 %. The cell's labour is 2.0 to 2.5 h (1.0 to 3.5 h gave 42 %, smoke-p9-4 step 3), at a fixed rate and fee.
    import statistics

    rows = history.generate(seed=26110)
    key = ("CRH", "MOT", "13-24")
    fixed = [r for r in rows if r["REPAIR_TYPE"] == "Repair and Return"]
    cell = [r for r in fixed if (r["MODEL_CLASS"], r["FAULT_CODE"], history.age_band(r["AGE_MONTHS"])) == key]
    assert len(cell) == 186 and {r["LABOUR_HOURS"] for r in cell} <= {2.0, 2.25, 2.5}
    price = dict(enumerate(p for _, p in history.PARTS["CRH"]))
    parts = [sum(price[int(p["PART_NUMBER"].split("-")[1])] for p in r["PARTS"]) for r in cell]
    totals = sorted(x + r["LABOUR_HOURS"] * 58 + 14 for x, r in zip(parts, cell, strict=True))
    q = statistics.quantiles(totals, n=10, method="inclusive")
    assert (q[8] - q[0]) / statistics.median(totals) <= 0.30
    # every other cell keeps its rows: the same random draws, so the counts and the other cells' hours are as before
    mine = {r["REPAIR_NUMBER"] for r in cell}
    other = [r["LABOUR_HOURS"] for r in fixed if r["REPAIR_NUMBER"] not in mine]
    assert min(other) == 1.0 and max(other) == 3.5


def test_get_repair_history_pages_and_filters(client):
    first = history_page(client, P_MODEL_CLASS="CRH", P_FAULT_CODE="MOT", P_MAX_RECORDS=500)
    total = int(first["X_TOTAL_COUNT"])
    assert total > 500 and len(items(first)) == 500 and first["X_HAS_MORE"] == "Y"
    second = history_page(client, P_MODEL_CLASS="CRH", P_FAULT_CODE="MOT", P_MAX_RECORDS=500, P_START_INDEX=501)
    assert len(items(second)) == total - 500 and second["X_HAS_MORE"] == "N"
    every = items(first) + items(second)
    assert {r["MODEL_CLASS"] for r in every} == {"CRH"} and {r["FAULT_CODE"] for r in every} == {"MOT"}
    assert sum(1 for r in every if history.age_band(r["AGE_MONTHS"]) == "13-24") == 186
    late = history_page(client, P_MODEL_CLASS="CRH", P_FAULT_CODE="MOT", P_DATE_CLOSED_FROM="2026-01-01", P_MAX_RECORDS=500)
    assert 0 < int(late["X_TOTAL_COUNT"]) < total and all(r["DATE_CLOSED"][:10] >= "2026-01-01" for r in items(late))
    changed = history_page(client, P_MODEL_CLASS="CRH", P_LAST_UPDATE_DATE_FROM="2026-09-01T00:00:00Z", P_MAX_RECORDS=500)
    assert 0 < int(changed["X_TOTAL_COUNT"]) < int(history_page(client, P_MODEL_CLASS="CRH")["X_TOTAL_COUNT"])
    r = client.get(Q + "/get_repair_history/", auth=DR_AUTH, params={"P_MAX_RECORDS": 501})
    assert r.status_code == 400


def test_get_repair_orders_is_unchanged(client):
    r = client.get(Q + "/get_repair_orders/", auth=DR_AUTH, params={"P_MAX_RECORDS": 500})
    got = r.json()["OutputParameters"]["X_REPAIR_ORDERS"]["X_REPAIR_ORDERS_ITEM"]
    assert got and not [x for x in got if x["REPAIR_NUMBER"].startswith("RH-")]
    assert all(x["REPAIR_NUMBER"].startswith("RO-") for x in got)


def test_tickets_and_offers_seeded(client):
    tickets = sn_rows(client, "sn_customerservice_case")
    by = {t["number"]: t for t in tickets}
    assert sum(1 for t in tickets if t["state"] == "1") == 40 and {"CS0010042", "CS0010050"} <= set(by)
    one = by["CS0010042"]
    lines = json.loads(one["u_lines"])
    assert (one["u_market"], one["u_batch_id"], one["u_requester_role"], one["state"]) == ("US", "", "Site manager", "1")
    assert len(lines) == 1 and lines[0]["model_class"] == "CRH" and lines[0]["fault_code"] == "MOT"
    assert lines[0]["age_months"] == 18 and lines[0]["cover_type"] == "fleet" and one["u_loaner_promised"] == "false"
    batch = by["CS0010050"]
    lines = json.loads(batch["u_lines"])
    assert len(lines) == 22 and batch["u_site"] == "Denver" and batch["u_requester_role"] == "Fleet desk" and batch["u_batch_id"]
    nominal_life = 60  # months; "past 50% of life" is age over 30 months here
    none = [x for x in lines if x["cover_type"] == "none"]
    assert sum(1 for x in none if x["age_months"] > nominal_life / 2) == 9
    assert sum(1 for x in none if x["age_months"] <= nominal_life / 2) == 11
    assert sum(1 for x in lines if x["cover_type"] == "fleet" and x["model_class"] == "CRH") == 2
    assert all(isinstance(x["serial"], str) and x["cover_until"] is not None for x in lines)
    offers = sn_rows(client, "u_upgrade_offer")
    assert len(offers) == 2400
    mine = [o for o in offers if o["account"] == "ACC-US-0042"]
    assert len(mine) == 14 and sum(1 for o in mine if o["u_accepted"] == "true") == 4
    assert min(o["u_offered_at"][:10] for o in offers) >= "2024-10-07" and max(o["u_offered_at"][:10] for o in offers) <= "2026-10-07"
    assert {o["u_market"] for o in offers} <= {"DE", "UK", "US", "AU", "FR"}


def test_take_up_rises_with_credit(client):
    offers = sn_rows(client, "u_upgrade_offer")
    low = [o for o in offers if float(o["u_credit_pct"]) < 0.15]
    high = [o for o in offers if float(o["u_credit_pct"]) >= 0.30]
    assert len(low) > 100 and len(high) > 100
    rate = lambda rows: sum(1 for o in rows if o["u_accepted"] == "true") / len(rows)  # noqa: E731
    assert rate(high) > rate(low) + 0.3
    assert all(float(o["u_credit_amount"]) >= 0 and o["u_currency"] for o in offers)
    assert datetime.fromisoformat(offers[0]["u_offered_at"].replace(" ", "T"))
