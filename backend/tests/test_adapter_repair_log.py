"""Plan 9, P9-3.1: the legacy depot repair log (source `repairlog`) adapter against source-sim's synthetic mock.

`repairlog` is no demo source (and not Oracle Depot Repair, `repair`): it starts unregistered. Synced, it fills
`condition.<serial>` (grade, test result, inspection reference) and `repair_event.<roId or tdId>`. The mapping tests run
on literal records; the sync test needs source-sim running with the mock (restart it after the change, R14) and is
skipped, with the reason, when it lacks it.
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import check_fact
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "repairlog"
API = SIM + "/repairlog/api"
AUTH = ("di-connector", "repairlog-demo")

ORDER = {
    "roId": "DR-50123", "serial": "CRH-44120", "toolClass": "CRH", "market": "US", "ageMonths": 31, "faultCode": "BAT-CONTACT",
    "grade": "B", "testResult": "pass", "gradedAt": "2026-10-05", "labourHours": 1.5, "partsCost": 64.0, "labourRate": 78.0,
    "status": "closed", "closedAt": "2026-10-05",
    "components": [{"name": "Battery contacts", "replaced": True, "runHoursAtReplacement": 1840},
                   {"name": "Chuck", "replaced": False, "runHoursAtReplacement": 900}],
}  # fmt: skip
OPEN = ORDER | {"roId": "DR-50999", "serial": "CMH-48213", "grade": None, "testResult": None, "gradedAt": None,
                "closedAt": None, "status": "open"}  # fmt: skip
TEARDOWN = {"tdId": "TD-80001", "serial": "CMH-60001", "toolClass": "CMH", "component": "Motor brushes", "runHours": 1620,
            "verdict": "worn_out", "observedAt": "2025-03-04"}  # fmt: skip


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = ANY(:s)"), {"s": ["fleet", "repairlog"]})
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract', 'contract_line', 'repair_event')"))
        conn.execute(
            text(
                "DELETE FROM canonical c WHERE c.model IN ('condition', 'demand') AND NOT EXISTS "
                "(SELECT 1 FROM provenance p WHERE p.model = c.model AND p.key = c.key)"
            )
        )


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/repair-orders", auth=AUTH, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the repair log mock: restart it (R14)")


def canonical(model: str, key: str) -> dict:
    with SessionLocal() as s:
        rec = store.get(s, model, key)
    assert rec is not None, f"{model}.{key} missing"
    return rec


def test_repair_log_maps_grade_and_components_from_records():
    facts = ADAPTERS[SID].map(Record("orders", "DR-50123", ORDER))
    cond = {f.field: f.value for f in facts if f.model == "condition"}
    assert {f.key for f in facts if f.model == "condition"} == {"CRH-44120"}
    assert cond == {"grade": "B", "test_result": "pass", "inspection_ref": "DR-50123", "graded_at": "2026-10-05"}
    ev = {f.field: f.value for f in facts if f.model == "repair_event"}
    assert {f.key for f in facts if f.model == "repair_event"} == {"DR-50123"}
    assert ev["kind"] == "repair_order" and ev["event_id"] == ev["ro_id"] == "DR-50123" and ev["fault_code"] == "BAT-CONTACT"
    assert ev["components"][0] == {"name": "Battery contacts", "replaced": True, "runHoursAtReplacement": 1840}
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_an_open_order_has_no_grade_fact():
    facts = ADAPTERS[SID].map(Record("orders", "DR-50999", OPEN))
    assert not [f for f in facts if f.model == "condition"]
    ev = {f.field: f.value for f in facts}
    assert ev["status"] == "open" and "grade" not in ev and "closed_at" not in ev
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_a_teardown_is_a_repair_event_of_kind_teardown():
    facts = ADAPTERS[SID].map(Record("teardowns", "TD-80001", TEARDOWN))
    assert {f.model for f in facts} == {"repair_event"} and {f.key for f in facts} == {"TD-80001"}
    by = {f.field: f.value for f in facts}
    assert (by["kind"], by["td_id"], by["event_id"], by["verdict"], by["run_hours"], by["component"]) == (
        "teardown", "TD-80001", "TD-80001", "worn_out", 1620, "Motor brushes",
    )  # fmt: skip
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


@needs_mock
def test_repair_log_adapter_maps_grade_and_components():
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    seeded = httpx.get(API + "/repair-orders", auth=AUTH, params={"serial": "CRH-44120"}, timeout=30).json()["items"]
    assert len(seeded) == 1 and seeded[0]["grade"] in "ABCD"
    cond = canonical("condition", "CRH-44120")
    assert cond["data"]["grade"] == seeded[0]["grade"] and cond["data"]["inspection_ref"] == seeded[0]["roId"]
    assert cond["data"]["inspection_ref"].startswith("DR-")
    assert {x["source_id"] for x in cond["provenance"]["grade"]} == {SID}
    ev = canonical("repair_event", seeded[0]["roId"])["data"]
    assert ev["components"] == seeded[0]["components"] and ev["kind"] == "repair_order"
    late = canonical("repair_event", httpx.get(API + "/repair-orders", auth=AUTH, params={"serial": "CMH-48213"}, timeout=30)
                     .json()["items"][0]["roId"])["data"]  # fmt: skip
    assert late["status"] == "open" and "grade" not in late  # the late one: no grade yet
    td = canonical("repair_event", "TD-80000")["data"]
    assert td["kind"] == "teardown" and td["verdict"] in ("worn_out", "serviceable")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM canonical WHERE model = 'repair_event'")).scalar_one()
    assert n >= 2400 + 900
