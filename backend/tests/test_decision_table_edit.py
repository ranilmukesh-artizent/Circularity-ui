"""P9-8.16 (E §8.2 C, §11.2; registry entry I-15): a decision table inside a flow is checked before submit, and the editor's
"Test this decision" returns the output and the matched row. Computed rules, not language: nothing here reads free text (R16)."""

import copy

from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.modeler import tables
from di.services.modeler.flow import default_flow, fe, fn
from di.services.modeler.templates import load_template
from di.services.modeler.validate import blocking, validate_flow

TF = load_template("tool_fleet")
MESSAGE = "Function nodes are off: tables hold conditions and outputs only."


def cover_body() -> dict:
    spec = tables.market_spec("tool_fleet")
    assert spec is not None and spec.table("cover_terms").body is not None
    return copy.deepcopy(spec.table("cover_terms").body)


def flow_with_table(body: dict):
    f = default_flow(TF)
    f["nodes"].append(fn("tbl", "table", 0, 0, "Cover terms", body=body))
    f["edges"].append(fe("in", "tbl"))
    return f


def test_table_function_node_fails_validation():
    body = cover_body()
    body["nodes"].append({"id": "fx", "type": "functionNode", "name": "Code", "content": "export const handler = async (i) => i"})
    fails = [c for c in blocking(validate_flow(TF, flow_with_table(body))) if c.node_id == "tbl"]
    assert [(c.level, c.msg) for c in fails] == [("fail", MESSAGE)]


def test_table_expression_node_fails_validation():
    body = cover_body()
    body["nodes"].append({"id": "ex", "type": "expressionNode", "name": "Maths", "content": {"expressions": []}})
    fails = [c for c in blocking(validate_flow(TF, flow_with_table(body))) if c.node_id == "tbl"]
    assert [c.msg for c in fails] == [MESSAGE]


def test_valid_table_adds_no_failure():
    assert [c for c in blocking(validate_flow(TF, flow_with_table(cover_body()))) if c.node_id == "tbl"] == []


def test_table_test_returns_matched_row():
    table = tables.JdmTable.model_validate(cover_body())
    out = tables.ZenEvaluator().evaluate(table, {"market": "DE", "family": "CRH", "cover_type": "fleet", "age_months": 14})
    assert out.outputs["swap_allowed"] is True
    assert out.matched == ["r1"]


def test_no_new_approve_action_for_tables():
    # saves, submits and tests are marketTable.* (P9-4.2); approving stays a person's
    assert {"marketTable.approve", "marketTable.reject"} <= set(FORBIDDEN_ACTIONS)
