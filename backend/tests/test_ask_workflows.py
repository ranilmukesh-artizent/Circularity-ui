"""P9-2.23: Ask reads workflows and their runs (user review 25 Nov 2026: "why did WF-116 fail", answered "no access").

- test_ask_workflow_run_failure: get_workflow_run gives the failed step, the upstream error, the retries and the log;
  the reply of a model that names them passes its checks (by_model true); with no model the rules answer the same
- test_ask_workflow_id_not_a_case: get_case is never run with a WF- or RUN- id; an unknown workflow is "no workflow
  WF-999 you can see", never a case, never "no access"
- test_ask_workflow_number_check: a count that is in no tool result is refused, the model retries once, then the rules
  answer (`by_model` false)
- test_ask_workflow_access: a person who cannot open Workflow Studio gets not_found and no run detail
- test_ask_tools_read_only: the new tools reach reads only; the write buttons (run, reprocess, apply fix) are no tool
The model is a deterministic in-process AskModel (tests/test_ask.py Fake), never a live provider. The failing run is the
demo's seeded WF-116 run, read from the workflow, not typed in.
"""

import json

import pytest

from di.core import state
from di.core.db import SessionLocal
from di.main import app
from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import agent_mode
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.ask import tools
from di.services.ask.model import NoModel, get_model
from tests import starting
from tests.helpers import call
from tests.test_ask import Fake, ask, once, use

STUDIO = {"page": "integration", "section": "studio"}
WF_TOOLS = {"list_workflows": "workflow.list", "get_workflow": "workflow.get", "get_workflow_run": "workflow.runGet"}


def setup_module():
    starting.reset()


def teardown_module():
    app.dependency_overrides.clear()
    starting.reset()


@pytest.fixture(autouse=True)
def _no_override():
    yield
    app.dependency_overrides.pop(get_model, None)


@pytest.fixture(scope="module")
def failed_run() -> dict:
    """WF-116's latest run as the workflow records it (a failed run at Validation & enrichment)."""
    with SessionLocal() as s:
        w = state.get(s, "workflows", "WF-116")
    assert w["lastRun"]["status"] == "failed"
    return {"id": w["lastRun"]["id"], "rows": w["last"]["rows"], "note": w["last"]["note"]}


def question(run_id: str) -> str:
    return f"Why did Ingest · Oracle Depot Repair (WF-116) fail at Validation & enrichment in run {run_id}, and how do I fix it?"


def explain(seen: list) -> str:
    d = seen[0][1]["data"]
    return (
        f"Run {d['run']['id']} of {d['workflow']['id']} failed at {d['failed_step']['label']}: {d['error']}. "
        f"The run retried {d['retries']} times and read {d['run']['records_read']} records. Use Diagnose or Fix on the page."
    )


def test_ask_workflow_run_failure(failed_run):
    fake = Fake(once(("get_workflow_run", {"id": failed_run["id"]})), explain)
    use(fake)
    _, final = ask("developer", question(failed_run["id"]), context=STUDIO)
    (_, r) = fake.seen[0]
    assert r["ok"] is True
    d = r["data"]
    assert d["failed_step"]["label"] == "Validation & enrichment" and d["failed_step"]["state"] == "failed"
    assert d["error"] == failed_run["note"] and "connection reset" in d["error"]
    assert d["retries"] == 3 and d["run"]["records_read"] == failed_run["rows"]
    assert any("ERROR" in x and "connection reset" in x for x in d["log"])
    assert {s["state"] for s in d["steps"]} >= {"success", "failed", "upstream_failed"}
    assert final["provider"] == "fake" and final["by_model"] is True and final["fallback_reason"] is None
    assert "Validation & enrichment" in final["text"] and "connection reset" in final["text"] and "3 times" in final["text"]
    assert [(t["name"], t["ok"]) for t in final["tools"]] == [("get_workflow_run", True)]
    # the page and the id shapes steer the model
    assert "WF-nnn" in fake.requests[0].system and "Workflow Studio" in fake.requests[0].system


def test_ask_workflow_run_failure_without_a_model(failed_run):
    use(NoModel("disabled"))
    _, final = ask("developer", question(failed_run["id"]), context=STUDIO)
    assert final["provider"] == "fallback" and final["by_model"] is False
    t = final["text"]
    assert "Validation & enrichment" in t and "connection reset" in t and "3 retries" in t and str(failed_run["rows"]) in t
    assert failed_run["id"] in t and "WF-116" in t
    assert [x["name"] for x in final["tools"]] == ["workflow.runGet"] and final["tools"][0]["ok"] is True
    assert final["refused"] == [] and "case" not in t.lower()


def test_ask_workflow_id_not_a_case(monkeypatch, failed_run):
    seen_actions: list[str] = []
    real = tools.invoke
    monkeypatch.setattr(tools, "invoke", lambda a, i, c: (seen_actions.append(a), real(a, i, c))[1])
    fake = Fake(
        once(
            ("get_case", {"case_id": "WF-116"}), ("get_case", {"case_id": failed_run["id"]}), ("get_workflow", {"id": "WF-999"})
        ),
        lambda seen: "There is no workflow WF-999 you can see.",
    )
    use(fake)
    _, final = ask("developer", "Why did WF-116 fail?", context=STUDIO)
    wrong, wrong2, missing = (r for _, r in fake.seen)
    assert wrong["error"]["code"] == wrong2["error"]["code"] == "wrong_kind" and "workflow" in wrong["error"]["message"]
    assert "run" in wrong2["error"]["message"] and "get_workflow" in wrong["error"]["message"]
    assert "case.get" not in seen_actions and "case.evidence" not in seen_actions and seen_actions == ["workflow.get"]
    assert missing["error"] == {"code": "not_found", "message": "There is no workflow WF-999 you can see."}
    assert "case" not in final["text"].lower() and "access" not in final["text"].lower()


def test_ask_workflow_id_not_a_case_without_a_model():
    use(NoModel("disabled"))
    _, final = ask("developer", "Why did WF-999 fail?", context=STUDIO)
    assert final["text"] == "There is no workflow WF-999 you can see."
    assert "case" not in final["text"].lower() and "access" not in final["text"].lower()
    assert final["refused"][0]["code"] == "not_found"


def test_ask_workflow_number_check(failed_run):
    """A count that is in no tool result: refused, one retry with the reasons, then the rules answer."""
    rid = failed_run["id"]

    def wrong(seen):
        return f"Run {rid} failed at Validation & enrichment and held 7,777 records."

    fake = Fake(once(("get_workflow_run", {"id": rid})), wrong)
    use(fake)
    ev, final = ask("developer", question(rid), context=STUDIO)
    assert len(fake.requests) == 2 and "7,777" in json.dumps(fake.requests[1].conversation)
    assert final["provider"] == "fallback" and final["by_model"] is False and final["fallback_reason"] == "unchecked"
    assert "7,777" not in final["text"] and "connection reset" in final["text"]
    assert not any(e == "reset" for e, _ in ev)  # the refused text never reached the person


def test_ask_workflow_number_check_retry_passes(failed_run):
    rid = failed_run["id"]

    class Retrying(Fake):
        def __init__(self):
            super().__init__(once(("get_workflow_run", {"id": rid})), lambda seen: "")

        def say_now(self):
            return (
                f"Run {rid} failed at Validation & enrichment after 3 retries."
                if len(self.requests) > 1
                else f"Run {rid} failed at Validation & enrichment after 9 retries."
            )

        def answer(self, request, toolbox):
            self.say = lambda seen: self.say_now()
            return super().answer(request, toolbox)

    fake = Retrying()
    use(fake)
    _, final = ask("developer", question(rid), context=STUDIO)
    assert len(fake.requests) == 2 and final["by_model"] is True and "after 3 retries" in final["text"]


def test_ask_workflow_access(failed_run):
    rid = failed_run["id"]
    fake = Fake(
        once(("get_workflow_run", {"id": rid}), ("get_workflow", {"id": "WF-116"}), ("list_workflows", {})),
        lambda seen: "There is no workflow WF-116 you can see.",
    )
    use(fake)
    _, final = ask("planner-a", question(rid), context=STUDIO)
    run, wf, lst = (r for _, r in fake.seen)
    assert run == {"ok": False, "error": {"code": "not_found", "message": f"There is no run {rid} you can see."}}
    assert wf == {"ok": False, "error": {"code": "not_found", "message": "There is no workflow WF-116 you can see."}}
    assert lst["ok"] is False and lst["error"]["code"] == "not_found"
    blob = json.dumps(final)
    assert "connection reset" not in blob and "Validation" not in blob.replace(question(rid), "")
    # the same refusal through the action endpoint, and for a workflow that does not exist
    assert call("workflow.runGet", {"id": rid}, "planner-a")["error"]["code"] == "not_found"
    assert call("workflow.get", {"id": "WF-999"}, "developer")["error"]["code"] == "not_found"


def test_ask_workflow_source_outside_the_tenant(monkeypatch, failed_run):
    """A tenant-scoped person whose tenant does not cover the workflow's source's org unit gets not_found."""
    from di.services.actions import workflow_read

    monkeypatch.setattr(workflow_read, "_source_org", lambda s, w: "ou-elsewhere")
    monkeypatch.setattr(workflow_read.policy, "tenant_ok", lambda *a, **k: False)
    r = call("workflow.runGet", {"id": failed_run["id"]}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "not_found"


def test_ask_tools_read_only():
    assert set(WF_TOOLS) <= set(tools.TOOL_NAMES)
    for name, action in WF_TOOLS.items():
        assert tools.ACTION_TOOLS[name][0] == action and ACTIONS[action].risk == "read"
        assert not action.startswith(FORBIDDEN_ACTIONS) and agent_mode(ACTIONS[action]) == "yes"
    for a in ("workflow.get", "workflow.list", "workflow.runs", "workflow.runGet"):
        assert ACTIONS[a].risk == "read" and ACTIONS[a].handler is not None
    reached = {a for a, *_ in tools.ACTION_TOOLS.values()}
    assert not reached & {"workflow.applyFix", "workflow.run", "workflow.reprocess", "workflow.save", "workflow.draft"}
    assert all(w in FORBIDDEN_ACTIONS for w in ("workflow.publish", "workflow.setStatus", "workflow.delete"))
    # a model that calls a write button by name gets nothing run
    fake = Fake(
        once(*[(n, {"id": "WF-116"}) for n in ("workflow_run", "workflow.applyFix", "reprocess_workflow")]),
        lambda seen: "Nothing changed.",
    )
    use(fake)
    ask("developer", "Run WF-116 again", context=STUDIO)
    assert [r["error"]["code"] for _, r in fake.seen] == ["not_found"] * 3


def test_ask_workflow_list_and_get():
    fake = Fake(once(("list_workflows", {"status": "failing"}), ("get_workflow", {"id": "WF-116"})), lambda seen: "Read them.")
    use(fake)
    ask("developer", "Which workflows are failing?", context=STUDIO)
    (_, lst), (_, one) = fake.seen
    assert lst["ok"] and "WF-116" in [w["id"] for w in lst["data"]["workflows"]]
    assert all(w["status"] == "failing" for w in lst["data"]["workflows"])
    d = one["data"]
    assert d["workflow"]["id"] == "WF-116" and d["workflow"]["version"] and d["workflow"]["trigger"]
    assert d["blocks"] and d["last_run"]["state"] == "failed" and d["recent_runs"]
