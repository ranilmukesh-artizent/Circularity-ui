"""B5b/B9: the Oracle Depot Repair adapter (repair) against source-sim's EBS Depot Repair mock.

Needs source-sim running and the worker stopped. Only repair is reset, and only its cursors and queued jobs cleared.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.sync import ensure_sources, run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store

SIM = get_settings().source_sim_url
SID = "repair"
REST = "/depot-repair/webservices/rest"
USER = ("DI_CONNECTOR", "repair-demo-password")


def sim(method: str, path: str, **kw) -> httpx.Response:
    r = httpx.request(method, SIM + path, timeout=60, **kw)
    r.raise_for_status()
    return r


def clear_state() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM job WHERE kind = 'sync.source' AND status = 'queued' AND payload->>'source_id' = :s"), {"s": SID}
        )
        conn.execute(text("DELETE FROM sync_cursor WHERE source_id = :s"), {"s": SID})


@pytest.fixture(scope="module", autouse=True)
def reset_repair():
    sim("DELETE", "/_sim/faults", params={"system": SID})
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(text("UPDATE source_system SET status = 'live' WHERE id = :s"), {"s": SID})
        s.commit()
    clear_state()
    yield
    sim("POST", "/_sim/reset", params={"system": SID})
    sim("POST", "/_sim/webhooks/deliver")
    clear_state()


def sync(trigger: str = "schedule") -> dict:
    out = run_sync(SID, trigger)
    assert out["status"] in ("ok", "partial"), out
    if out["status"] == "partial":
        assert "deadlock" in (out["error"] or "").lower(), out
        again = run_sync(SID, "manual", full=True)
        assert again["status"] in ("ok", "partial"), again
    return out


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, (model, key)
    return rec


def prov(model: str, key: str, field: str) -> dict:
    rows = [p for p in canonical(model, key)["provenance"].get(field, []) if p["source_id"] == SID]
    assert rows, (model, key, field)
    return rows[0]


def mapping(p: dict) -> tuple:
    return p["source_field"], p["source_value"], p["value"], p["transform"]


def test_initial_sync_reproduces_the_demo_mapping():
    out = sync("initial")
    assert out["records_read"] >= 53 + 53  # repair orders, plus task and test-result groups
    iv = canonical("intervention", "MTR-2041")["data"]
    assert (iv["cost"], iv["scope"], iv["hours"], iv["repair_order_ref"]) == (1800.0, "Light repair + test", 22.0, "RO-61048")
    assert mapping(prov("intervention", "MTR-2041", "cost")) == ("REPAIR_COST", "1,800.00 USD", 1800.0, "Currency kept in USD")
    assert mapping(prov("intervention", "MTR-2041", "process")) == (
        "SCOPE",
        "Light repair + test",
        "light repair + test",
        "Process map",
    )
    assert mapping(prov("intervention", "MTR-2041", "predicted_condition")) == ("RESULT_STATE", "B", "B", "Grade table v3")
    cond = canonical("condition", "MTR-2041")
    assert cond["data"]["grade"] == "B" and cond["data"]["test_result"] == "pass" and cond["data"]["inspection_ref"] == "RO-61048"
    assert prov("condition", "MTR-2041", "grade")["authority"] is True
    assert canonical("asset", "MTR-2041")["data"]["case_ref"] == "RT-1048"


def test_delta_reads_nothing_then_a_new_repair_order_and_its_completion():
    assert run_sync(SID, "schedule")["records_read"] == 0
    body = {
        "CREATE_REPAIR_ORDER_Input": {
            "RESTHeader": {"Responsibility": "DEPOT_REPAIR_SUPER_USER", "RespApplication": "CSD"},
            "InputParameters": {
                "P_API_VERSION_NUMBER": "1.0",
                "P_REPLN_REC": {
                    "SERIAL_NUMBER": "TST-OPS-1",
                    "REPAIR_TYPE": "Refurbishment",
                    "ATTRIBUTE_CATEGORY": "CIRCULARITY",
                    "ATTRIBUTE1": "Clean, test and certify",
                    "ATTRIBUTE2": "950",
                    "ATTRIBUTE3": "A",
                },
            },
        }
    }
    o = sim("POST", REST + "/csdrepairs/create_repair_order/", auth=USER, json=body).json()["OutputParameters"]
    assert o["X_RETURN_STATUS"] == "S"
    out = sync()
    assert out["records_read"] == 2  # the repair order and its task group
    iv = canonical("intervention", "TST-OPS-1")["data"]
    assert (iv["cost"], iv["repair_order_ref"], iv["repair_status"]) == (950.0, o["X_REPAIR_NUMBER"], "OPEN")

    sim("POST", "/_sim/clock/advance", json={"hours": 6})  # start, then complete (bench labour 4 h)
    sync()
    iv = canonical("intervention", "TST-OPS-1")["data"]
    assert iv["repair_status"] == "REPAIR_COMPLETE" and iv["tasks_complete"] == "1/1"
    assert iv["released"] == "RTS-" + o["X_REPAIR_NUMBER"]
    assert canonical("condition", "TST-OPS-1")["data"]["test_result"] == "pass"
    assert run_sync(SID, "schedule")["records_read"] == 0
