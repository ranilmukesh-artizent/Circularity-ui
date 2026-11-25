"""MVP-8.1: opening a case from data (`case.open`, di.services.cases.intake).

    case.open  act  {org_unit_id, template_key, asset_key, reason, facts?}   openCases (Admin, Developer, Planner)

A new case gets the next RT-<n> above the highest, belongs to the org unit, starts at the first stage and is valued by
the engine (industrial) or the template's valuer (tool fleet, device), then the live rules. The same asset and reason
twice open one case (Review Focus 5). Every test ends with the starting state (the opened cases are dropped).
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories.live_rules import flow_version, live_pack
from di.services.actions.registry import ActionError
from di.services.cases import intake, store
from di.services.cases.decide import decide_case
from di.services.engine.routes import rank_routes
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import tool_fleet
from di.services.modeler.valuers.routes_adapter import to_routes
from tests import starting
from tests.helpers import call, tool_case_facts

MOTOR = {"cls": "motor", "grade": "B", "age": 4, "qty": 1, "demand": {"site": "Site 2", "confirmed": True}}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def _open(asset: str, reason: str = "rma", user: str = "planner-a", **over) -> dict:
    body = {"org_unit_id": "Customer A", "template_key": "industrial", "asset_key": asset, "reason": reason, "facts": MOTOR}
    return call("case.open", body | over, user)


def _highest() -> int:
    with engine.connect() as c:
        return max(int(i[3:]) for i in c.execute(text("SELECT id FROM case_record")).scalars())


def test_open_industrial_case():
    top = _highest()
    r = _open("T-MTR-1")
    assert r["ok"], r
    cid = r["output"]["case_id"]
    assert cid == f"RT-{top + 1}"
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        log = s.execute(text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c"), {"c": cid}).all()
        ev = s.execute(text("SELECT count(*) FROM domain_event WHERE type = 'case.opened' AND case_id = :c"), {"c": cid})
        assert ev.scalar_one() == 1
    # a recommendation waits for approval, as after a re-evaluation (MVP-12.4: "none" left it stuck)
    assert (c["owner"], c["template"], c["stage"], c["assetId"]) == ("Customer A", "industrial", "awaiting_approval", "T-MTR-1")
    assert (c["cls"], c["grade"], c["age"], c["qty"]) == ("motor", "B", 4, 1)
    assert [r["id"] for r in c["routes"]] == ["resale", "redeploy", "relase", "intparts", "extparts", "material", "exit"]
    assert c["recommendation"] is rank_routes(c["routes"], None)
    assert c["intake"]["reason"] == "rma" and c["flowVer"] >= 0
    assert [x[0] for x in log] == ["Case opened from rma"]
    rows = call("cases.list", {"q": "T-MTR-1"}, "planner-a")["output"]["rows"]
    assert [x["id"] for x in rows] == [cid]
    assert call("cases.list", {"q": "T-MTR-1"}, "planner-b")["output"]["rows"] == []


def test_opened_case_can_be_submitted():
    """MVP-12.4: the case page offers Submit for an opened case with a recommendation, and the server takes it."""
    cid = _open("T-MTR-9")["output"]["case_id"]
    r = call("decision.submit", {"case_id": cid}, "planner-a")
    assert r["ok"], r


def test_ids_count_up():
    a, b = _open("T-MTR-2")["output"]["case_id"], _open("T-MTR-3")["output"]["case_id"]
    assert int(b[3:]) == int(a[3:]) + 1


def test_open_case_is_idempotent():
    first = _open("T-MTR-4")
    assert first["ok"], first
    again = _open("T-MTR-4")
    assert again["ok"] is False and again["error"]["code"] == "duplicate", again
    with SessionLocal() as s:  # the same record from a webhook replay, outside the pipeline: still one case
        with pytest.raises(ActionError) as e:
            intake.open_case(s, {"org_unit_id": "Customer A", "template_key": "industrial", "asset_key": "T-MTR-4",
                                 "reason": "rma", "facts": MOTOR}, "system")  # fmt: skip
        assert e.value.code == "duplicate"
        n = s.execute(text("SELECT count(*) FROM case_record WHERE data->>'assetId' = 'T-MTR-4'")).scalar_one()
    assert n == 1
    assert _open("T-MTR-4", reason="lease_end")["ok"]  # another reason is another case


def test_open_tool_fleet_case_uses_valuer():
    facts = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62}
    r = _open("T-CMH-1", template_key="tool_fleet", reason="contract_end", facts=tool_case_facts("T-CMH-1", facts))
    assert r["ok"], r
    with SessionLocal() as s:
        c = store.get(s, r["output"]["case_id"])
    assert c is not None and c["template"] == "tool_fleet"
    vc = intake.tool_fleet_case(c["id"], facts)
    want = to_routes(load_template("tool_fleet"), tool_fleet.decide(vc, rules=[], queue=[vc])["all"])
    assert [x["id"] for x in c["routes"]] == list(tool_fleet.PK)
    assert [x["plan"] for x in c["routes"]] == [p.name for p in load_template("tool_fleet").paths]
    assert [x["net"] for x in c["routes"]] == [x["net"] for x in want]
    assert c["recommendation"]["id"] == rank_routes(want)["id"]


def test_open_device_case_uses_valuer():
    facts = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12}
    r = _open("T-LOT-1", template_key="device", reason="trade_in", facts=facts)
    assert r["ok"], r
    with SessionLocal() as s:
        c = store.get(s, r["output"]["case_id"])
    assert c is not None and [x["id"] for x in c["routes"]] == ["buynow", "offers", "auction", "market"]
    assert c["recommendation"] is not None


def test_unknown_org_refused():
    r = _open("T-MTR-5", user="admin", org_unit_id="No such unit")
    assert r["ok"] is False and r["error"]["code"] == "not_found", r


def test_bad_input_refused():
    assert _open("T-MTR-6", reason="whim")["error"]["code"] == "validation_error"
    assert _open("T-MTR-6", template_key="nope")["error"]["code"] == "validation_error"
    assert _open("T-MTR-6", facts={"grade": "B"})["error"]["code"] == "validation_error"  # no asset class


def test_planner_other_org_refused():
    r = _open("T-MTR-7", org_unit_id="Customer B")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r


def test_roles_without_open_cases_refused():
    assert _open("T-MTR-8", user="approver")["error"]["code"] == "out_of_scope"


def _stored(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def test_r19_reevaluate_data_opened_industrial_case_keeps_open_numbers():
    cid = _open("T-MTR-R19")["output"]["case_id"]
    opened = _stored(cid)["recommendation"]
    assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    again = _stored(cid)["recommendation"]
    assert (again["id"], again["net"]) == (opened["id"], opened["net"])


def test_r19_record_result_on_tool_fleet_case_uses_decide_case():
    facts = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62}
    cid = _open("T-CMH-R19", template_key="tool_fleet", reason="contract_end", facts=tool_case_facts("T-CMH-R19", facts))[
        "output"
    ]["case_id"]
    r = call("evidence.recordResult", {"case_id": cid}, "admin")
    assert r["ok"], r
    c = _stored(cid)
    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    assert c["recommendation"] is not None and (c["recommendation"]["id"], c["recommendation"]["net"]) == (d.route, d.net)
