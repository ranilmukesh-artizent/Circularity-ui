"""MVP-8.1: opening a case from data (`case.open`, di.services.cases.intake).

    case.open  act  {org_unit_id, template_key, asset_key, reason, facts?}   openCases (Admin, Developer, Planner)

A new case gets the next RT-<n> above the highest, belongs to the org unit, starts at the first stage and is valued by
the engine (industrial) or the template's valuer (tool fleet, device), then the live rules. The same asset and reason
twice open one case (Review Focus 5). Every test ends with the starting state (the opened cases are dropped).
"""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.actions.registry import ActionError
from di.services.cases import intake, store
from di.services.engine.routes import rank_routes
from di.services.modeler.templates import load_template
from di.services.modeler.valuers import tool_fleet
from di.services.modeler.valuers.routes_adapter import to_routes
from tests import starting
from tests.helpers import call

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
    assert (c["owner"], c["template"], c["stage"], c["assetId"]) == ("Customer A", "industrial", "none", "T-MTR-1")
    assert (c["cls"], c["grade"], c["age"], c["qty"]) == ("motor", "B", 4, 1)
    assert [r["id"] for r in c["routes"]] == ["resale", "redeploy", "relase", "intparts", "extparts", "material", "exit"]
    assert c["recommendation"] is rank_routes(c["routes"], None)
    assert c["intake"]["reason"] == "rma" and c["flowVer"] >= 0
    assert [x[0] for x in log] == ["Case opened from rma"]
    rows = call("cases.list", {"q": "T-MTR-1"}, "planner-a")["output"]["rows"]
    assert [x["id"] for x in rows] == [cid]
    assert call("cases.list", {"q": "T-MTR-1"}, "planner-b")["output"]["rows"] == []


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
    r = _open("T-CMH-1", template_key="tool_fleet", reason="contract_end", facts=facts)
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
