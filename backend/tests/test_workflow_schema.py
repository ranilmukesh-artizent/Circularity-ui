"""P9-0.7: the workflow JSON Schema (di/workflow/schema.py) and the validated workflow.import.

- The schema is generated from the block catalogue: one branch per block, a property per setting.
- An export in the shape the web app's exportJson writes validates with no error.
- workflow.import collects every problem (schema, then the importer's own checks, then the graph checks that
  workflow.validate runs) and refuses once, naming each by path; a valid file creates the same draft as before.
"""

import copy

import pytest
from jsonschema import Draft202012Validator

from di.workflow import blocks
from di.workflow.schema import STEP_KINDS, workflow_schema
from tests import starting
from tests.helpers import call, client, h


def setup_module():
    starting.reset()


def teardown_module():
    starting.reset()


def _export() -> dict:
    """A fixture export in exportJson's shape: a connector step linked to a map step."""
    return {
        "id": "WF-1", "name": "ERP ingest", "version": "1.0", "type": "Ingest", "status": "draft", "owner": "Developer",
        "trigger": {"t": "schedule", "min": 60}, "source": "SAP S/4HANA", "source_id": "erp",
        "description": "Reads the ERP.",
        "steps": [
            {"id": "r", "kind": "conn", "ref": "erp", "label": "ERP", "x": 24, "y": 170, "cfg": {"mode": "full"}},
            {"id": "m", "kind": "map", "ref": "erp", "label": "ERP fields", "x": 230, "y": 170},
        ],
        "links": [{"from": "r", "to": "m", "fixed": False}],
        "exported_by": "Developer", "exported_at": "2026-11-20T09:00:00.000Z",
    }  # fmt: skip


def _import(data: dict) -> dict:
    return call("workflow.import", {"data": data}, "developer")


def _paths(r: dict) -> list[str]:
    return [p["path"] for p in r["error"]["problems"]]


def _count() -> int:
    return len(client.get("/api/screens/workflows", headers=h("developer")).json()["workflows"])


def test_schema_is_valid_draft_2020_12_and_deterministic():
    s = workflow_schema()
    Draft202012Validator.check_schema(s)
    assert s["$id"] == "https://circularity.example/schemas/workflow-export-1.json"
    assert s["title"] == "Workflow export v1"
    assert s["properties"]["steps"]["items"]["properties"]["kind"]["enum"] == list(STEP_KINDS)
    assert workflow_schema() == s


def test_schema_lists_every_block():
    s = workflow_schema()
    branches = s["properties"]["steps"]["items"]["allOf"]
    keyed = {b["x-block"] for b in branches}
    assert keyed == set(blocks.BLOCKS)
    cfg = {b["x-block"]: b["then"]["properties"]["cfg"] for b in branches}
    for ref, spec in blocks.BLOCKS.items():
        assert set(cfg[ref]["properties"]) == {f.key for f in spec.fields}, ref
    assert cfg["x_val"]["properties"]["on_failure"]["enum"] == ["hold", "reject"]
    assert cfg["act"]["properties"]["retries"]["maximum"] == 5


def test_export_shape_validates():
    assert list(Draft202012Validator(workflow_schema()).iter_errors(_export())) == []


def test_import_returns_every_problem():
    exp = _export()
    exp["steps"][0]["kind"] = "gadget"
    del exp["steps"][1]["id"]
    exp["links"] = [{"from": "r", "to": "ghost", "fixed": False}]
    n = _count()
    r = _import(exp)
    assert not r["ok"] and r["error"]["code"] == "validation_error", r
    assert _paths(r) == ["steps[0].kind", "steps[1].id", "links[0].to"], r
    assert r["error"]["message"].startswith("3 problems in this file. The first: ")
    assert _count() == n


def test_import_names_a_bad_setting_by_its_path():
    exp = _export()
    exp["steps"][0]["cfg"] = {"mode": "sideways", "lookback_days": 9999, "bogus": 1}
    r = _import(exp)
    assert not r["ok"]
    assert sorted(_paths(r)) == ["steps[0].cfg", "steps[0].cfg.lookback_days", "steps[0].cfg.mode"], r


def test_import_runs_graph_checks():
    exp = _export()
    exp["steps"][1]["ref"] = "crm"  # the ERP connector feeds the CRM's field mapping
    r = _import(exp)
    assert not r["ok"], r
    msgs = [p["message"] for p in r["error"]["problems"]]
    assert any("Field names would not line up." in m for m in msgs), msgs
    assert "steps[1]" in _paths(r)


def test_import_valid_file_unchanged():
    r = _import(_export())
    assert r["ok"], r
    try:
        d = client.get(f"/api/screens/workflows/{r['output']['id']}", headers=h("developer")).json()["workflow"]
        assert d["status"] == "draft" and d["ver"] == "0.1" and d["name"] == "ERP ingest" and d["src"] == "erp"
        assert d["graph"]["nodes"][0]["cfg"] == {"mode": "full"}
    finally:
        call("workflow.delete", {"id": r["output"]["id"]}, "developer")


def test_schema_endpoint_is_studio_only():
    ok = client.get("/api/screens/workflows/schema", headers=h("developer"))
    assert ok.status_code == 200 and ok.json() == workflow_schema()
    assert client.get("/api/screens/workflows/schema", headers=h("planner-a")).status_code == 403


@pytest.mark.parametrize("ref", sorted(blocks.BLOCKS))
def test_every_block_defaults_validate(ref):
    """A step that carries its block's default settings is valid (the export omits defaults, but may keep them)."""
    kind = ref if ref in STEP_KINDS else "xf"
    step = {"id": "s", "kind": kind, "ref": "erp" if kind in ("conn", "wconn", "map") else ref,
            "cfg": copy.deepcopy(blocks.default_cfg(ref))}  # fmt: skip
    exp = _export() | {"steps": [step], "links": []}
    assert list(Draft202012Validator(workflow_schema()).iter_errors(exp)) == []
