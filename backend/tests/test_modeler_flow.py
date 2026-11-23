"""MVP-2.2: the flow graph (Domain spec D1) and each template's default flow."""

from di.core import golden
from di.services.modeler.flow import LOCKED, default_flow, node_label, reach
from di.services.modeler.templates import load_template

FLOWS = golden.load("po/flows")
WORLD_ROUTES = [r["id"] for r in golden.load("world")["routes"]]


def test_default_flows_equal_golden():
    for key, g in (("tool_fleet", "equip"), ("device", "device")):
        f = default_flow(load_template(key))
        assert f == {"nodes": FLOWS[g]["n"], "edges": FLOWS[g]["e"]}, key
    # a fresh copy each time: editing one never changes the next
    f = default_flow(load_template("tool_fleet"))
    f["nodes"].pop()
    assert default_flow(load_template("tool_fleet"))["nodes"] == FLOWS["equip"]["n"]


def test_industrial_default_has_no_rule_nodes():
    f = default_flow(load_template("industrial"))
    nodes = {n["id"]: n for n in f["nodes"]}
    assert not [n for n in f["nodes"] if n["t"] in ("rule", "agent")]
    assert [n["path"] for n in f["nodes"] if n["t"] == "path"] == WORLD_ROUTES
    assert [nodes[i]["label"] for i in ("in", "gate", "dec", "apr")] == [
        "Asset returned", "Guardrail gate", "Choose best route", "Owner approves"
    ]  # fmt: skip
    assert all(n["lock"] == (n["t"] in LOCKED) for n in f["nodes"])
    edges = {e["id"] for e in f["edges"]}
    assert {"in>gate", "gate>dec", "dec>apr", "exe>lrn"} <= edges
    assert all(f"apr>p-{k}" in edges and f"p-{k}>exe" in edges for k in WORLD_ROUTES)
    assert all(e["id"] == e["a"] + ">" + e["b"] and e["l"] == "" for e in f["edges"])
    assert reach(f, "in") == set(nodes)


def test_reach_skips_node():
    f = default_flow(load_template("tool_fleet"))
    assert "p-exit" in reach(f, "in")
    assert reach(f, "in", skip="gate") == {"in", "cond", "dem", "fit", "val"}
    assert reach(f, "apr", skip="p-exit") >= {"p-release", "exe", "lrn"} and "p-exit" not in reach(f, "apr", skip="p-exit")


def test_node_label():
    t = load_template("tool_fleet")
    nodes = {n["id"]: n for n in default_flow(t)["nodes"]}
    assert node_label(nodes["dec"]) == "Choose best path"
    assert node_label(nodes["r1"], t) == "BR-01 · never recycle"
    assert node_label({**nodes["r1"], "path": None}, t) == "BR-01 · set a path"
