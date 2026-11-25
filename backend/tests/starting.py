"""The demo's starting state, for tests that compare against the golden files.

`reset()` puts di back where a fresh copy of the demo starts: every case reopened from the engine's evaluation, the
workspace collections (events, notes, requests, accounts ...) back to their starting values, delegations on, no tenant
grants, and no journal, events, stage moves made by actions, instructions or queued jobs. Sources created in the
Connection Fabric are removed and the demo's sources get back their starting status and description
(di.connectors.sync.reset_sources); their connector data (canonical store, sync cursors) is left alone.

Plan 8 state goes back too: the seeded default decision flows only (no versions, drafts or shadow rows), the seeded org
units only, no agent runs, proposals or model versions, and only the demo's agents.

`strict()` (from tests/helpers.py) makes booleans compare strictly: Python's `==` treats True == 1, which hides real
differences.
"""

import json

from sqlalchemy import Connection, text

from di.connectors.sync import reset_sources
from di.core import state
from di.core.db import engine
from di.services.cases import store
from di.services.modeler.flow import default_flow
from di.services.modeler.templates import TEMPLATE_KEYS, load_template
from tests.helpers import strict  # noqa: F401  (tests call starting.strict)


def reset() -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM instruction"))
        conn.execute(text("DELETE FROM action_journal"))
        conn.execute(text("DELETE FROM job WHERE kind <> 'sync.source'"))
        # plan 8 phase 11: the demo's nine agents only, all started (the kill switch is also kept in "agents_off"),
        # with no runs and no proposals held for a person
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        # back to the seeded registry rows exactly (autonomy, tools, org scope), as migration 0023 inserts them:
        # a person may have changed an agent's autonomy on the Agents page
        conn.execute(text("DELETE FROM agent_identity"))
        for aid, name, tools, autonomy in SEED_AGENTS:
            conn.execute(
                text("INSERT INTO agent_identity (id, name, kind, tools, autonomy) " "VALUES (:i, :n, 'internal', :t, :a)"),
                {"i": aid, "n": name, "t": list(tools), "a": autonomy},
            )
        conn.execute(text("DELETE FROM model_version"))  # plan 8 MVP-12.2: no candidate or promoted model
        # plan 9: no open work items (P9-1.7), customer overlays (P9-1.3) or imported pack versions (P9-1.6): the packs
        # in force are the files, as shipped
        conn.execute(text("DELETE FROM work_item"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM pack_version"))
        _reset_flows(conn)
        reset_sources(conn)
        # plan 8 MVP-1.1: only the seeded org units (workspace and the three customers), once no source points at others
        conn.execute(text("DELETE FROM org_unit WHERE id <> ALL(:seed) AND parent_id IS NOT NULL"), {"seed": list(SEED_ORGS)})
    store.reset()
    state.reset()


SEED_ORGS = ("workspace", "Customer A", "Customer B", "Customer C")

# The agents migration 0023 seeds, less the tools migration 0029 removes (no handler): (id, name, tools, autonomy).
# Keep in step with those migrations
# (tests/test_agent_registry.py::test_seeded_agents checks the live rows).
SEED_AGENTS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("assembler", "Evidence Assembler", ("get_case_evidence", "list_eligible_routes", "get_model_validation"), "act"),
    (
        "finder",
        "Opportunity Finder",
        ("find_demand", "predict_outcomes", "optimize_pool", "list_eligible_routes", "get_case_evidence"),
        "act",
    ),
    ("gap", "Gap Requester", ("get_case_evidence", "request_missing_evidence"), "act"),
    ("coordinator", "Handoff Coordinator", ("get_case_evidence", "request_approval", "send_instruction"), "act"),
    ("reconciler", "Reconciler", ("get_case_evidence", "reconcile_outcome", "get_model_validation"), "act"),
    ("briefer", "Briefing Agent", ("inbox.get", "cases.list"), "act"),
    ("analyst", "Analytics Explainer", ("kpi.explain", "analytics.models"), "act"),
    (
        "integrator",
        "Integration Assistant",
        ("workflow.draft", "workflow.validate"),
        "act",
    ),
    ("auditor", "Audit Assistant", ("case.trace",), "act"),
    ("ask", "Ask Circularity", (), "read"),
)


def _reset_flows(conn: Connection) -> None:
    """Plan 8 MVP-3.1: only the seeded published default flow of each template on `workspace`, at version 1, with no
    history, drafts or shadow rows (as migration 0021 seeds them)."""
    conn.execute(text("DELETE FROM shadow_decision"))
    conn.execute(text("DELETE FROM decision_flow_version"))
    conn.execute(text("DELETE FROM decision_flow WHERE org_unit_id <> 'workspace'"))
    for key in TEMPLATE_KEYS:
        conn.execute(
            text(
                "UPDATE decision_flow SET status = 'pub', ver = 1, dver = NULL, maker = NULL, checker = NULL, "
                "draft = NULL, returned = NULL, published = CAST(:g AS jsonb) "
                "WHERE template_key = :k AND org_unit_id = 'workspace'"
            ),
            {"k": key, "g": json.dumps(default_flow(load_template(key)))},
        )
