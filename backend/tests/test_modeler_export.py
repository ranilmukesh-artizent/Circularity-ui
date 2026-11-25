"""P9-8.21 (enabler: E 8.2 "DMN export" and "BPMN 2.0 export of the case process"): a flow leaves the Modeler as DMN
and BPMN XML. The tests read the element structure and namespaces with ElementTree; they never compare whole strings."""

import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import market_tables
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.modeler import export_bpmn
from di.services.modeler.compile import compile_flow
from di.services.modeler.export_dmn import Table, decision_id, to_dmn
from di.services.modeler.flow import default_flow
from di.services.modeler.pack import load_pack
from di.services.modeler.stages import STAGE_KEYS
from di.services.modeler.templates import load_template
from tests import flowkit
from tests.flowkit import ok, with_rule
from tests.helpers import call


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)  # noqa: S314 - the export's own output, read back


DMN = "https://www.omg.org/spec/DMN/20191111/MODEL/"
BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
D, B = "{" + DMN + "}", "{" + BPMN + "}"
DECISION_REF = "{http://camunda.org/schema/1.0/bpmn}decisionRef"
PACK = "tool_fleet"


def _flow_with_rules():
    t = load_template(PACK)
    g = default_flow(t)  # the pack's own sample rules go: the two below are the only business rules
    gone = {n["id"] for n in g["nodes"] if n["t"] == "rule"}
    g["nodes"] = [n for n in g["nodes"] if n["id"] not in gone]
    g["edges"] = [e for e in g["edges"] if e["a"] not in gone and e["b"] not in gone]
    g = with_rule(g, "BR-01", "exclude", t.path_ids()[0], {"grade": ["D"]})
    return t, with_rule(g, "BR-02", "prefer", t.path_ids()[1], {"cls": ["CMH"]})


def _dmn(tables=()):
    t, g = _flow_with_rules()
    return _parse(to_dmn(load_pack(PACK), g, compile_flow(t, g), tables))


def _decisions(root):
    return {d.get("id"): d for d in root.findall(D + "decision")}


def _rules_table(root):
    return _decisions(root)[decision_id(load_pack(PACK))].find(D + "decisionTable")


def _text(el, tag):
    return [x.findtext(D + "text") for x in el.findall(D + tag)]


def _notes(tbl):
    return [r.find(D + "annotationEntry").findtext(D + "text") for r in tbl.findall(D + "rule")]


def test_dmn_rules_in_order():
    t, g = _flow_with_rules()
    root = _dmn()
    assert root.tag == D + "definitions"
    tbl = _rules_table(root)
    assert tbl.get("hitPolicy") == "FIRST"
    rules = tbl.findall(D + "rule")
    notes = _notes(tbl)
    assert [c.id for c in compile_flow(t, g)][:2] == ["BR-01", "BR-02"]
    assert "BR-01" in notes[0] and "BR-02" in notes[1]
    assert [_text(r, "outputEntry")[1] for r in rules[:2]] == ['"exclude"', '"prefer"']
    ins = [i.find(D + "inputExpression").findtext(D + "text") for i in tbl.findall(D + "input")]
    assert ins == [d.key for d in t.dims]  # the inputs are the pack's dimensions
    assert [o.get("name") for o in tbl.findall(D + "output")] == ["path", "action"]
    assert _text(rules[0], "inputEntry")[ins.index("grade")] == '"D"', (notes[0], [_text(r, "inputEntry") for r in rules[:3]])
    assert _text(rules[0], "inputEntry")[ins.index("cls")] == "-"


def test_dmn_guardrails_locked_annotation():
    pack = load_pack(PACK)
    guards = [d for i, d in _decisions(_dmn()).items() if i != decision_id(pack) and "guardrail" in i]
    assert len(guards) == 1
    tbl = guards[0].find(D + "decisionTable")
    rows = tbl.findall(D + "rule")
    assert len(rows) == len(pack.guardrails)
    for g, note in zip(pack.guardrails, _notes(tbl), strict=True):
        assert g.owner in note
        assert (f"locked, owner {g.owner}" in note) == g.locked


def test_dmn_waiver_default_row():
    tbl = _rules_table(_dmn())
    last = tbl.findall(D + "rule")[-1]
    assert set(_text(last, "inputEntry")) == {"-"}
    assert "waive" in _notes(tbl)[-1].lower()


def _jdm(rules, hit="first", cols=("age",)):
    return {
        "nodes": [
            {"id": "i", "type": "inputNode", "name": "Request"},
            {"id": "t", "type": "decisionTableNode", "name": "Table", "content": {
                "hitPolicy": hit,
                "inputs": [{"id": "in_" + c, "name": c, "field": c} for c in cols],
                "outputs": [{"id": "out_x", "name": "x", "field": "x"}],
                "rules": rules}},
            {"id": "o", "type": "outputNode", "name": "Response"},
        ],
        "edges": [{"id": "e1", "sourceId": "i", "targetId": "t"}, {"id": "e2", "sourceId": "t", "targetId": "o"}],
    }  # fmt: skip


def test_dmn_table_decisions_unary_exportable_and_the_rest_listed():
    good = Table(
        "cover",
        "cover terms",
        "DE",
        1,
        _jdm([{"_id": "r1", "in_age": "<= 24", "out_x": "true"}, {"_id": "r2", "in_age": "", "out_x": "false"}]),
    )
    bad = Table("credit", "credit rules", "DE", 1, _jdm([{"_id": "r1", "in_age": "age * 2 > 4", "out_x": "1"}]))
    root = _dmn([good, bad])
    ds = _decisions(root)
    cover = [d for i, d in ds.items() if "cover" in i]
    assert len(cover) == 1 and not [i for i in ds if "credit" in i]
    tbl = cover[0].find(D + "decisionTable")
    assert [_text(r, "inputEntry")[0] for r in tbl.findall(D + "rule")] == ["<= 24", "-"]
    desc = ds[decision_id(load_pack(PACK))].findtext(D + "description")
    assert "not exportable" in desc.lower() and "credit rules" in desc


def test_dmn_ids_are_unique_ncnames():
    ids = [e.get("id") for e in _dmn().iter() if e.get("id")]
    assert len(ids) == len(set(ids))
    assert all(i[0].isalpha() or i[0] == "_" for i in ids)


def _bpmn():
    pack = load_pack(PACK)
    proc = export_bpmn.process_of(pack, default_flow(load_template(PACK)))
    return pack, proc, _parse(export_bpmn.to_bpmn(pack, proc, decision_id(pack)))


def test_bpmn_has_stage_tasks_and_timers():
    pack, proc, root = _bpmn()
    assert root.tag == B + "definitions"
    p = root.find(B + "process")
    services = p.findall(B + "serviceTask")
    assert len(services) == 7 == len(STAGE_KEYS)
    rule_tasks = p.findall(B + "businessRuleTask")
    assert len(rule_tasks) == 1
    assert rule_tasks[0].get(DECISION_REF) == decision_id(pack)
    sla = pack.runtime.sla_hours["exception"]
    assert len(proc.stage_sla_hours) == 7
    timers = [b for b in p.findall(B + "boundaryEvent") if b.find(B + "timerEventDefinition") is not None]
    assert {b.get("attachedToRef") for b in timers} == {s.get("id") for s in services}
    assert timers[0].find(B + "timerEventDefinition").findtext(B + "timeDuration") == f"PT{int(sla)}H"
    assert p.findall(B + "startEvent") and len(p.findall(B + "endEvent")) == 1
    assert p.findall(B + "exclusiveGateway")
    ids = {e.get("id") for e in p.iter() if e.get("id")}
    for f in p.findall(B + "sequenceFlow"):
        assert f.get("sourceRef") in ids and f.get("targetRef") in ids


def test_bpmn_user_tasks_for_approvals_and_route_flows():
    pack, _, root = _bpmn()
    p = root.find(B + "process")
    approvals = [g for g in pack.guardrails if g.type == "Approval"]
    assert len(p.findall(B + "userTask")) == len(approvals) >= 1
    split = p.findall(B + "exclusiveGateway")[0]
    out = [f for f in p.findall(B + "sequenceFlow") if f.get("sourceRef") == split.get("id")]
    assert {f.get("name") for f in out} == {r.name for r in pack.routes}


# ---------------------------------------------------------------- the actions
@pytest.fixture
def fresh():
    flowkit.reset_flows()
    with SessionLocal() as s:
        market_tables.ensure_seeded(s, PACK)
        s.commit()
    yield
    flowkit.reset_flows()


def _journal() -> int:
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM action_journal")).scalar_one()


def test_exports_are_reads(fresh):
    fid = flowkit.flow_id(PACK, "workspace")
    before = _journal()
    dmn = ok(call("flow.exportDmn", {"flow_id": fid}, "admin"))
    bpmn = ok(call("flow.exportBpmn", {"flow_id": fid}, "admin"))
    assert _journal() == before
    assert dmn["filename"] == "tool_fleet-workspace-v1.dmn" and bpmn["filename"] == "tool_fleet-workspace-v1.bpmn"
    assert dmn["content_type"] == bpmn["content_type"] == "application/xml"
    names = [e.get("id") for e in _parse(dmn["xml"]).findall(D + "decision")]
    assert any("cover_terms" in n for n in names)  # the seeded decision tables are their own decisions
    ref = _parse(bpmn["xml"]).find(B + "process").find(B + "businessRuleTask").get(DECISION_REF)
    assert ref in names  # the BPMN points at a decision the DMN file holds
    f, _ = flowkit.get(fid)
    assert (f.status, f.ver) == ("pub", 1)


def test_exports_open_to_the_modeler_page_only(fresh):
    fid = flowkit.flow_id(PACK, "workspace")
    assert ok(call("flow.exportDmn", {"flow_id": fid}, "exec"))["xml"]
    r = call("flow.exportBpmn", {"flow_id": fid}, "warehouse1")
    assert not r["ok"] and r["error"]["code"] == "out_of_scope"
    assert call("flow.exportDmn", {"flow_id": 999999}, "admin")["error"]["code"] == "not_found"


def test_exports_are_not_forbidden_to_agents():
    assert not {"flow.exportDmn", "flow.exportBpmn"} & set(FORBIDDEN_ACTIONS)
