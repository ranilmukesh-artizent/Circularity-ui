"""B9 adapters for Salesforce (crm), IBM Sterling OMS (oms) and ServiceNow FSM (fsm) against the live mocks.

Needs source-sim running (docker compose) and the worker stopped, so scheduled syncs do not race the tests. Only these
three systems are reset, and only their cursors and queued jobs are cleared: the canonical store is shared.
"""

import httpx
import pytest
from sqlalchemy import text

from di.canonical import store
from di.config import get_settings
from di.connectors.sync import ensure_sources, run_sync
from di.db import SessionLocal, engine

SIM = get_settings().source_sim_url
MINE = ("crm", "oms", "fsm")
LEASE_OPP = "006Hs00000002j4IAA"  # RT-1048's re-lease opportunity (LS-5530), Proposal
REPLACEMENT_OPP = "006Hs00000002j3IAA"  # RT-1048's replacement demand at Site 3, Closed Won


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def reset_mine() -> None:
    for s in MINE:
        sim("POST", "/_sim/reset", params={"system": s})
    sim("POST", "/_sim/webhooks/deliver")  # deliver the reset events now, so they cannot void cursors mid-test


def clear_state() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id IN ('crm','oms','fsm')"))
        conn.execute(text("DELETE FROM job WHERE kind = 'sync.source' AND payload->>'source_id' IN ('crm','oms','fsm')"))


@pytest.fixture(scope="module", autouse=True)
def clean():
    reset_mine()
    clear_state()
    with SessionLocal() as s:
        ensure_sources(s)
        # registered before these adapters existed: the source counted as unavailable
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id IN ('crm','oms','fsm') AND status = 'unavailable'"))
        s.commit()
    yield
    reset_mine()
    clear_state()


def record(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def prov(model: str, key: str, field: str, source: str) -> dict:
    rows = [p for p in record(model, key)["provenance"].get(field, []) if p["source_id"] == source]
    assert rows, f"no {source} provenance for {model}.{key}.{field}"
    return rows[0]


def mapping(p: dict) -> tuple:
    return p["value"], p["source_field"], p["source_value"], p["transform"]


def initial(source: str) -> dict:
    """An initial sync. Other sources syncing at the same time (shared containers) can deadlock on the same canonical
    rows; such records are counted as failed, so one full re-read is allowed for that reason only."""
    out = run_sync(source, "initial")
    if out["status"] == "partial" and "Deadlock" in (out["error"] or ""):
        out = run_sync(source, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    return out


# ------------------------------------------------------------------ Salesforce
def sf_client() -> httpx.Client:
    form = {
        "grant_type": "client_credentials",
        "client_id": "3MVG9circularity.demo.northfield.crm.connector",
        "client_secret": "circularity-demo-salesforce-secret",
    }
    tok = sim("POST", "/salesforce/services/oauth2/token", data=form).json()["access_token"]
    return httpx.Client(base_url=SIM + "/salesforce/services/data/v59.0", headers={"Authorization": "Bearer " + tok}, timeout=30)


def test_salesforce_initial_sync_maps_the_demo_examples():
    out = initial("crm")
    assert out["records_read"] >= 3 + 105  # accounts, opportunities (and contracts)

    lease = record("demand", LEASE_OPP)
    assert lease["data"]["status"] == "forecast" and lease["data"]["kind"] == "lease"
    assert lease["data"]["case_ref"] == "RT-1048" and lease["data"]["relase_ref"] == "LS-5530"
    p = prov("demand", LEASE_OPP, "status", "crm")
    assert p["authority"] is True
    assert mapping(p) == ("forecast", "Opportunity.StageName", "Proposal", "Stage map: Proposal → forecast")
    assert mapping(prov("demand", LEASE_OPP, "need_by", "crm")) == (
        "2026-12-31",
        "Opportunity.CloseDate",
        "2026-12-31",
        "Date format",
    )
    assert mapping(prov("demand", LEASE_OPP, "lease_rate", "crm"))[1:] == (
        "Opportunity.Amount",
        146.67,
        "Currency + period normalised",
    )

    repl = record("demand", REPLACEMENT_OPP)["data"]
    assert (repl["status"], repl["need_by"], repl["amount"], repl["kind"]) == ("confirmed", "2026-10-17", 12000.0, "replacement")
    assert (repl["buyer"], repl["ship_to_site"], repl["asset_ref"]) == ("Customer A", "Site 3", "MTR-2041")

    owner = prov("asset", "MTR-2041", "owner_tenant", "crm")
    assert mapping(owner) == ("Customer A", "Account.Id", "001Hs00003AbCdE", "Tenant key lookup")
    assert owner["authority"] is False  # the lease system owns ownership
    asset = {f: prov("asset", "MTR-2041", f, "crm")["value"] for f in ("case_ref", "relase_ref", "relase_term_months")}
    assert asset == {"case_ref": "RT-1048", "relase_ref": "LS-5530", "relase_term_months": 30}


def test_salesforce_delta_reads_only_changes():
    assert run_sync("crm", "schedule")["records_read"] == 0
    with sf_client() as c:
        r = c.patch(f"/sobjects/Opportunity/{LEASE_OPP}", json={"StageName": "Closed Won"})
        assert r.status_code == 204, r.text
    out = run_sync("crm", "webhook")
    assert out["records_read"] == 1, out
    assert record("demand", LEASE_OPP)["data"]["status"] == "confirmed"
    assert prov("demand", LEASE_OPP, "status", "crm")["transform"] == "Stage map: Closed Won → confirmed"


# ------------------------------------------------------------------ Sterling
def sterling_client() -> httpx.Client:
    form = {"grant_type": "client_credentials"}
    tok = sim(
        "POST", "/sterling/smcfs/restapi/oauth/token", data=form, auth=("di-connector", "circularity-demo-sterling-secret")
    ).json()["access_token"]
    return httpx.Client(base_url=SIM + "/sterling/smcfs/restapi", headers={"Authorization": "Bearer " + tok}, timeout=30)


def test_sterling_initial_sync_maps_the_demo_examples():
    out = initial("oms")
    assert out["records_read"] == 71 + 128  # sales orders and return orders

    so = record("demand", "SO-48102")
    d = so["data"]
    assert (d["demand_id"], d["line"], d["need_by"], d["item"], d["qty"]) == ("SO-48102", 10, "2026-10-17", "MTR-55KW", 1)
    assert (d["accepts_refurbished"], d["status"], d["order_status"], d["purchase_ref"]) == (
        True,
        "confirmed",
        "Created",
        "PO-49048",
    )
    assert (d["buyer"], d["ship_to_site"], d["unit_price"], d["kind"]) == ("Customer A", "Site 3", 12000.0, "replacement")
    assert mapping(prov("demand", "SO-48102", "demand_id", "oms")) == ("SO-48102", "OrderNo", "SO-48102", "Pass-through")
    assert mapping(prov("demand", "SO-48102", "line", "oms")) == (10, "PrimeLineNo", "10", "Integer")
    loc = ("Site 3 · Chennai Foundry", "ShipToKey", "LOC-CHN-03", "Location lookup")
    assert mapping(prov("demand", "SO-48102", "location", "oms")) == loc
    ship_to = prov("demand", "SO-48102", "ship_to", "oms")
    assert mapping(ship_to) == loc and ship_to["authority"] is True
    need = prov("demand", "SO-48102", "need_by", "oms")
    assert mapping(need) == ("2026-10-17", "ReqDeliveryDate", "2026-10-17T00:00:00+05:30", "Date to ISO") and need["authority"]

    ret = {
        f: prov("asset", "MTR-2041", f, "oms")["value"] for f in ("return_ref", "return_received_at", "receipt_ref", "relase_ref")
    }
    assert ret == {
        "return_ref": "RMA-56509",
        "return_received_at": "2026-10-03T00:00:00+00:00",
        "receipt_ref": "GR-570262",
        "relase_ref": "LS-5530",
    }
    assert prov("asset", "MTR-2041", "customer_intent", "oms")["value"] == "Lease return, no credit"


def test_sterling_delta_picks_up_an_allocation():
    assert run_sync("oms", "schedule")["records_read"] == 0
    with sterling_client() as c:
        r = c.post("/order/allocate", json={"OrderNo": "SO-48102", "PrimeLineNo": "10", "SerialNo": "MTR-2041"})
        assert r.status_code == 200, r.text
    out = run_sync("oms", "webhook")
    assert out["records_read"] == 1, out
    d = record("demand", "SO-48102")["data"]
    assert (d["allocated_asset"], d["order_status"], d["ship_node"]) == ("MTR-2041", "Scheduled", "WH01")
    assert prov("asset", "MTR-2041", "allocated_to", "oms")["value"] == "SO-48102"


# ------------------------------------------------------------------ ServiceNow
SN_AUTH = ("di.integration", "Circularity-demo-sn-1")


def test_servicenow_initial_sync_maps_the_demo_examples():
    out = initial("fsm")
    assert out["records_read"] == 294 + 422 + 422  # alm_asset, wm_order, wm_task

    assert mapping(prov("asset", "MTR-2041", "work_order_ref", "fsm")) == (
        "WO0010382",
        "wm_order.number",
        "WO0010382",
        "Pass-through",
    )
    assert mapping(prov("asset", "MTR-2041", "source_refs", "fsm")) == (
        ["FSM:SN-77120-A"],
        "alm_asset.serial_number",
        "SN-77120-A",
        "Prefixed with system",
    )
    assert mapping(prov("asset", "MTR-2041", "availability", "fsm")) == (
        "in_service",
        "wm_task.state",
        "3",
        "State map: 3 → in_service",
    )
    assert mapping(prov("condition", "MTR-2041", "service_date", "fsm")) == (
        "2026-09-30T14:05:11Z",
        "wm_task.closed_at",
        "2026-09-30 14:05:11",
        "Local time → UTC",
    )
    assert prov("condition", "MTR-2041", "service_hours", "fsm")["value"] == 2.5
    assert prov("asset", "MTR-2041", "case_ref", "fsm")["value"] == "RT-1048"

    demand = prov("demand", "SO-48102", "service_demand", "fsm")
    assert demand["authority"] is True
    assert demand["value"] == {
        "work_order": "WO0010362",
        "work_type": "Install",
        "state": "Ready",
        "site": "Site 3",
        "due": "2026-10-17T09:00:00Z",
        "qty": 1,
    }
    assert prov("demand", "SO-48102", "dispatch_status", "fsm")["value"] == "Pending Dispatch"


def test_servicenow_delta_picks_up_a_dispatch():
    assert run_sync("fsm", "schedule")["records_read"] == 0
    with httpx.Client(base_url=SIM + "/servicenow/api/now/table", auth=SN_AUTH, timeout=30) as c:
        task = c.get("/wm_task", params={"sysparm_query": "parent.number=WO0010362", "sysparm_fields": "sys_id"}).json()
        sid = task["result"][0]["sys_id"]
        r = c.patch(f"/wm_task/{sid}", json={"assigned_to": "tech.0412"})
        assert r.status_code == 200, r.text
    out = run_sync("fsm", "webhook")
    assert out["records_read"] == 2, out  # the task, and its order rolled up to Scheduled
    d = record("demand", "SO-48102")["data"]
    assert (d["dispatch_status"], d["dispatch_tech"], d["service_state"]) == ("Assigned", "tech.0412", "Scheduled")
