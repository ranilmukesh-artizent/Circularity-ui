"""MVP-2.1: template packs as data. `tool_fleet` and `device` are built from the PO prototype goldens
(fixtures/golden/po/templates.json); `industrial` from its packaged JSON over the demo's 7 routes."""

import pytest

from di.core import golden
from di.services.engine import gates
from di.services.modeler.templates import TEMPLATE_KEYS, Forbid, load_template

PO = {t["key"]: t for t in golden.load("po/templates")["templates"]}
WORLD = golden.load("world")


def test_template_keys():
    assert TEMPLATE_KEYS == ("industrial", "tool_fleet", "device")


def test_tool_fleet_pack_matches_golden():
    t, g = load_template("tool_fleet"), PO["equip"]
    assert (t.key, t.name, t.pre) == ("tool_fleet", g["name"], g["pre"])
    assert [(p.id, p.name, p.app, p.owner, p.lead_days) for p in t.paths] == [
        (p["key"], p["name"], p["app"], p["owner"], p["lead"]) for p in g["paths"]
    ]
    # GR-14, GR-15 (P9-3.15) and GR-C1 (credits over $300, P9-5.4) are plan 9 approval guardrails; the demo has none
    guards = [(x.id, x.text, x.owner) for x in t.guardrails if x.id not in ("GR-14", "GR-15", "GR-C1")]
    assert guards == [(x["id"], x["text"], x["owner"]) for x in g["guards"]]
    dims = [(d.key, d.label, list(d.values) or None) for d in t.dims if d.key != "keyAccount"]  # keyAccount: P9-3.16, plan 9
    assert dims == [(d["key"], d["label"], d["values"]) for d in g["dims"]]
    assert [d.kind for d in t.dims] == ["set", "set", "set", "set", "max", "min", "set"]
    gr01 = t.guardrails[0]
    assert gr01.forbids == (Forbid("release", ("require", "prefer"), {"grade": ("C", "D")}),)
    assert t.actors == tuple((a["id"], a["name"], a["role"]) for a in golden.load("po/templates")["ACTORS"])


def test_device_pack_matches_golden():
    t, g = load_template("device"), PO["device"]
    assert (t.key, t.name, t.pre) == ("device", "Device recommerce", g["pre"])
    # the wholesale lot (P9-6.10, a Recover channel) is a plan 9 addition, not in the demo
    assert [(p.id, p.name) for p in t.paths if p.id != "wholesale"] == [(p["key"], p["name"]) for p in g["paths"]]
    # GR-D7 (blacklist, P9-6.6), GR-D8 (price confidence, P9-6.10), GR-D10 and GR-D12 (wholesale lots, P9-6.11), GR-D11
    # (payout gap, P9-6.8) and GR-D13 (quote match, P9-6.5) are plan 9 additions for received devices; the demo has none of them
    guards = [
        (x.id, x.text, x.owner) for x in t.guardrails if x.id not in ("GR-D7", "GR-D8", "GR-D10", "GR-D11", "GR-D12", "GR-D13")
    ]
    assert guards == [(x["id"], x["text"], x["owner"]) for x in g["guards"]]
    # the listing dims (listChannel, listDaysMin, offersMax: ageing rules, P9-6.13) are a plan 9 addition, not in the demo
    ageing = ("listChannel", "listDaysMin", "offersMax")
    dims = [d for d in t.dims if d.key not in ageing]
    assert [(d.key, d.label, list(d.values) or None) for d in dims] == [(d["key"], d["label"], d["values"]) for d in g["dims"]]
    assert [d.kind for d in dims] == ["set", "set", "set", "min", "min"]
    gr_d3 = next(x for x in t.guardrails if x.id == "GR-D3")
    assert {f.path for f in gr_d3.forbids} == {"buynow", "market"}


def test_industrial_paths_are_world_routes():
    t = load_template("industrial")
    assert [(p.id, p.name) for p in t.paths] == [(r["id"], r["name"]) for r in WORLD["routes"]]
    assert [p.id for p in t.paths] == ["redeploy", "resale", "intparts", "relase", "material", "extparts", "exit"]
    texts = {x.id: x.text for x in t.guardrails}
    assert texts == {
        "GR-I1": gates.DATA_ERASURE,
        "GR-I2": gates.SAFETY_RATED,
        "GR-I3": gates.CONSENT,
        "GR-I4": gates.HAZARDOUS,
        "GR-I5": "Every decision is approved by a named owner before execution",
    }
    assert all(x.forbids == () for x in t.guardrails)
    gr05 = next(x for x in load_template("tool_fleet").guardrails if x.id == "GR-05")
    assert next(x for x in t.guardrails if x.id == "GR-I5").protects == gr05.protects
    assert [x.owner for x in t.guardrails][-1] == "Governance board"
    dims = {d.key: d for d in t.dims}
    assert list(dims) == ["cls", "grade", "site", "owner", "alarm"]  # alarm: telemetry scope (MVP-7.1)
    assert dims["cls"].values == tuple(WORLD["classes"])
    assert dims["grade"].values == ("A", "B", "C", "D")
    assert dims["site"].values == tuple(s["id"] for s in WORLD["sites"])
    assert dims["owner"].values == tuple(WORLD["tenants"])


def test_unknown_template_raises_keyerror():
    with pytest.raises(KeyError):
        load_template("equip")
