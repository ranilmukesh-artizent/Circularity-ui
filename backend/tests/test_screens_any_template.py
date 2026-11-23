"""MVP-8.3: the case pages render a case of any template.

A tool-fleet case and a device case are opened from data (case.open); every endpoint the case page and the asset pages
call answers 200 for them and shows the template's routes (`plan`: the template's path names). The class tables of
the industrial template (new price, components, labour ...) take the template's stand-in class
(di.services.engine.predictor.engine_class); the demo's cases keep their own (tests/test_screens_case.py).
"""

import pytest

from di.services.engine.predictor import CLASSES, engine_class
from di.services.modeler.templates import load_template
from tests import starting
from tests.helpers import call, client, h

FACTS = {
    "tool_fleet": {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62},
    "device": {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12},
}


@pytest.fixture(scope="module")
def opened() -> dict[str, str]:
    starting.reset()
    out = {}
    for t, facts in FACTS.items():
        body = {"org_unit_id": "Customer A", "template_key": t, "asset_key": f"T-ANY-{t}", "reason": "manual",
                "facts": facts}  # fmt: skip
        r = call("case.open", body, "planner-a")
        assert r["ok"], r
        out[t] = r["output"]["case_id"]
    yield out
    starting.reset()


def _paths(t: str) -> list[str]:
    return [p.name for p in load_template(t).paths]


@pytest.mark.parametrize("template", list(FACTS))
@pytest.mark.parametrize("user", ["admin", "planner-a"])
def test_case_pages_answer_for_any_template(opened, template, user):
    cid = opened[template]
    page = client.get(f"/api/screens/case/{cid}", headers=h(user))
    assert page.status_code == 200, page.text
    assert [r["plan"] for r in page.json()["case"]["routes"]] == _paths(template)
    analysis = client.get(f"/api/screens/case/{cid}/analysis", headers=h(user))
    assert analysis.status_code == 200, analysis.text
    for url in (f"/api/screens/product/journey/{cid}", f"/api/screens/product/asset/{cid}"):
        r = client.get(url, headers=h(user))
        assert r.status_code == 200, (url, r.text)
    for a in ("case.get", "case.routes", "case.trace", "case.evidence", "asset.compare"):
        r = call(a, {"case_id": cid}, user)
        assert r["ok"], (a, r)
    routes = call("case.routes", {"case_id": cid}, user)["output"]
    assert routes


def test_lists_answer_with_template_cases(opened):
    for url in ("/api/screens/product/returned", "/api/screens/command/kpis", "/api/screens/command/charts",
                "/api/screens/command/exceptions", "/api/screens/command/actions", "/api/screens/command/inbox"):  # fmt: skip
        r = client.get(url, headers=h("admin"))
        assert r.status_code == 200, (url, r.text)
    rows = call("cases.list", {"q": "T-ANY-", "limit": 10}, "admin")["output"]["rows"]
    assert sorted(x["id"] for x in rows) == sorted(opened.values())


def test_engine_class_keeps_the_demos_classes():
    for cls in CLASSES:
        assert engine_class({"cls": cls}) == cls
    assert engine_class({"cls": "CMH", "template": "tool_fleet"}) == "drill"
    assert engine_class({"cls": "device", "template": "device"}) == "it"
