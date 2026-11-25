# ruff: noqa: E501
"""Plan 9, P9-4.1: the service desk sources `sdesk` (ServiceNow customer service cases and upgrade offers) and `rephist`
(Oracle Depot Repair's closed repairs and released refurbished units), against source-sim's synthetic mocks.

Both are extra systems: no demo source, so they start unregistered (no source_system row) and every demo screen and
count is unchanged. They write plain tables (service_ticket, upgrade_offer, repair_history, refurb_unit), not canonical
facts. The repositories read them. The sync tests need source-sim running with the new tables and method (restart it
after the change, R14) and are skipped, with the reason, when it lacks them.
"""

from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import text

from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core import golden
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.repositories import refurb_stock, repair_history, service_tickets, upgrade_offers
from tests import starting
from tests.helpers import call, client, h

SIM = get_settings().source_sim_url
DEMO_IDS = {s["id"] for s in golden.load("sources")["sources"]}
SN_AUTH = ("di.integration", "Circularity-demo-sn-1")
DR_AUTH = ("DI_CONNECTOR", "repair-demo-password")
WINDOW = (date(2023, 10, 7), date(2026, 10, 7))
TABLES = ("repair_history", "upgrade_offer", "refurb_unit", "service_ticket")


def served() -> bool:
    try:
        a = httpx.get(SIM + "/servicenow/api/now/table/u_upgrade_offer", auth=SN_AUTH, params={"sysparm_limit": 1}, timeout=10)
        b = httpx.get(SIM + "/depot-repair/webservices/rest/xxcsdroquery/get_repair_history/", auth=DR_AUTH, timeout=10)
        return a.status_code == 200 and b.status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the service desk mocks: restart it (R14)")


def count(table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608 - fixed names


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


# ------------------------------------------------------------------ registration and reset
def test_extra_adapters_start_unregistered():
    assert ADAPTERS["sdesk"].extra and ADAPTERS["rephist"].extra
    with engine.connect() as conn:
        ids = set(conn.execute(text("SELECT id FROM source_system")).scalars())
    assert ids == DEMO_IDS and len(ids) == 21 and not {"sdesk", "rephist"} & ids
    for sid in ("sdesk", "rephist"):
        assert run_sync(sid, "manual")["status"] == "skipped"
    rows = client.get("/api/screens/integration/sources", headers=h("developer")).json()["sources"]
    assert {r["id"] for r in rows} == DEMO_IDS


def test_the_reset_clears_the_service_desk_tables():
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO refurb_unit (serial, model_class, grade, market, released_on) VALUES ('X-1','CRH','A','US','2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO upgrade_offer (id, account, market, offered_on, accepted) VALUES ('o1','ACC-US-1','US','2026-01-01',false)"
            )
        )
        conn.execute(text("INSERT INTO service_ticket (number, lines, opened_at) VALUES ('CS1','[]','2026-01-01')"))
        conn.execute(text("INSERT INTO repair_history (id, closed_on) VALUES ('RH-1','2026-01-01')"))
    assert all(count(t) == 1 for t in TABLES)
    starting.reset()
    assert [count(t) for t in TABLES] == [0, 0, 0, 0]


# ------------------------------------------------------------------ repositories (rows inserted by hand)
def _history(rows: list[tuple]) -> None:
    with engine.begin() as conn:
        for i, (org, cls, fault, age, closed) in enumerate(rows):
            conn.execute(
                text(
                    "INSERT INTO repair_history (id, org_unit_id, serial, model_class, age_months, fault_code, market, parts, "
                    "labour_hours, test_fee, turnaround_days, actual_cost, currency, closed_on, source) VALUES "
                    '(:i, :o, :s, :c, :a, :f, \'US\', \'[{"PART_NUMBER": "CRH-0", "QUANTITY": 1}]\', 1.5, false, 5, 210.00, '
                    "'USD', :d, 'rephist')"
                ),
                {"i": f"T-{i}", "o": org, "s": f"S-{i}", "c": cls, "a": age, "f": fault, "d": closed},
            )


def test_similar_widens_without_age_band():
    starting.reset()
    _history(
        [
            (None, "CRH", "MOT", 5, "2025-01-01"),
            (None, "CRH", "MOT", 18, "2025-02-01"),
            (None, "CRH", "MOT", 30, "2025-03-01"),
            (None, "CRH", "MOT", 40, "2026-10-07"),  # closed on `until`: outside [since, until)
            (None, "CRH", "ELE", 18, "2025-02-01"),
            (None, "DCD", "MOT", 18, "2025-02-01"),
            ("Customer A", "CRH", "MOT", 20, "2025-04-01"),
            ("Customer B", "CRH", "MOT", 21, "2025-04-02"),
        ]
    )
    with SessionLocal() as s:
        banded = repair_history.similar(s, None, "CRH", "MOT", "13-24", *WINDOW)
        wide = repair_history.similar(s, None, "CRH", "MOT", None, *WINDOW)
        mine = repair_history.similar(s, "Customer A", "CRH", "MOT", None, *WINDOW)
    assert sorted(r.age_months for r in banded) == [18]
    assert sorted(r.age_months for r in wide) == [5, 18, 30]  # shared rows only; Customer rows are not shared
    assert sorted(r.age_months for r in mine) == [5, 18, 20, 30]  # the org's rows and the shared ones
    row = banded[0]
    assert (row.model_class, row.fault_code, row.closed_on, row.currency) == ("CRH", "MOT", date(2025, 2, 1), "USD")
    assert row.parts == [{"PART_NUMBER": "CRH-0", "QUANTITY": 1}] and row.actual_cost == 210.0 and row.test_fee is False
    starting.reset()


def test_refurb_stock_counts_and_reserves():
    starting.reset()
    with engine.begin() as conn:
        for i, org in enumerate((None, None, None, "Customer B")):
            conn.execute(
                text(
                    "INSERT INTO refurb_unit (serial, org_unit_id, model_class, grade, market, released_on) VALUES (:s, :o, 'CRH', 'A', 'US', '2026-05-01')"
                ),
                {"s": f"CRH-R{i}", "o": org},
            )
    with SessionLocal() as s:
        assert refurb_stock.available(s, None, "CRH") == 3 and refurb_stock.available(s, "Customer B", "CRH") == 4
        assert refurb_stock.available(s, None, "DCD") == 0
        refurb_stock.reserve(s, "CRH-R0", "RT-1")
        s.commit()
    with SessionLocal() as s:
        assert refurb_stock.available(s, None, "CRH") == 2
    starting.reset()


def test_tickets_pending_have_no_case_yet():
    starting.reset()
    with engine.begin() as conn:
        for n, case in (("CS1", None), ("CS2", "SD-1"), ("CS3", None)):
            conn.execute(
                text(
                    "INSERT INTO service_ticket (number, account, market, site, lines, requester_role, loaner_promised, opened_at, case_id) VALUES (:n, 'ACC-US-0042', 'US', 'Austin', '[{\"serial\": \"CRH-1\"}]', 'Site manager', false, '2026-10-01T09:00:00+00', :c)"
                ),
                {"n": n, "c": case},
            )
    with SessionLocal() as s:
        got = service_tickets.pending(s, None)
    assert [t.number for t in got] == ["CS1", "CS3"] and got[0].lines == [{"serial": "CRH-1"}]
    assert (got[0].account, got[0].market, got[0].batch_id, got[0].loaner_promised) == ("ACC-US-0042", "US", None, False)
    assert got[0].opened_at == datetime(2026, 10, 1, 9, tzinfo=UTC)
    starting.reset()


def test_upgrade_offers_filter_by_account_market_and_dates():
    starting.reset()
    with engine.begin() as conn:
        for i, (acc, mkt, d) in enumerate(
            [
                ("ACC-US-0042", "US", "2026-01-01"),
                ("ACC-US-0042", "US", "2024-01-01"),
                ("ACC-US-0001", "US", "2026-02-01"),
                ("ACC-DE-0001", "DE", "2026-02-01"),
            ]
        ):
            conn.execute(
                text(
                    "INSERT INTO upgrade_offer (id, account, market, model_class, offered_on, credit_pct, credit_amount, currency, accepted, source) VALUES (:i, :a, :m, 'CRH', :d, 0.2, 120.00, 'USD', :x, 'sdesk')"
                ),
                {"i": f"o{i}", "a": acc, "m": mkt, "d": d, "x": i % 2 == 0},
            )
    with SessionLocal() as s:
        every = upgrade_offers.offers(s, None, None, "US", date(2025, 10, 7), date(2026, 10, 7))
        mine = upgrade_offers.offers(s, None, "ACC-US-0042", "US", date(2023, 10, 7), date(2026, 10, 7))
    assert sorted(o.account for o in every) == ["ACC-US-0001", "ACC-US-0042"]
    assert len(mine) == 2 and mine[0].credit_pct == 0.2 and mine[0].accepted in (True, False)
    starting.reset()


# ------------------------------------------------------------------ sync against the mocks
@needs_mock
def test_sdesk_sync_lands_tickets_and_offers():
    r = call("source.reconnect", {"source_id": "sdesk"}, "developer")
    assert r["ok"], r
    out = run_sync("sdesk", "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    assert (count("service_ticket"), count("upgrade_offer")) == (40, 2400)
    with SessionLocal() as s:
        pending = {t.number: t for t in service_tickets.pending(s, None)}
        mine = upgrade_offers.offers(s, None, "ACC-US-0042", "US", *WINDOW)
    assert {"CS0010042", "CS0010050"} <= set(pending) and len(pending["CS0010050"].lines) == 22
    assert pending["CS0010042"].lines[0]["model_class"] == "CRH" and pending["CS0010042"].batch_id is None
    assert len(mine) == 14 and sum(o.accepted for o in mine) == 4
    again = run_sync("sdesk", "manual", full=True)  # idempotent on the source key
    assert again["status"] == "ok"
    assert (count("service_ticket"), count("upgrade_offer")) == (40, 2400)
    assert run_sync("sdesk", "manual")["status"] == "ok" and count("upgrade_offer") == 2400


@needs_mock
def test_rephist_sync_lands_history_and_stock():
    r = call("source.reconnect", {"source_id": "rephist"}, "developer")
    assert r["ok"], r
    out = run_sync("rephist", "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with SessionLocal() as s:
        sample = repair_history.similar(s, None, "CRH", "MOT", "13-24", *WINDOW)
        assert len(sample) == 186
        assert len(repair_history.similar(s, None, "DCD", "ELE", "37+", *WINDOW)) == 37
        assert refurb_stock.available(s, None, "CRH") == 30
        assert all(refurb_stock.available(s, None, c) == 30 for c in ("CMH", "BRK", "DCD", "AGR", "LSR"))
    total = count("repair_history")
    assert 5500 <= total <= 6500
    run_sync("rephist", "manual", full=True)
    assert count("repair_history") == total and count("refurb_unit") == 180
