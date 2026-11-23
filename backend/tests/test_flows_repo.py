"""MVP-3.1: the decision flow tables (migration 0021) and the read repository di.repositories.flows."""

import json

import pytest
from sqlalchemy import inspect, text

import di.models
from di.core.db import SessionLocal, engine
from di.repositories import flows
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import TEMPLATE_KEYS, load_template

SITE = "MVP31 site"


@pytest.fixture
def company_flow():
    """A flow of its own for Customer A (industrial), and a site below Customer A; both removed afterwards."""
    g = json.dumps(default_flow(load_template("industrial")))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO org_unit (id, parent_id, kind, name) VALUES (:i, 'Customer A', 'site', :i)"), {"i": SITE})
        fid = conn.execute(
            text(
                "INSERT INTO decision_flow (template_key, org_unit_id, name, status, ver, published) "
                "VALUES ('industrial', 'Customer A', 'Industrial returns', 'pub', 1, CAST(:g AS jsonb)) RETURNING id"
            ),
            {"g": g},
        ).scalar_one()
    yield fid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM decision_flow WHERE id = :i"), {"i": fid})
        conn.execute(text("DELETE FROM org_unit WHERE id = :i"), {"i": SITE})


def test_seeded_flows():
    with SessionLocal() as s:
        rows = [f for f in flows.flows(s, {"workspace"}) if f.org_unit_id == "workspace"]
    assert sorted(f.template_key for f in rows) == sorted(TEMPLATE_KEYS)
    for f in rows:
        t = load_template(f.template_key)
        assert (f.name, f.status, f.ver, f.dver, f.draft) == (t.name, "pub", 1, None, None)
        assert f.published == default_flow(t)


def test_flow_for_uses_nearest_ancestor(company_flow):
    with SessionLocal() as s:
        own = flows.flow_for(s, "industrial", "Customer A")
        below = flows.flow_for(s, "industrial", SITE)
        other = flows.flow_for(s, "industrial", "Customer B")
        none = flows.flow_for(s, "industrial", "no such unit")
        by_id = flows.get_flow(s, company_flow)
        assert flows.versions(s, company_flow) == []
    assert own is not None and own.id == company_flow
    assert below is not None and below.id == company_flow
    assert other is not None and other.org_unit_id == "workspace"
    assert none is None
    assert by_id == own


def test_flows_lists_only_the_given_orgs(company_flow):
    with SessionLocal() as s:
        a = flows.flows(s, {"Customer A"})
        b = flows.flows(s, {"Customer B"})
    assert [f.id for f in a] == [company_flow]
    assert b == []


def test_models_match_migrations():
    live = set(inspect(engine).get_table_names())
    for t in ("decision_flow", "decision_flow_version"):
        assert t in di.models.metadata.tables and t in live
