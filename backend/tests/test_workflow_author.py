"""P9-8.12 (enabler `workflow_author`, R16): `workflow.author` drafts a workflow graph from a sentence.

With a model, the model drafts the graph as typed Pydantic AI output and code checks it (the typed shape, the block settings
against the source's real fields, the graph rules of `workflow.validate`, the sources the caller may read); each failed check
goes back to the model as `(node, field, message)`, at most three repair rounds (four tries), then a hand-over with the
errors and no draft. With no model the keyword planner answers. A valid graph is test run (dry) and saved as a draft with
every node `ai: 1`; publishing stays a person's (golden rule 10). Every model here is a `FunctionModel`: no live provider.
"""

import json
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel

from di.core import state
from di.core.db import SessionLocal
from di.services.agents import runtime
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.workflow import graph_model as gm
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
models.ALLOW_MODEL_REQUESTS = False

PROMPT = "every 15 minutes pull returns from rl and drop records without a serial"
USER = "developer"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model unless a test installs one
    yield
    runtime.set_loop(None)
    starting.reset()


def _scripted(outputs: list[dict[str, Any]], prompts: list[str] | None = None) -> list[int]:
    """Install a model that answers with `outputs` in turn (the last one repeats); returns the list of its calls."""
    calls: list[int] = []

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        if prompts is not None:
            prompts.append(str(messages[-1]))
        out = outputs[min(len(calls), len(outputs) - 1)]
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn)))
    return calls


def _typed(graph: dict[str, Any]) -> dict[str, Any]:
    """The planner's graph in the shape a model writes: id, k, ref, cfg and the edges' ends."""
    return {
        "nodes": [{k: n[k] for k in ("id", "k", "ref", "cfg") if k in n} for n in graph["nodes"]],
        "edges": [{"a": e["a"], "b": e["b"]} for e in graph["edges"]],
    }


def _good_graph() -> dict[str, Any]:
    r = call("workflow.plan", {"prompt": PROMPT, "answers": {"_defaults": True, "steps": ["x_filter"]}}, USER)
    return _typed(r["output"]["plan"]["graph"])


def _draft(graph: dict[str, Any], **over: Any) -> dict[str, Any]:
    return {"plan": ["read returns from rl", "filter", "map"], "name": "Returns ingest", "trigger": {"t": "schedule", "min": 15},
            "graph": graph} | over  # fmt: skip


def _author(prompt: str = PROMPT, user: str = USER, **extra: Any) -> dict[str, Any]:
    r = call("workflow.author", {"prompt": prompt, **extra}, user)
    assert r["ok"] is True, r
    out: dict[str, Any] = r["output"]
    return out


def _drafts(wid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        return [d for d in state.items(s, "workflow_drafts") if d.get("wf") == wid]


def _workflows() -> int:
    return len(client.get("/api/screens/workflows", headers=h(USER)).json()["workflows"])


def test_workflow_author_no_key_uses_planner():
    r = _author()
    assert r["status"] == "drafted" and r["by_model"] is False and r["rounds"] == 0 and r["errors"] == [], r
    assert r["trigger"] == {"t": "schedule", "min": 15}
    refs = [n["ref"] for n in r["graph"]["nodes"]]
    assert "x_filter" in refs and "rl" in refs
    assert all(n["ai"] == 1 for n in r["graph"]["nodes"])
    assert r["test_run"] and {"in", "out", "held", "status"} <= set(r["test_run"]), r["notes"]
    (d,) = _drafts(r["draft_id"])
    assert all(n["ai"] == 1 for n in d["graph"]["nodes"]) and d["trig"] == {"t": "schedule", "min": 15}
    # the filter names the serial field when the records have it (the synced main stack), else the notes say it was not
    # found (a fresh database): said, never invented
    flt = next(n for n in r["graph"]["nodes"] if n["ref"] == "x_filter")
    assert "serial" in str(flt.get("cfg", {})) or any("serial" in n for n in r["notes"]), (flt, r["notes"])


def test_workflow_author_asks_what_the_planner_asks():
    r = _author("pull something every hour")
    assert r["status"] == "questions" and r["draft_id"] is None and r["graph"] is None
    assert r["questions"][0]["id"] in ("type", "system")


def test_workflow_author_model_draft_accepted_and_saved():
    prompts: list[str] = []
    calls = _scripted([_draft(_good_graph())], prompts)
    r = _author()
    assert r["status"] == "drafted" and r["by_model"] is True and r["rounds"] == 1 and len(calls) == 1
    assert r["test_run"], r["notes"]
    assert r["name"] == "Returns ingest" and r["draft_id"] and r["test_run"]["status"] in ("success", "held")
    assert PROMPT in prompts[0] and "<<<" in prompts[0]  # the sentence is data inside a fence, never an instruction
    (d,) = _drafts(r["draft_id"])
    assert [n["id"] for n in d["graph"]["nodes"]] == [n["id"] for n in _good_graph()["nodes"]]
    assert all(n["ai"] == 1 for n in d["graph"]["nodes"])


def test_workflow_author_repairs_in_three_rounds():
    good = _good_graph()
    unknown = {"nodes": [{"id": "x", "k": "xf", "ref": "x_nope"}], "edges": []}
    no_field = {"nodes": [{"id": "f", "k": "xf", "ref": "x_filter", "cfg": {"condition": [{"check": "present"}]}}], "edges": []}
    prompts: list[str] = []
    calls = _scripted([_draft(unknown), _draft(no_field), _draft(good)], prompts)
    r = _author()
    assert r["status"] == "drafted" and r["rounds"] == 3 and len(calls) == 3 and r["draft_id"] and r["errors"] == []
    assert "x_nope" in prompts[1]  # the error of round 1 went back to the model, with its step
    assert "cfg.condition.0.field" in prompts[2]  # and the one of round 2, naming the setting


def test_workflow_author_takes_the_planner_graph_after_three_failed_repairs():
    """27 Nov 2026: a model whose every draft fails the checks no longer leaves the person without a draft. After the first
    try and three repair rounds the planner's graph goes through the same checks and is saved, marked as not the model's."""
    unknown = {"nodes": [{"id": "x", "k": "xf", "ref": "x_nope"}], "edges": []}
    before = _workflows()
    calls = _scripted([_draft(unknown)])
    r = _author()
    assert len(calls) == 4 and r["rounds"] == 4  # the first try and three repair rounds, no more
    assert r["status"] == "drafted" and r["by_model"] is False and r["draft_id"] and r["errors"] == []
    assert not [n for n in r["graph"]["nodes"] if n.get("ref") == "x_nope"]  # none of the refused draft is in it
    assert any("did not pass the checks after 4 tries" in n for n in r["notes"])
    assert _workflows() == before + 1  # one draft, the planner's


def test_workflow_author_repairs_graph_rule_errors():
    good = _good_graph()
    cut = {
        **good,
        "nodes": [{**n, "cfg": {"required": ["nope"]}} if n["ref"] == "x_val" else n for n in good["nodes"]],
    }  # a field the records lack
    calls = _scripted([_draft(cut), _draft(good)])
    r = _author()
    assert r["status"] == "drafted" and r["rounds"] == 2 and len(calls) == 2


def test_workflow_author_model_cannot_read_an_unreadable_source():
    good = _good_graph()
    bad = {"nodes": [{**n, "ref": "iot"} if n["k"] == "conn" else n for n in good["nodes"]], "edges": good["edges"]}
    prompts: list[str] = []
    _scripted([_draft(bad), _draft(good)], prompts)
    r = _author()
    assert r["status"] == "drafted" and r["rounds"] == 2
    assert "iot" in prompts[1]  # the second try was told which source the caller cannot read


def test_workflow_author_never_publishes():
    r = call("workflow.author", {"prompt": PROMPT}, USER)  # a person's call, to compare with
    assert r["ok"] is True
    hdr = h(USER) | {"X-Circularity-Preparer": "gap"}
    a = client.post("/api/actions/workflow.author", json={"prompt": PROMPT}, headers=hdr).json()
    assert a["ok"] is True, a
    wid = a["output"]["workflow_id"]
    pub = client.post("/api/actions/workflow.publish", json={"id": wid}, headers=hdr).json()
    assert pub["ok"] is False and pub["error"]["code"] == "approval_required"
    shown = client.get("/api/screens/workflows", headers=h(USER)).json()["workflows"]
    assert next(w for w in shown if w["id"] == wid)["status"] == "draft"


def test_workflow_author_refuses_unreadable_source():
    before = _workflows()
    r = call("workflow.author", {"prompt": "every hour read telemetry from the device telemetry system"}, USER)
    assert r["ok"] is False and "Device telemetry" in r["error"]["message"]
    assert _workflows() == before


def test_workflow_author_needs_manage_workflows():
    r = call("workflow.author", {"prompt": PROMPT}, "exec")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"


# ---------------------------------------------------------------- the typed graph (di.workflow.graph_model)
def test_graph_model_errors_name_the_step_and_the_setting():
    g, errs = gm.parse({"nodes": [{"id": "f", "k": "xf", "ref": "x_fx", "cfg": {"currency": "XXX", "bogus": 1}}], "edges": []})
    assert g is None and {(e["node"], e["field"]) for e in errs} == {("f", "cfg.currency"), ("f", "cfg.bogus")}
    _, errs = gm.parse({"nodes": [{"id": "z", "k": "banana", "ref": "x"}], "edges": []})
    assert errs[0]["node"] == "z" and "No block" in errs[0]["message"]


def test_graph_model_engine_graph_lays_out_orders_and_marks():
    g, errs = gm.parse(
        {
            "nodes": [
                {"id": "r", "k": "conn", "ref": "rl"},
                {"id": "b", "k": "xf", "ref": "x_branch"},
                {"id": "m", "k": "map", "ref": "rl"},
                {"id": "e", "k": "xf", "ref": "x_err"},
            ],
            "edges": [{"a": "b", "b": "e", "port": "else"}, {"a": "r", "b": "b"}, {"a": "b", "b": "m"}],
        }  # fmt: skip
    )
    assert g is not None and errs == [] and gm.structure_errors(g) == []
    out = gm.engine_graph(g)
    assert [n["x"] for n in out["nodes"]] == [24, 230, 436, 436] and all(n["ai"] == 1 for n in out["nodes"])
    assert [(e["a"], e["b"]) for e in out["edges"]] == [("r", "b"), ("b", "m"), ("b", "e")]  # the else edge goes last
    assert json.dumps(out)


def test_graph_model_structure_errors():
    g, _ = gm.parse(
        {"nodes": [{"id": "r", "k": "conn", "ref": "rl"}, {"id": "r", "k": "map", "ref": "rl"}], "edges": [{"a": "r", "b": "q"}]}
    )
    assert g is not None
    msgs = " ".join(e["message"] for e in gm.structure_errors(g))
    assert "used twice" in msgs and "not a step" in msgs
