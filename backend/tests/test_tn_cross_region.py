"""Plan 9, P9-10.15 (story TN-18): idle units in one region while another region buys new.

`AL-TN-XREGION`: units of a model idle more than 30 days in one region while another region has an open requisition for the
model -> an alert for the Planner with a transfer suggestion per unit. `SR-TN-XREGION` ("offer surplus across regions before a
new purchase order") is offered as a rule suggestion; adopting it is a flow draft, approved and published by someone else.
The tests write the spares planning records through the adapter's own `map` (literal records, no source-sim).
"""

import json

import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import tn_cross_region as xr
from di.services.modeler.flow import default_flow
from di.services.modeler.pack import load_pack
from di.services.modeler.templates import template_of_pack
from tests import flowkit, starting
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
# "%:SPARE-%": the demo seed leaves SPARE-1 (test_tn_facts._market) in the pool; it must not count here
CELLS = ("%:XR-%", "%:SPARE-%", f"{ORG}:%:PSU-48", f"{ORG}:%:RRU-4410")


def _clean() -> None:
    with engine.begin() as conn:
        for p in CELLS:
            conn.execute(text("DELETE FROM provenance WHERE model <> 'part' AND key LIKE :p"), {"p": p})
            conn.execute(text("DELETE FROM canonical WHERE model <> 'part' AND key LIKE :p"), {"p": p})
        conn.execute(
            text(
                "DELETE FROM decision_flow_version WHERE flow_id IN "
                "(SELECT id FROM decision_flow WHERE template_key = 'telecom_network')"
            )
        )
        conn.execute(text("DELETE FROM decision_flow WHERE template_key = 'telecom_network'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _write(resource: str, payload: dict) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "tn_spares", ADAPTERS["tn_spares"].map(Record(resource, "x", payload | {"org_unit_id": ORG})))
        s.commit()


def _idle(n: int, region: str, days: int = 45, model: str = "PSU-48", tag: str = "A") -> None:
    for k in range(n):
        _write("stock", {"serial": f"XR-{tag}-{region[:1]}-{k}", "model": model, "region": region, "idleDays": days})


def _req(region: str, model: str, req_id: str, qty: int, status: str = "open") -> None:
    _write(
        "requisitions",
        {
            "region": region,
            "model": model,
            "requisitions": [{"reqId": req_id, "quantity": qty, "status": status, "createdAt": "2026-09-28"}],
        },
    )


def _flow() -> int:
    g = default_flow(template_of_pack(load_pack("telecom_network")))
    with SessionLocal() as s:
        fid = s.execute(
            text(
                "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, published) "
                "VALUES ('telecom_network', :o, 'Telecom network', 'pub', 1, CAST(:g AS jsonb)) RETURNING id"
            ),
            {"o": ORG, "g": json.dumps(g)},
        ).scalar_one()
        s.execute(text("INSERT INTO decision_flow_version (flow_id, ver, graph, published_by) "
                       "VALUES (:f, 1, CAST(:g AS jsonb), 'system')"),
                  {"f": fid, "g": json.dumps(g)})  # fmt: skip
        s.commit()
    return fid


def _out(fid: int, user: str = "planner-a") -> dict:
    return flowkit.ok(call("telecom.crossRegion", {"flow_id": fid}, user))


def test_tn_18_idle_power_units_alert():
    _idle(3, "North")
    _req("West", "PSU-48", "PR-3301", 3)
    out = _out(_flow())
    (a,) = out["alerts"]
    assert a["id"] == "AL-TN-XREGION" and a["to_role"] == "Planner"
    assert a["text"] == "3 idle PSU-48 in North; West raised PR-3301"
    assert a["action"] == "Transfer to the region buying new"
    assert a["n"] == 3 and {t["serial"] for t in a["transfers"]} == {"XR-A-N-0", "XR-A-N-1", "XR-A-N-2"}
    assert all(t["from"] == "North" and t["to"] == "West" and t["req_id"] == "PR-3301" for t in a["transfers"])


def test_tn_18_no_alert_when_not_idle_long_enough_or_same_region_or_closed():
    _idle(2, "North", days=30)  # 30 is not more than 30
    _idle(2, "West", days=60, tag="B")  # idle in the region that buys: no surplus
    _req("West", "PSU-48", "PR-3301", 3)
    _req("South", "RRU-4410", "PR-9", 1, status="closed")
    _idle(1, "North", days=90, model="RRU-4410", tag="C")
    out = _out(_flow())
    assert out["alerts"] == [] and out["suggestion"] is None


def test_tn_18_transfers_stop_at_the_requisition_quantity_oldest_first():
    _idle(1, "North", days=40, tag="A")
    _idle(1, "East", days=90, tag="B")
    _idle(1, "East", days=70, tag="C")
    _req("West", "PSU-48", "PR-3301", 2)
    alerts = _out(_flow())["alerts"]
    east = next(a for a in alerts if a["region"] == "East")
    assert [t["idle_days"] for t in east["transfers"]] == [90, 70]
    assert next(a for a in alerts if a["region"] == "North")["n"] == 1


def test_tn_18_pure_alerts():
    u = [xr.Unit("S1", "PSU-48", "North", 31), xr.Unit("S2", "PSU-48", "North", 30)]
    (a,) = xr.alerts(u, [xr.Req("PR-1", "PSU-48", "West", 5)], 30, "Planner", "Do")
    assert a.text == "1 idle PSU-48 in North; West raised PR-1" and len(a.transfers) == 1


def test_tn_18_rule_suggestion_needs_approval():
    _idle(3, "North")
    _req("West", "PSU-48", "PR-3301", 3)
    fid = _flow()
    sug = _out(fid)["suggestion"]
    assert sug["id"] == "SR-TN-XREGION" and sug["text"].startswith("Offer surplus across regions before a new purchase order")
    assert sug["proposal"]["kind"] == "rule" and sug["proposal"]["guard"] is None
    graph = sug["proposal"]["graph"]
    flowkit.ok(call("flow.saveDraft", {"flow_id": fid, "graph": graph}, "planner-a"))  # adopting is the person's own draft
    flowkit.ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    assert call("flow.approve", {"flow_id": fid}, "planner-a")["ok"] is False
    assert call("flow.publish", {"flow_id": fid}, "planner-a")["ok"] is False  # the author does not publish
    flowkit.ok(call("flow.approve", {"flow_id": fid}, "approver"))
    flowkit.ok(call("flow.publish", {"flow_id": fid}, "approver"))
    f, _ = flowkit.get(fid)
    assert any(n.get("rid") == sug["proposal"]["rid"] for n in f.published["nodes"])


def test_tn_18_person_only_and_telecom_only():
    assert forbidden("telecom.crossRegion")
    r = call("telecom.crossRegion", {"flow_id": flowkit.flow_id("device", "workspace")}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert call("telecom.crossRegion", {"flow_id": _flow()}, "warehouse1")["ok"] is False


def test_tn_18_f9_an_agent_on_a_persons_token_cannot_read_the_transfers():
    from tests.helpers import client, h

    fid = _flow()
    assert call("telecom.crossRegion", {"flow_id": fid}, "planner-a")["ok"] is True
    r = client.post(
        "/api/actions/telecom.crossRegion", json={"flow_id": fid}, headers=h("planner-a") | {"X-Circularity-Preparer": "gap"}
    ).json()
    assert r["ok"] is False and r["error"]["code"] == "approval_required", r
