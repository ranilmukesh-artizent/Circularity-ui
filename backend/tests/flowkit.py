"""Helpers for the decision flow tests (plan 8, phase 3): put the flows back to the seeded defaults, build a graph with
a business rule, and take a flow through its lifecycle as people would."""

import copy
import json
from typing import Any

from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import flows
from di.services.modeler.flow import Flow, default_flow, fe, fn
from di.services.modeler.templates import TEMPLATE_KEYS, load_template
from tests.helpers import call


def reset_flows() -> None:
    """Only the seeded published defaults on `workspace`, at version 1, with no history or shadow rows."""
    with engine.begin() as conn:
        if conn.execute(text("SELECT to_regclass('shadow_decision')")).scalar():
            conn.execute(text("DELETE FROM shadow_decision"))
        conn.execute(text("DELETE FROM decision_flow_version"))
        conn.execute(text("DELETE FROM decision_flow WHERE org_unit_id <> 'workspace'"))
        for key in TEMPLATE_KEYS:
            conn.execute(
                text(
                    "UPDATE decision_flow SET status = 'pub', ver = 1, dver = NULL, maker = NULL, checker = NULL, "
                    "draft = NULL, published = CAST(:g AS jsonb) WHERE template_key = :k AND org_unit_id = 'workspace'"
                ),
                {"k": key, "g": json.dumps(default_flow(load_template(key)))},
            )


def flow_id(template_key: str, org_unit_id: str) -> int:
    with SessionLocal() as s:
        f = flows.flow_for(s, template_key, org_unit_id)
    assert f is not None
    return f.id


def get(fid: int):
    with SessionLocal() as s:
        return flows.get_flow(s, fid), flows.versions(s, fid)


def with_rule(g: Flow, rid: str, action: str, path: str | None, scope: dict[str, Any]) -> Flow:
    """The graph with one more rule node between the guardrail gate and the decision."""
    g = copy.deepcopy(g)
    gate = next(n["id"] for n in g["nodes"] if n["t"] == "gate")
    dec = next(n["id"] for n in g["nodes"] if n["t"] == "decision")
    nid = "r-" + rid
    g["nodes"].append(fn(nid, "rule", 320, 200, "", "", rid=rid, action=action, path=path, scope=scope))
    g["edges"] += [fe(gate, nid), fe(nid, dec)]
    return g


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def publish(fid: int, graph: Flow, maker: str = "planner-a", checker: str = "approver") -> None:
    """Draft, submit, approve and publish `graph` on the flow."""
    ok(call("flow.saveDraft", {"flow_id": fid, "graph": graph}, maker))
    ok(call("flow.submit", {"flow_id": fid}, maker))
    ok(call("flow.approve", {"flow_id": fid}, checker))
    ok(call("flow.publish", {"flow_id": fid}, checker))


def fork_and_publish(org: str, graph_rules: list[tuple[str, str, str, dict[str, Any]]], maker: str = "planner-a") -> int:
    """A flow of the org's own (industrial) with these rules (rid, action, path, scope) published."""
    fid = ok(call("flow.fork", {"template_key": "industrial", "org_unit_id": org}, maker))["flow_id"]
    g = default_flow(load_template("industrial"))
    for rid, action, path, scope in graph_rules:
        g = with_rule(g, rid, action, path, scope)
    publish(fid, g, maker)
    return int(fid)
