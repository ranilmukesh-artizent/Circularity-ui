"""P9-1.13 (story X-09): views come from the pack. KPIs and the two analytics questions are data (`kpis[].measure`,
`analytics[].query`, computed by `di.services.modeler.kpis`); My work reads its exception labels, owners and actions from
`runtime.exception_types` and shows the pack KPIs; the case page lists the stage agents of its pack. A new pack is served
with no page code. The industrial demo's screens are unchanged (no KPI, no stage agents). Every test ends with the
starting state."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.cases import process
from di.services.modeler import kpis
from di.services.modeler.pack import load_pack, parse_pack
from tests import flowkit, starting
from tests.helpers import call, client, h, tool_case_facts

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "packs" / "rental_std_test.json"
ORG = "Customer A"
TOOLS = [
    {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62},
    {"cls": "CMH", "grade": "C", "ft": "Repair center", "site": "Houston", "rul": 40},
]


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM work_item"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    _clean()
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _open(key: str, asset: str, facts: dict[str, Any]) -> str:
    body = {
        "org_unit_id": ORG,
        "template_key": key,
        "asset_key": asset,
        "reason": "manual",
        "facts": tool_case_facts(asset, facts) if key == "tool_fleet" else facts,
    }
    return str(ok(call("case.open", body, "planner-a"))["case_id"])


def _pack_view(key: str, user: str = "admin") -> dict[str, Any]:
    r = client.get("/api/screens/analytics/pack", params={"key": key}, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def _case(rec: str, net: float = 0, received: str = "2026-11-02T10:00:00.000Z", **more: Any) -> dict[str, Any]:
    return {"id": rec, "template": "tool_fleet", "received": received, "recommendation": {"id": rec, "net": net}} | more


def _kpi(pack_key: str, kpi_id: str):
    return next(k for k in load_pack(pack_key).kpis if k.id == kpi_id)


def test_x_09_kpis_from_pack_data():
    cases = [_case("release", 100), _case("resell", 200), _case("exit", -30)]
    got = kpis.compute(_kpi("tool_fleet", "redeploy_rate"), cases)
    assert got["unit"] == "%" and got["value"] == pytest.approx(33.3, abs=0.05)
    assert kpis.compute(_kpi("tool_fleet", "value_per_tool"), cases)["value"] == pytest.approx(90)
    held = [_case("resell", 1, gateHold={"gates": ["G-1"]}), _case("resell", 1, gates=[{"passed": False}]), _case("resell", 1)]
    assert kpis.compute(_kpi("tool_fleet", "held_by_guardrails"), held)["value"] == pytest.approx(66.7, abs=0.05)
    # the three the plan leaves to later phases show no data
    for kid in ("days_to_next_use", "straight_through", "upgrade_accepted"):
        assert kpis.compute(_kpi("tool_fleet", kid), cases)["value"] is None
    lots = [
        {"ref": 200, "recommendation": {"id": "market", "net": 150}},
        {"ref": 100, "recommendation": {"id": "market", "net": 25}},
    ]
    lots[0]["evidenceRecords"] = [{"type": "data_wipe", "result": "pass", "at": "2026-11-01T00:00:00Z", "source": "lab"}]
    assert kpis.compute(_kpi("device", "recovery_rate"), lots)["value"] == pytest.approx(50)
    assert kpis.compute(_kpi("device", "wipe_compliance"), lots)["value"] == pytest.approx(50)


def test_x_09_measure_grammar():
    def kpi(measure: dict[str, Any], trend: str | None = None):
        return parse_pack(
            {
                **json.loads(FIXTURE.read_text(encoding="utf-8")),
                "kpis": [{"id": "k", "label": "K", "definition": "d", "measure": measure, "trend": trend}],
            }
        ).kpis[0]

    cases = [
        _case("a", 10, received="2026-11-02T00:00:00Z"),
        _case("b", 30, received="2026-11-03T00:00:00Z"),
        _case("a", 50, received="2026-12-01T00:00:00Z"),
    ]
    only_a = [{"fact": "recommendation.id", "op": "eq", "value": "a"}]
    assert kpis.compute(kpi({"kind": "count", "where": only_a}), cases)["value"] == 2
    assert kpis.compute(kpi({"kind": "sum", "of": "recommendation.net", "where": only_a}), cases)["value"] == 60
    assert kpis.compute(kpi({"kind": "avg", "of": "recommendation.net"}), cases)["value"] == pytest.approx(30)
    over = [{"fact": "recommendation.net", "op": "gte", "value": 30}]
    assert kpis.compute(kpi({"kind": "share", "where": only_a, "over": over}), cases)["value"] == pytest.approx(50)
    assert kpis.compute(kpi({"kind": "avg", "of": "recommendation.net / ref"}), cases)["value"] is None
    assert kpis.compute(kpi({"kind": "count"}), [])["value"] is None
    monthly = kpis.compute(kpi({"kind": "avg", "of": "recommendation.net"}, "monthly"), cases)["trend"]
    assert monthly == [{"period": "2026-11", "value": 20}, {"period": "2026-12", "value": 50}]
    weekly = kpis.compute(kpi({"kind": "count"}, "weekly"), cases)["trend"]
    assert [t["period"] for t in weekly] == ["2026-W45", "2026-W49"]
    with pytest.raises(kpis.KpiError):
        kpis.compute(kpi({"kind": "median", "of": "x"}), cases)


def test_x_09_two_analytics_questions():
    for key in ("tool_fleet", "device"):
        assert len(load_pack(key).analytics) == 2 and all(q.query for q in load_pack(key).analytics)
    ids = [_open("tool_fleet", f"T-CMH-{i}", f) for i, f in enumerate(TOOLS)]
    view = _pack_view("tool_fleet", "planner-a")
    assert [q["question"] for q in view["questions"]] == [q.question for q in load_pack("tool_fleet").analytics]
    for q in view["questions"]:
        assert q["rows"] and all({"key", "value"} <= set(r) for r in q["rows"])
        assert 1 <= len(q["examples"]) <= 5 and set(q["examples"]) <= set(ids)
    assert sum(r["value"] for r in view["questions"][0]["rows"]) == len(ids)


def test_x_09_exception_types_from_pack():
    label = next(t for t in load_pack("tool_fleet").runtime.exception_types if t.id == "not_in_system_of_record")
    cid = _open("tool_fleet", "T-CMH-7", TOOLS[0])
    with SessionLocal() as s:
        process.open_item(
            s, kind="exception", case_id=cid, org_unit_id=ORG, type="not_in_system_of_record", title="old words",
            cause="why", action="old action", owner_role="Admin", due_hours=None, by="system",
        )  # fmt: skip
        s.commit()
    r = client.get("/api/screens/mywork", headers=h("admin"))
    assert r.status_code == 200, r.text
    row = next(i for i in r.json()["items"] if i["case_id"] == cid and i["kind"] == "exception")
    assert (row["title"], row["owner"], row["action"]) == (label.label, label.owner_role, label.action)
    assert row["cause"] == "why"
    # a type the pack does not know keeps the row as it was written
    with SessionLocal() as s:
        process.open_item(
            s, kind="exception", case_id=cid, org_unit_id=ORG, type="nothing_like_it", title="Own words", cause=None,
            action="Own action", owner_role="Admin", due_hours=None, by="system",
        )  # fmt: skip
        s.commit()
    rows = client.get("/api/screens/mywork", headers=h("admin")).json()["items"]
    assert any(i["title"] == "Own words" and i["action"] == "Own action" and i["owner"] == "Admin" for i in rows)


def test_x_09_mywork_kpi_strip_follows_visible_cases():
    assert client.get("/api/screens/mywork", headers=h("planner-a")).json()["kpis"] == []  # the demo: no pack KPI
    _open("tool_fleet", "T-CMH-8", TOOLS[0])
    strip = client.get("/api/screens/mywork", headers=h("planner-a")).json()["kpis"]
    assert {k["pack"] for k in strip} == {"tool_fleet"} and len(strip) == len(load_pack("tool_fleet").kpis)
    assert all({"pack", "id", "label", "value", "unit"} <= set(k) for k in strip)
    assert client.get("/api/screens/mywork", headers=h("planner-b")).json()["kpis"] == []  # another tenant's cases


def test_x_09_new_pack_views_need_no_page_code():
    doc = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    doc["kpis"] = [
        {"id": "utilisation_gain", "label": "Utilisation gain", "definition": "mean net", "trend": "monthly",
         "measure": {"kind": "avg", "of": "recommendation.net"}},
        {"id": "units_in", "label": "Units in", "definition": "cases", "measure": {"kind": "count"}},
    ]  # fmt: skip
    doc["analytics"] = [
        {
            "question": "Where do units go?",
            "chart": "bar",
            "query": {"group_by": "recommendation.id", "measure": {"kind": "count"}},
        }
    ]
    pid = int(ok(call("pack.import", {"doc": doc}, "admin"))["id"])
    ok(call("pack.submit", {"id": pid}, "admin"))
    ok(call("pack.approve", {"id": pid}, "approver"))
    cid = _open("rental_std_test", "RS-9", {"rate": 40, "months": 12, "utilisation": 0.8, "prep": 60})
    view = _pack_view("rental_std_test")
    assert [(k["id"], k["label"]) for k in view["kpis"]] == [("utilisation_gain", "Utilisation gain"), ("units_in", "Units in")]
    assert view["kpis"][0]["value"] == pytest.approx(324) and view["kpis"][1]["value"] == 1
    assert view["questions"][0]["rows"] == [{"key": "rerent", "value": 1}] and view["questions"][0]["examples"] == [cid]
    assert view["stages"][0]["key"] == "receive" and "rental_std_test" in {p["key"] for p in view["packs"]}
    assert client.get("/api/screens/analytics/pack", params={"key": "nothing"}, headers=h("admin")).status_code == 404


def test_x_09_pack_view_is_for_analytics_accounts_and_tenant_scoped():
    assert client.get("/api/screens/analytics/pack", params={"key": "tool_fleet"}).status_code == 401
    _open("tool_fleet", "T-CMH-3", TOOLS[0])
    own = _pack_view("tool_fleet", "planner-a")["questions"][0]["rows"]
    other = _pack_view("tool_fleet", "planner-b")["questions"][0]["rows"]
    assert own and other == []
    industrial = _pack_view("industrial")
    assert industrial["kpis"] == [] and industrial["questions"] == []


def test_ui30_pack_view_defaults_and_follows_the_pack():
    r = client.get("/api/screens/analytics/pack", headers=h("admin"))
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["packs"][0]["key"] == "industrial" and first["key"] == "industrial"  # no pack has cases: the primary one
    assert first["worked_questions"] == [] and first["renewals"] is False
    _open("tool_fleet", "T-CMH-30", TOOLS[0])
    got = client.get("/api/screens/analytics/pack", headers=h("admin")).json()
    assert got["key"] == "tool_fleet" and got["cases"] >= 1 and got["renewals"] is True  # the first pack with data
    device = _pack_view("device")
    assert [q["id"] for q in device["worked_questions"]] == ["price_after_launch", "disputes_by_partner"]
    assert device["renewals"] is False
    assert [q["id"] for q in _pack_view("used_cars")["worked_questions"]] == ["wq_uc_1", "wq_uc_2"]


def test_x_09_stage_agents_on_case():
    cid = _open("tool_fleet", "T-CMH-5", TOOLS[0])
    r = client.get(f"/api/screens/case/{cid}", headers=h("planner-a"))
    assert r.status_code == 200, r.text
    got = r.json()["packStages"]
    want = [{"key": s.key, "label": s.label, "agent": s.agent, "autonomy": s.autonomy} for s in load_pack("tool_fleet").stages]
    assert got == want and len(got) == 7
    demo = client.get("/api/screens/case/RT-1051", headers=h("planner-a")).json()
    assert demo["packStages"] is None  # the industrial demo's case page is unchanged


def test_x_09_caseless_exception_takes_its_pack_wording():
    """An item with no case (a manifest serial that never arrived) shows the label and action of the pack that names its
    type (`EX-IT-MISSING`); the cause, which says the serial, stays the row's."""
    label = next(t for t in load_pack("itad").runtime.exception_types if t.id == "EX-IT-MISSING")
    with SessionLocal() as s:
        process.open_item(
            s, kind="exception", case_id=None, org_unit_id=ORG, type="EX-IT-MISSING",
            title="SN-X was expected back and has no case",
            cause="SN-X is on the manifest", action="old action", owner_role="Admin", due_hours=None, by="system",
        )  # fmt: skip
        s.commit()
    rows = client.get("/api/screens/mywork", headers=h("admin")).json()["items"]
    row = next(i for i in rows if i["cause"] == "SN-X is on the manifest")
    assert (row["title"], row["action"]) == (label.label, label.action)
