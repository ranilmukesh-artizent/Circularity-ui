"""U2 (audit 2026-11-24): the calibration models of a template, as a read action for agents and API clients (the
Modeler's and Agents page's panel reads GET /api/screens/agents/models).

model.list  read  {template?}  the template's models, the newest first (default industrial); for a person who may
                               fit (manageFlows) or promote (approve.flows) models
"""

from tests.helpers import call
from tests.test_model_promote import outcomes  # noqa: F401 - the fixture: five confirmed outcomes, no models


def test_lists_the_models_newest_first(outcomes):  # noqa: F811 - the fixture
    a = call("model.fit", {}, "planner-a")["output"]
    b = call("model.fit", {}, "planner-a")["output"]
    assert call("model.propose", {"id": a["id"]}, "planner-a")["ok"]  # two steps: a person proposes, another promotes
    assert call("model.promote", {"id": a["id"]}, "approver")["ok"]
    out = call("model.list", {}, "approver")
    assert out["ok"], out
    o = out["output"]
    assert o["template"] == "industrial"
    assert [(m["id"], m["status"]) for m in o["models"]] == [(b["id"], "candidate"), (a["id"], "active")]
    assert o["models"][0]["metrics"]["n"] == 5 and o["models"][1]["approved_by"] == "approver"
    assert call("model.list", {"template": "device"}, "planner-a")["output"] == {"template": "device", "models": []}


def test_only_who_fits_or_promotes_reads_them():
    out = call("model.list", {}, "finance")
    assert not out["ok"] and out["error"]["code"] == "out_of_scope"
    bad = call("model.list", {"template": "nope"}, "admin")
    assert not bad["ok"] and bad["error"]["code"] == "validation_error"
