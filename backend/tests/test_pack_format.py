"""P9-1.1 (I-1): pack format v1. The three packs are data, validate against the model and the committed schema, and
build the templates and valuer constants the PO goldens pin."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from di.core import golden
from di.services.modeler import carbon
from di.services.modeler.compile import compile_flow, rule_text
from di.services.modeler.flow import default_flow
from di.services.modeler.pack import (
    FIELD_PART,
    PACK_PARTS,
    Pack,
    PackError,
    load_pack,
    pack_keys,
    parse_pack,
)
from di.services.modeler.stages import STAGE_KEYS
from di.services.modeler.templates import TEMPLATE_KEYS, load_template, template_of_pack
from di.services.modeler.valuers import device, tool_fleet

PACKS = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs"
PO = {t["key"]: t for t in golden.load("po/templates")["templates"]}


def _doc(key: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((PACKS / f"{key}.json").read_text(encoding="utf-8"))
    return doc


def test_x_01_missing_part_named():
    doc = _doc("tool_fleet")
    del doc["stages"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.key, e.value.version, e.value.part, e.value.part_name) == ("tool_fleet", "3.2.0", 4, "stages")
    assert str(e.value) == "Pack tool_fleet v3.2.0: part 4 (stages): Field required"


def test_x_01_unknown_field_refused():
    with pytest.raises(PackError):
        parse_pack({**_doc("tool_fleet"), "screens": []})


def test_x_01_bad_value_names_its_part():
    doc = _doc("device")
    doc["stages"][0]["confidence"] = 0.95
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert (e.value.part, e.value.part_name) == (4, "stages")
    doc = _doc("device")
    doc["routes"][0]["classes"] = ["teleport"]
    with pytest.raises(PackError) as e:
        parse_pack(doc)
    assert e.value.part == 5


def test_three_packs_validate():
    assert TEMPLATE_KEYS == ("industrial", "tool_fleet", "device")
    assert set(pack_keys()) - {"used_cars", "medical_rental", "telecom_network"} == set(
        TEMPLATE_KEYS
    )  # P9-9.1, P9-10.1, P9-11.1: pack files, not templates yet
    got = {k: load_pack(k) for k in TEMPLATE_KEYS}
    assert {k: p.version for k, p in got.items()} == {"industrial": "1.0.0", "tool_fleet": "3.2.0", "device": "2.7.0"}
    assert all(isinstance(p, Pack) and p.key == k for k, p in got.items())
    assert load_pack("tool_fleet") is load_pack("tool_fleet")
    with pytest.raises(KeyError):
        load_pack("equip")


def test_every_field_belongs_to_one_of_the_13_parts():
    assert PACK_PARTS == {
        1: "identity", 2: "prompts", 3: "classes", 4: "stages", 5: "routes", 6: "guardrails",
        7: "customer_layer", 8: "data", 9: "valuer", 10: "replay", 11: "runtime", 12: "kpis", 13: "stories",
    }  # fmt: skip
    assert set(FIELD_PART) == set(Pack.model_fields)
    assert set(FIELD_PART.values()) == set(PACK_PARTS)


def test_schema_file_is_generated():
    want = {"$schema": "https://json-schema.org/draft/2020-12/schema", **Pack.model_json_schema()}
    assert json.loads((PACKS / "pack.schema.json").read_text(encoding="utf-8")) == want


@pytest.mark.parametrize("key", TEMPLATE_KEYS)
def test_pack_files_satisfy_the_schema(key):
    schema = json.loads((PACKS / "pack.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(_doc(key))
    assert not jsonschema.Draft202012Validator(schema).is_valid({**_doc(key), "screens": []})
    assert not jsonschema.Draft202012Validator(schema).is_valid({**_doc(key), "prompts": ["a"]})


def test_tool_fleet_template_equals_po_golden():
    t, g = load_template("tool_fleet"), PO["equip"]
    assert t == template_of_pack(load_pack("tool_fleet"))
    assert [(p.id, p.name, p.app, p.owner, p.lead_days) for p in t.paths] == [
        (p["key"], p["name"], p["app"], p["owner"], p["lead"]) for p in g["paths"]
    ]
    assert [(x.id, x.text, x.owner) for x in t.guardrails] == [(x["id"], x["text"], x["owner"]) for x in g["guards"]]
    assert [(d.key, d.label, list(d.values) or None) for d in t.dims] == [(d["key"], d["label"], d["values"]) for d in g["dims"]]
    for c in golden.load("po/compile_cases")["cases"]:
        flow = {"nodes": c["flow"]["n"], "edges": c["flow"]["e"]}
        rules = compile_flow(t, flow)
        assert [asdict(r) for r in rules] == c["rules"], c["name"]
        if c["name"] != "harvest_removed":  # that rule's text is the flow's own note
            assert [rule_text(t, asdict(r)) for r in rules] == [r["text"] for r in c["rules"]], c["name"]


def test_device_template_equals_po_golden():
    t, g = load_template("device"), PO["device"]
    assert t == template_of_pack(load_pack("device"))
    assert [(p.id, p.name) for p in t.paths] == [(p["key"], p["name"]) for p in g["paths"]]
    # GR-D7 (blacklist, P9-6.6), GR-D11 (payout limit, P9-6.8), GR-D13 (quote match, P9-6.5): plan 9 additions, not in the demo
    guards = [(x.id, x.text, x.owner) for x in t.guardrails if x.id not in ("GR-D7", "GR-D11", "GR-D13")]
    assert guards == [(x["id"], x["text"], x["owner"]) for x in g["guards"]]
    assert [(d.key, d.label, list(d.values) or None) for d in t.dims] == [(d["key"], d["label"], d["values"]) for d in g["dims"]]
    assert [asdict(r) for r in compile_flow(t, default_flow(t))] == [
        {"id": "DR-01", "scope": {"dohMin": 45}, "action": "exclude", "path": "buynow", "text": "45+ days on hand: never Buy Now"}
    ]


def test_valuer_params_from_pack():
    tf, dv = load_pack("tool_fleet").valuer.params, load_pack("device").valuer.params
    assert {k: {kk: vv for kk, vv in v.items() if kk != "freight"} for k, v in tool_fleet.CLS.items()} == tf["classes"]
    assert (tf["paths"], tf["basep"], tf["fin"]) == (tool_fleet.PATHS, tool_fleet.BASEP, tool_fleet.FIN)
    assert (tf["funcs"], tf["sites"], tf["sources"]) == (tool_fleet.FUNCS, tool_fleet.SITES, tool_fleet.SOURCES)
    assert (tf["cust"], tf["dealers"], frozenset(tf["poolk"])) == (tool_fleet.CUST, tool_fleet.DEALERS, tool_fleet.POOLK)
    assert dv["dg"] == device.DG
    assert (dv["dch"], dv["dcn"], dv["dcfg"], dv["dst"]) == (device.DCH, device.DCN, device.DCFG, device.DST)
    assert tool_fleet.CLS is not tf["classes"], "the valuer copies the pack's params: the cached pack stays as loaded"
    assert tool_fleet.CLS["CMH"]["freight"] == 34


def test_stages_are_the_seven():
    for k in TEMPLATE_KEYS:
        p = load_pack(k)
        assert tuple(s.key for s in p.stages) == STAGE_KEYS
        assert all(0.65 <= s.confidence <= 0.85 for s in p.stages)
        assert [(s.key, s.autonomy) for s in p.stages] == [
            ("receive", "alone"), ("match", "alone"), ("condition", "limits"), ("value", "alone"),
            ("decide", "limits"), ("execute", "limits"), ("close", "alone"),
        ]  # fmt: skip
        assert len(p.prompts) == 3


def test_route_classes_and_guardrail_types():
    classes = {k: {r.id: list(r.classes) for r in load_pack(k).routes} for k in TEMPLATE_KEYS}
    assert classes["tool_fleet"]["exit"] == ["recycle", "exit"]
    assert classes["device"] == {c: ["sale"] for c in ("buynow", "offers", "auction", "market")}
    assert classes["industrial"]["extparts"] == ["parts", "sale"]
    d2 = next(g for g in load_pack("device").guardrails if g.id == "GR-D2")
    assert d2.param is not None and (d2.param.field, d2.param.value, d2.param.stricter) == ("floor", 0.55, "higher")
    assert load_pack("device").customer_layer.editable == {"GR-D2": ["floor"]}
    assert [(g.id, g.type, g.stage, g.locked) for g in load_pack("tool_fleet").guardrails][:3] == [
        ("GR-01", "Compliance", "decide", True), ("GR-02", "Compliance", "decide", True),
        ("GR-03", "Threshold", "condition", False),
    ]  # fmt: skip


def test_runtime_and_kpis_of_the_two_packs():
    tf, dv = load_pack("tool_fleet"), load_pack("device")
    # P9-1.10 added not_in_system_of_record and expected_return_missing (both Planner) in front of the five of P9-1.1
    # no_active_contract belongs to the Fleet desk, which the pack's roles table routes to a Planner (P9-3.6);
    # P9-5.1 added refresh_late (Fleet desk); P9-3.7 recall_quarantine (Quality), the technician check (Engineer) and P9-3.8
    # stale_telematics (Quality, last)
    assert [e.id for e in tf.runtime.exception_types] == [
        "not_in_system_of_record", "expected_return_missing", "no_active_contract", "recall_quarantine", "technician_check",
        "grade_wear_disagree", "repair_over_limit", "writeoff_under_24m", "inspection_backlog", "refresh_late",
        "stale_telematics",
    ]  # fmt: skip
    assert [e.owner_role for e in tf.runtime.exception_types] == [
        "Planner", "Planner", "Fleet desk", "Quality", "Engineer", "Engineer", "Approver", "Planner", "Planner", "Fleet desk",
        "Quality",
    ]  # fmt: skip
    assert len(dv.runtime.exception_types) == 10 and len(dv.kpis) == 6  # P9-6.5 quote_mismatch, P9-6.6 blacklist_hit
    assert [k.label for k in tf.kpis][:2] == ["Value recovered per tool", "Days to next use"]
    # P9-1.13 gave three of the six a measure; the other three show "No data yet" until their phase
    assert len(tf.kpis) == 6 and [k.id for k in tf.kpis if k.measure] == ["value_per_tool", "redeploy_rate", "held_by_guardrails"]


def test_carbon_reads_the_pack_named_set():
    assert load_pack("tool_fleet").valuer.carbon.set == "cfs-2026.2"
    pack = load_pack("tool_fleet")
    assert carbon.co2_avoided(pack, "CMH", "release", 1, confirmed=True) is not None
    carbon_ref = pack.valuer.carbon.model_copy(update={"set": "other"})
    other = pack.model_copy(update={"valuer": pack.valuer.model_copy(update={"carbon": carbon_ref})})
    assert carbon.co2_avoided(other, "CMH", "release", 1, confirmed=True) is None
