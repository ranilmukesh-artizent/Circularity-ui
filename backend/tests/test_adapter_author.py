"""P9-8.7 (enabler: "Adapter generation drafts a declarative spec held for a person", D 1.3, F 8; R16; golden rule 10):
`registry.draftFromSpec` starts the `adapter_author` run. The model drafts the spec's gaps as typed output (a `FunctionModel`
here, never a live provider), code checks every draft (`spec_check`, the importer's resources and auth) with at most three repair
rounds, and one proposal holds `registry.saveEntry {status: "tested"}` for a person. Nothing is saved before a person accepts it,
and releasing stays another person's action. No test calls the shared source-sim: the sample steps run on an in-process fake.
"""
# ruff: noqa: E501 - long lines in the call bodies

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.connectors.openapi_import import import_openapi
from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents import runtime
from di.services.agents.playbooks import adapter_author
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from tests.helpers import call

models.ALLOW_MODEL_REQUESTS = False
FIX = Path(__file__).parent / "fixtures" / "openapi"
BASE = "http://source-sim:8100/mock"
NAME = "p987 Mock Parts"
ENTRY = "p987-mock-parts"
SECRET = "SUPERSECRETVALUE-123456"


def doc(**info: Any) -> dict[str, Any]:
    d: dict[str, Any] = json.loads((FIX / "generic_mock.json").read_text(encoding="utf-8"))
    d["info"] = d["info"] | info
    return d


def importer_spec() -> dict[str, Any]:
    spec: dict[str, Any] = import_openapi(doc(), BASE).spec
    return spec


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step WHERE run_id IN (SELECT id FROM agent_run WHERE playbook = 'adapter_author')"))
        s.execute(
            text("DELETE FROM agent_run_message WHERE run_id IN (SELECT id FROM agent_run WHERE playbook = 'adapter_author')")
        )
        s.execute(text("DELETE FROM agent_proposal WHERE run_id IN (SELECT id FROM agent_run WHERE playbook = 'adapter_author')"))
        s.execute(text("DELETE FROM agent_run WHERE playbook = 'adapter_author'"))
        s.execute(text("DELETE FROM adapter_registry WHERE id LIKE 'p987-%'"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    _clean()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model unless a test installs one
    yield
    runtime.set_loop(None)
    _clean()


def scripted(outputs: list[dict[str, Any]], seen: list[str] | None = None) -> list[int]:
    """Install a model that answers with `outputs` in turn (the last one repeats); returns the list of its calls."""
    calls: list[int] = []

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(str(messages))
        out = outputs[min(len(calls), len(outputs) - 1)]
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn)))
    return calls


def draft(spec: dict[str, Any] | None = None, **over: Any) -> dict[str, Any]:
    return {"spec": spec if spec is not None else importer_spec(), "summary": "Reads parts and orders, offset paging.",
            "open_questions": ["Which warehouse owns the parts list?"]} | over  # fmt: skip


def bad_host() -> dict[str, Any]:
    spec = copy.deepcopy(importer_spec())
    spec["resources"][0]["docs_url"] = "https://other.example.com/docs"  # another host than the connection's
    return spec


def start(document: Any = None, user: str = "developer", **extra: Any) -> str:
    r = call(
        "registry.draftFromSpec",
        {"name": NAME, "system_type": "erp", "vendor_family": "Mock", "document": document or doc(), "base_url": BASE, **extra},
        user,
    )
    assert r["ok"], r
    run_id: str = r["output"]["run_id"]
    return run_id


def drive(run_id: str) -> dict[str, Any]:
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def proposals(run_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = text("SELECT id, agent, action, input, status FROM agent_proposal WHERE run_id = :r ORDER BY id")
        return [dict(r) for r in s.execute(q, {"r": run_id}).mappings()]


def entries() -> list[dict[str, Any]]:
    with SessionLocal() as s:
        return [
            dict(r) for r in s.execute(text("SELECT id, version, status FROM adapter_registry WHERE id LIKE 'p987-%'")).mappings()
        ]


def agent_ctx(s: Any, user: str = "developer", **kw: Any) -> CallContext:
    pctx = load_context(s)
    return CallContext(
        actor=Actor(account=policy.account(user, pctx), ctx=pctx), session=s, preparer=adapter_author.AGENT_ID, **kw
    )


def test_adapter_author_holds_one_proposal():
    calls = scripted([draft()])
    run = drive(start())
    assert run["status"] == "waiting" and run["state"]["waiting"] == "proposal" and run["state"]["by_model"] is True, run["state"]
    assert len(calls) == 1
    (p,) = proposals(run["id"])
    assert p["action"] == "registry.saveEntry" and p["status"] == "pending" and p["agent"] == adapter_author.AGENT_ID
    entry = p["input"]["entry"]
    assert entry["id"] == ENTRY and entry["kind"] == "from_spec" and entry["status"] == "tested"
    assert entry["spec"]["resources"] == importer_spec()["resources"]
    notes = entry["spec"]["import"]
    assert notes["summary"] == "Reads parts and orders, offset paging." and notes["open_questions"] == [
        "Which warehouse owns the parts list?"
    ]
    assert notes["checks"] == [] and notes["by_model"] is True
    assert entries() == []  # nothing is saved before a person accepts; no entry is released


def test_adapter_author_no_key_importer_only():
    run = drive(start())
    assert run["status"] == "waiting" and run["state"]["by_model"] is False
    (p,) = proposals(run["id"])
    assert p["input"]["entry"]["spec"]["resources"] == importer_spec()["resources"]
    assert p["input"]["entry"]["spec"]["paging"] == importer_spec()["paging"]
    assert entries() == []


def test_adapter_author_repairs_three_rounds():
    calls = scripted([draft(bad_host()), draft(bad_host()), draft()])
    run = drive(start())
    assert len(calls) == 3 and run["status"] == "waiting", run["state"]
    assert len(proposals(run["id"])) == 1 and proposals(run["id"])[0]["input"]["entry"]["spec"]["import"]["rounds"] == 3


def test_adapter_author_four_bad_answers_stop_with_the_errors():
    seen: list[str] = []
    calls = scripted([draft(bad_host())], seen)
    run = drive(start())
    assert len(calls) == 4 and run["status"] == "stopped", run["state"]
    assert any("other.example.com" in e["message"] for e in run["state"]["errors"])
    assert "other.example.com" in seen[1]  # the errors went back to the model
    assert proposals(run["id"]) == [] and entries() == []
    assert run["state"]["draft"]["spec"]["resources"][0]["docs_url"]  # handed over with its errors, never saved as valid


def test_adapter_author_model_cannot_invent_an_endpoint_or_a_secret():
    invented = copy.deepcopy(importer_spec())
    invented["resources"].append({"name": "secrets", "path": "/admin/secrets", "id_field": "id", "data_selector": "items"})
    keyed = copy.deepcopy(importer_spec())
    keyed["auth_params"] = {"api_key": SECRET}
    writes = copy.deepcopy(importer_spec())
    writes["resources"][0]["method"] = "POST"
    scripted([draft(invented), draft(keyed), draft(writes), draft()])
    run = drive(start())
    assert run["status"] == "waiting", run["state"]
    (p,) = proposals(run["id"])
    assert p["input"]["entry"]["spec"]["import"]["rounds"] == 4 and SECRET not in json.dumps(p["input"])


def test_adapter_author_never_sees_credentials():
    d = doc(description=f"Use the key {SECRET} in the X-Api-Key header.")
    d["components"] = d.get("components", {}) | {
        "securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "X-Api-Key", "x-example": SECRET}}
    }
    d["x-password"] = SECRET
    seen: list[str] = []
    scripted([draft()], seen)
    run = drive(start(d))
    assert seen and all(SECRET not in s for s in seen)  # the document's text never reaches the model, only the importer's reading
    assert not any(w in s.lower() for s in seen for w in (f"password: {SECRET.lower()}", "bearer "))
    assert SECRET not in json.dumps(proposals(run["id"])) and SECRET not in json.dumps(run["state"])


def test_adapter_author_cannot_release():
    for confirmed in (False, True):
        with SessionLocal() as s:
            r = invoke("registry.release", {"id": ENTRY, "version": 1}, agent_ctx(s, confirmed=confirmed))
            s.rollback()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", r


def test_adapter_author_agent_save_as_tested_is_held_not_saved():
    entry = {"id": ENTRY, "kind": "from_spec", "system_type": "erp", "vendor_family": "Mock", "status": "tested"}
    with SessionLocal() as s:
        r = invoke("registry.saveEntry", {"entry": entry}, agent_ctx(s))
        s.commit()
    assert r["ok"] and "held" in r["output"] and entries() == []


def test_adapter_author_accepting_saves_it_tested_and_another_person_releases():
    run_id = drive(start())["id"]
    (p,) = proposals(run_id)
    assert call("proposal.accept", {"id": p["id"]}, "developer")["error"]["code"] == "conflict"  # the starter cannot accept
    accepted = call("proposal.accept", {"id": p["id"]}, "admin")
    assert accepted["ok"], accepted
    assert [(e["id"], e["status"]) for e in entries()] == [(ENTRY, "tested")]
    assert drive(run_id)["status"] == "done"
    assert (
        call("registry.release", {"id": ENTRY, "version": 1}, "admin")["error"]["code"] == "conflict"
    )  # the maker cannot release
    assert call("registry.release", {"id": ENTRY, "version": 1}, "developer")["ok"]


def test_save_entry_status_is_draft_or_tested():
    base = {"id": ENTRY, "kind": "from_spec", "system_type": "erp", "vendor_family": "Mock"}
    assert (
        call("registry.saveEntry", {"entry": base | {"status": "released"}}, "developer")["error"]["code"] == "validation_error"
    )
    assert call("registry.saveEntry", {"entry": base | {"status": "tested"}}, "developer")["ok"]
    assert [e["status"] for e in entries()] == ["tested"]


def test_draft_from_spec_guards():
    body = {"name": NAME, "system_type": "erp", "vendor_family": "Mock", "document": doc()}
    assert call("registry.draftFromSpec", body, "planner-a")["error"]["code"] == "out_of_scope"
    assert call("registry.draftFromSpec", body | {"document": "not an api"}, "developer")["error"]["code"] == "validation_error"
    assert call("registry.draftFromSpec", body | {"base_url": "ftp://x"}, "developer")["error"]["code"] == "validation_error"
    assert call("registry.draftFromSpec", body | {"test_source_id": "nope"}, "developer")["error"]["code"] == "not_found"


def test_adapter_author_sample_steps_run_through_the_pipeline(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, dict[str, Any]]] = []

    def fake(action: str, i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        seen.append((action, i))
        if action == "connection.discover":
            return {"ok": True, "output": {"counts": {"parts": 120, "orders": 40}, "spread": {"parts": True, "orders": False}}}
        return {"ok": True, "output": {"rows": [{"field": "a"}] * 7, "gaps": ["asset.serial"], "waiting": 0, "by_model": False}}

    monkeypatch.setattr(adapter_author, "invoke", fake)
    with SessionLocal() as s:
        got = adapter_author.sample_steps(agent_ctx(s), "some-source")
    assert [a for a, _ in seen] == ["connection.discover", "mapping.suggest"]
    assert got["counts"] == {"parts": 120, "orders": 40} and got["mapping"] == {"fields": 7, "gaps": ["asset.serial"]}


def test_adapter_author_sample_steps_a_refusal_is_a_note(monkeypatch: pytest.MonkeyPatch):
    refusal = {"ok": False, "error": {"code": "conflict", "message": "Only a test connection is read."}}
    monkeypatch.setattr(adapter_author, "invoke", lambda *a, **k: refusal)
    with SessionLocal() as s:
        got = adapter_author.sample_steps(agent_ctx(s), "some-source")
    assert got["counts"] is None and "Only a test connection is read." in got["note"]
