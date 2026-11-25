"""Plan 9, P9-5.1 (stories CR-01, CR-08): a refresh case per contract entering its window.

A fleet contract whose window has opened (90 days before its end, or before its notice date when the contract has one)
opens one `contract_refresh` case, once per term, with its lines from the canonical store. The scan is the daily job
`refresh.scan`. The case carries a proposal-due item on the process layer (5 working days; `refresh_late` when it is
overdue). Dates and counts are computed; no model step. The tests write canonical contract facts as the fleet adapter
would, in their own org unit, and start and end with the demo reset.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from di import worker
from di.connectors import extra
from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import intake, process, refresh_intake, refresh_window
from tests import starting
from tests.helpers import call, client, h

ORG = "tool-fleet-a"
TODAY = date(2026, 10, 7)


def _contract(cid: str, end: str, notice: str | None = None, status: str = "active", market: str = "US") -> list[canonical.Fact]:
    f = {"contract_id": cid, "customer": "Brightline Mechanical", "market": market, "start_date": "2024-01-05",
         "end_date": end, "notice_date": notice, "term_months": 36, "status": status}  # fmt: skip
    return [canonical.Fact("contract", cid, k, v, resource="contracts") for k, v in f.items() if v is not None]


def _lines(cid: str, n: int) -> list[canonical.Fact]:
    out = []
    for i in range(n):
        serial = f"{cid}-S{i:02d}"
        f = {"contract_id": cid, "serial": serial, "tool_class": "CMH", "model": "CMH-12 Pro", "fee_month": 55.0,
             "months_on_contract": 33, "status": "on_contract", "line_id": f"FL-{cid}-{i:02d}"}  # fmt: skip
        out += [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in f.items()]
    return out


def _land(*facts: list[canonical.Fact]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "fleet", [f for fs in facts for f in fs])
        s.commit()


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract', 'contract_line')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line')"))
        conn.execute(text("DELETE FROM job WHERE kind IN ('refresh.scan', 'work.sla', 'case.replan')"))


@pytest.fixture(scope="module", autouse=True)
def org():
    starting.reset()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    _forget()
    starting.reset()


@pytest.fixture(autouse=True)
def fresh():
    _forget()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": ORG})
        conn.execute(text("DELETE FROM work_item WHERE org_unit_id = :o"), {"o": ORG})
    return


def _scan(today: date) -> list[str]:
    with SessionLocal() as s:
        ids = refresh_intake.scan(s, ORG, today)
        s.commit()
    return ids


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        return intake.store.get(s, case_id)  # type: ignore[return-value]


def _view(case_id: str, user: str = "admin"):
    return client.get(f"/api/screens/refresh/{case_id}", headers=h(user))


# ------------------------------------------------------------------ the pure window
def test_cr_08_window_opens_from_notice_or_end():
    assert refresh_window.window_opens(date(2027, 6, 30), None) == date(2027, 4, 1)
    assert refresh_window.window_opens(date(2027, 6, 30), date(2027, 1, 5)) == date(2026, 10, 7)
    assert refresh_window.window_opens(date(2027, 1, 5), None, 60) == date(2026, 11, 6)


def test_cr_01_due_needs_status_open_window_and_unended_term():
    rows = [
        {"contract_id": "A", "status": "active", "end_date": "2027-01-05"},  # opens today
        {"contract_id": "B", "status": "active", "end_date": "2027-01-06"},  # tomorrow
        {"contract_id": "C", "status": "evergreen", "end_date": "2027-01-05"},
        {"contract_id": "D", "status": "ended", "end_date": "2027-01-05"},
        {"contract_id": "E", "status": "active", "end_date": "2026-10-01"},  # the term has ended
        {"contract_id": "F", "status": "active", "end_date": None},
    ]
    assert refresh_window.due(rows, TODAY, 90) == ["A", "C"]


def test_cr_01_five_working_days_skip_the_weekend():
    assert refresh_window.add_working_days(date(2026, 10, 7), 5) == date(2026, 10, 14)  # Wed -> Wed
    assert refresh_window.add_working_days(date(2026, 10, 9), 1) == date(2026, 10, 12)  # Fri -> Mon


# ------------------------------------------------------------------ the scan
def test_cr_01_opens_once_per_contract_and_term():
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 14), _contract("FC-30118", "2027-01-06"), _lines("FC-30118", 2))
    opened = _scan(TODAY)
    assert len(opened) == 1  # FC-30118 ends a day later: its window has not opened
    c = _case(opened[0])
    assert (c["assetId"], c["template"], c["owner"], c["flow"], c["contract_id"]) == (
        "FC-30117",
        "tool_fleet",
        ORG,
        "contract_refresh",
        "FC-30117",
    )
    assert c["intake"]["reason"] == "contract_refresh" and c["intake"]["key"] == "FC-30117@2027-01-05:contract_refresh"
    assert c["stage"] == "none" and c["routes"] == [] and c["recommendation"] is None
    assert c["refresh"]["term_end"] == "2027-01-05" and c["refresh"]["market"] == "US" and len(c["refresh"]["lines"]) == 14
    assert {"serial", "cls", "model", "fee", "months"} <= set(c["refresh"]["lines"][0])
    assert _scan(TODAY) == []  # the same day
    (nxt,) = _scan(TODAY + timedelta(days=1))  # FC-30118's window opens; FC-30117's term is already open
    assert _case(nxt)["assetId"] == "FC-30118"
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM case_record WHERE data ->> 'assetId' = 'FC-30117'")).scalar()
    assert n == 1


def test_cr_01_next_day_opens_nothing_for_an_open_term():
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 2))
    assert len(_scan(TODAY)) == 1
    assert _scan(TODAY + timedelta(days=1)) == []
    assert _scan(TODAY + timedelta(days=30)) == []


def test_cr_01_new_term_opens_again():
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 2))
    assert len(_scan(TODAY)) == 1
    _land(_contract("FC-30117", "2028-01-05"))  # renewed: a new end date
    assert _scan(date(2027, 10, 6)) == []  # one day before the new window
    again = _scan(date(2027, 10, 7))
    assert len(again) == 1 and _case(again[0])["refresh"]["term_end"] == "2028-01-05"


def test_cr_08_window_from_notice_date():
    _land(_contract("FC-30121", "2027-06-30", notice="2027-01-05"), _lines("FC-30121", 3))
    (cid,) = _scan(TODAY)
    v = _view(cid).json()
    assert v["window"] == {"opens": "2026-10-07", "basis": "notice"}
    # without the notice date it would open on 2027-04-01
    _land(_contract("FC-30122", "2027-06-30"), _lines("FC-30122", 1))
    assert _scan(TODAY) == [] and _scan(date(2027, 3, 31)) == []
    (other,) = _scan(date(2027, 4, 1))
    assert _view(other).json()["window"] == {"opens": "2027-04-01", "basis": "end"}


def test_cr_01_scan_skips_a_contract_that_is_not_active():
    _land(_contract("FC-30130", "2027-01-05", status="ended"), _contract("FC-30131", "2027-01-05", status="evergreen"))
    opened = _scan(TODAY)
    assert [_case(c)["assetId"] for c in opened] == ["FC-30131"]


# ------------------------------------------------------------------ the SLA
def test_cr_01_late_proposal_escalates(monkeypatch):
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 2))
    (cid,) = _scan(TODAY)
    with engine.connect() as conn:
        item = (
            conn.execute(
                text("SELECT id, kind, type, owner_role, due_at, status, escalated_at FROM work_item WHERE case_id = :c"),
                {"c": cid},
            )
            .mappings()
            .one()
        )
    assert (item["kind"], item["type"], item["status"], item["escalated_at"]) == ("exception", "refresh_late", "open", None)
    assert item["owner_role"] == process.role_of_owner("Fleet desk")
    start = clock.now()
    assert item["due_at"] == datetime.combine(refresh_window.add_working_days(start.date(), 5), start.timetz())
    with SessionLocal() as s:
        assert process.on_sla(s, item["id"]) == "not_due"  # not overdue yet
        s.commit()
    monkeypatch.setattr(clock, "now", lambda: start + timedelta(days=8))
    with SessionLocal() as s:
        assert process.on_sla(s, item["id"]) == "escalated"
        s.commit()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT escalated_at, owner_role FROM work_item WHERE id = :i"), {"i": item["id"]}).one()
    assert row[0] is not None and row[1] == "Approver"  # the pack's escalate_to


def test_cr_01_pack_declares_the_refresh_flow_and_its_exception():
    from di.services.modeler.pack import load_pack

    pack = load_pack("tool_fleet")
    assert "contract_refresh" in [f.key for f in pack.flows]
    cfg = pack.valuer.params["contract_refresh"]
    assert cfg["window_days"] == 90 and cfg["routes"] == ["keep", "swap", "upgrade"] and cfg["sla_working_days"] == 5
    (exc,) = [e for e in pack.runtime.exception_types if e.id == "refresh_late"]
    assert exc.owner_role == "Fleet desk"


# ------------------------------------------------------------------ the screen
def test_cr_01_view_shape():
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 14))
    (cid,) = _scan(TODAY)
    r = _view(cid)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["case_id"] == cid and v["contract"]["id"] == "FC-30117" and v["contract"]["end"] == "2027-01-05"
    assert v["window"] == {"opens": "2026-10-07", "basis": "end"} and len(v["lines"]) == 14
    assert (v["tools"], v["match"], v["pricing"], v["approval"], v["execution"], v["outcome"]) == ([], [], None, None, None, None)


def test_cr_01_view_refuses_a_case_that_is_not_a_refresh():
    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": "CMH-1", "reason": "contract_end",
                "facts": {"tool_class": "CMH"}}, "system")  # fmt: skip
        s.commit()
    assert _view(c["id"]).status_code == 404


def test_cr_01_view_tenant_boundary():
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 1))
    (cid,) = _scan(TODAY)
    r = _view(cid, "planner.b")
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_boundary"


def test_cr_01_refresh_case_stays_out_of_the_tool_queue():
    """A refresh case has no tool class: it is not planned with the org's returns, and a re-evaluation leaves it as it is."""
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 2))
    (cid,) = _scan(TODAY)
    with SessionLocal() as s:
        assert [d["id"] for d in intake.open_tool_cases(s, ORG)] == []
        c = intake.store.get(s, cid)
        intake.revalue(s, c)
        assert c["stage"] == "none" and c["routes"] == []
    assert worker.HANDLERS["case.replan"]({"org_unit_id": ORG, "template": "tool_fleet"}) is None


# ------------------------------------------------------------------ the job
def test_cr_01_job_scans_each_org_with_a_fleet_source_and_queues_the_next_day():
    _land(_contract("FC-30117", "2027-01-05"), _lines("FC-30117", 2))
    with SessionLocal() as s:
        extra.register(s, "fleet", ORG)
        s.commit()
    worker.HANDLERS["refresh.scan"]({"today": "2026-10-07"})
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM case_record WHERE owner = :o"), {"o": ORG}).scalar() == 1
        nxt = conn.execute(
            text(
                "SELECT run_after > now() + interval '20 hours', dedupe_key FROM job "
                "WHERE kind = 'refresh.scan' AND status = 'queued'"
            )
        ).one()
    assert nxt[0] is True and nxt[1] == "refresh.scan:2026-10-08"
    worker.HANDLERS["refresh.scan"]({"today": "2026-10-07", "org_unit_id": ORG})  # named org, run again: nothing opens twice
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM case_record WHERE owner = :o"), {"o": ORG}).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM job WHERE kind = 'refresh.scan' AND status = 'queued'")).scalar() == 1
