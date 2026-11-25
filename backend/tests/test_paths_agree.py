"""P9-1.5 (R19, Review Focus 3): the same case decided by intake, re-evaluation, simulation and `decide_case` gives the same
route and the same net, to the cent. The chain (P9-2.1) and replay (P9-7.2) join by extending these tests. Every test ends
with the starting state."""

from typing import Any

import pytest

from di.core.db import SessionLocal
from di.repositories.live_rules import flow_version, live_pack
from di.services.cases import store
from di.services.cases.decide import decide_case
from tests import flowkit, starting
from tests.helpers import call, client, h, tool_case_facts

ORG = "Customer A"
ORDER = {"kind": "lease", "id": "L-1", "renew": True, "who": "Acme Rentals", "site": "Houston", "need": 9, "rate": 900,
         "term": 24, "what": "Fleet contract L-1 renews", "when": "renewal confirmed"}  # fmt: skip
FACTS = {
    "tool_fleet": {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 60, "dem": {"lease": [ORDER]}},
    "device": {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 300, "qty": 20},
}


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    flowkit.reset_flows()
    yield
    starting.reset()
    flowkit.reset_flows()


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _queue_row(template: str, cid: str) -> dict[str, Any]:
    page = client.get("/api/screens/modeler", params={"template": template, "org": ORG}, headers=h("planner-a"))
    assert page.status_code == 200, page.text
    return next(q for q in page.json()["queue"] if q["id"] == cid)


def _paths_agree(template: str) -> None:
    body = {
        "org_unit_id": ORG,
        "template_key": template,
        "asset_key": f"T-PA-{template}",
        "reason": "manual",
        "facts": tool_case_facts(f"T-PA-{template}", FACTS[template]) if template == "tool_fleet" else FACTS[template],
    }
    opened = call("case.open", body, "planner-a")
    assert opened["ok"], opened
    cid = opened["output"]["case_id"]
    c = _case(cid)
    seen = {"opened": (c["recommendation"]["id"], c["recommendation"]["net"])}

    assert call("decision.submit", {"case_id": cid}, "planner-a")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Check again."}, "approver")["ok"]
    assert _case(cid)["stage"] == "reeval"
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    c = _case(cid)
    seen["reevaluated"] = (c["recommendation"]["id"], c["recommendation"]["net"])

    row = _queue_row(template, cid)
    seen["simulation"] = (row["best"], row["net"])

    with SessionLocal() as s:
        d = decide_case(cid, live_pack(s, c), flow_version(s, c), session=s)
    seen["decide_case"] = (d.route, d.net)

    routes = {path[0] for path in seen.values()}
    assert len(routes) == 1, seen
    nets = [path[1] for path in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen


def test_paths_agree_tool_fleet():
    _paths_agree("tool_fleet")


def test_paths_agree_device():
    _paths_agree("device")
