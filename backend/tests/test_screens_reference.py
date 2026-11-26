"""B14: the reference lists (GET /api/screens/reference) are the demo's constants, the same for everyone, and agree with
the other golden files and the backend's own copies of them; the menu (GET /api/screens/nav) is the one each account
sees in the demo (fixtures/golden/screens/nav.json), with its badges and task count.
"""

import os

import pytest
from sqlalchemy import text

from di.core import golden, policy
from di.core.db import engine
from di.repositories import common, workspace
from di.services.screens import checks
from di.services.screens.nav import ISSUE_SQL
from tests import starting
from tests.helpers import client, h, live_stale_sources

REF = golden.load("screens/reference")
NAV = golden.load("screens/nav")


@pytest.fixture(scope="module", autouse=True)
def _start():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


# ---------------------------------------------------------------- reference
def test_reference_is_the_demos_constants():
    r = client.get("/api/screens/reference")  # the sign-in page reads it before anyone signs in
    assert r.status_code == 200
    # PACK_CLASSES is the one list that is not the demo's: the packs' own classes (UI audit gap 8)
    assert starting.strict({k: v for k, v in r.json().items() if k != "PACK_CLASSES"}) == starting.strict(REF)
    for acct in ("planner-b", "wm-1", "admin"):
        assert client.get("/api/screens/reference", headers=h(acct)).json() == r.json()


def test_ui_audit_8_pack_classes_name_every_pack_class_without_touching_the_demos_classes():
    from di.services.modeler.pack import load_pack, pack_keys

    r = client.get("/api/screens/reference", params={"names": "CLASSES,PACK_CLASSES"}).json()
    assert r["CLASSES"] == REF["CLASSES"]  # the demo's six classes are unchanged
    pc = r["PACK_CLASSES"]
    for k in ("car_ice", "radio", "infusion_pump", "CMH", "phone"):
        assert k in pc, k
    assert pc["car_ice"] == {"label": "Car (combustion)", "pack": "used_cars", "pack_name": load_pack("used_cars").name}
    assert not set(pc) & set(REF["CLASSES"])  # a demo class keeps its own entry
    for key in pack_keys():
        for cl in load_pack(key).classes:
            assert cl.id in pc or cl.id in REF["CLASSES"], (key, cl.id)


def test_ui_audit_c8_every_asset_family_has_named_classes():
    pc = client.get("/api/screens/reference", params={"names": "PACK_CLASSES"}).json()["PACK_CLASSES"]
    for k in ("car_ev", "router", "patient_monitor", "laptop", "ev_pack", "industrial_pack", "alternator", "excavator_20t"):
        assert pc[k]["label"].strip() and pc[k]["label"] != k, k  # a plain name, never the id
    assert {pc[k]["pack"] for k in ("ev_pack", "alternator", "laptop")} == {"battery", "auto_core", "itad"}


def test_reference_by_name():
    r = client.get("/api/screens/reference", params={"names": "MONTHS, ROUTES"})
    assert r.json() == {"MONTHS": REF["MONTHS"], "ROUTES": REF["ROUTES"]}
    r = client.get("/api/screens/reference", params={"names": "MONTHS,NOPE"})
    assert r.status_code == 404


def test_reference_agrees_with_the_other_golden_files():
    world, pol, tools = golden.load("world"), golden.load("policy"), golden.load("tools")
    for name, key in [("MONTHS", "months"), ("TENANTS", "tenants"), ("SITES", "sites"), ("FACILITIES", "facilities"),
                      ("ROUTES", "routes"), ("MODELS", "models"), ("GATES", "gates"), ("CLASSES", "classes"),
                      ("AS_OF", "as_of")]:  # fmt: skip
        assert REF[name] == world[key], name
    assert REF["ROLE_POLICY"] == pol["role_policy"]
    assert REF["PERM_ALIAS"] == pol["perm_alias"]
    assert REF["RB_SECS"] == pol["sections"]
    assert REF["TOOLS"] == tools["tools"]
    assert REF["HARD_RULES"] == tools["hard_rules"]
    assert REF["CANON"] == golden.load("canonical")["models"]
    assert REF["SRC_TYPES"] == golden.load("sources")["types"]


def test_reference_agrees_with_the_backends_copies():
    assert REF["CC_CAP"] == workspace.CC_CAP
    assert REF["CC_REASONS"] == workspace.CC_REASONS
    assert REF["EX_FX"] == common.EX_FX
    assert REF["RISK_LABEL"] == checks.RISK_LABEL
    assert REF["REQ_KIND"] == common.REQ_KIND
    assert {k: round(v, 6) for k, v in workspace.cc_est_per_unit().items()} == REF["CC_EST"]
    assert REF["JSTEPS"] == REF["JSTEPS_AF"] and REF["JMAP"][:11] == [0, 5, 6, 6, 6, 7, 8, 8, 8, 9, 10]


def test_reference_has_no_state():
    """State and per-account data are served by each area's endpoints, assets are bundled with the app."""
    for name in ("ACCOUNTS", "AGENTS", "CLIENT_SERVERS", "MAPPINGS", "SOURCES", "CONFLICTS", "EVENTS", "CALLS", "EXPECTED",
                 "POOLS", "ROWS", "CASE_BY_ID", "ACTIONS", "AF", "S", "ICON", "LOGO", "LOGO_INK"):  # fmt: skip
        assert name not in REF


# ---------------------------------------------------------------- the menu
def with_org_section(acct: str, groups: list[dict]) -> list[dict]:
    """The demo's menu, with Access's Organisation section for whoever may see it (plan 8 MVP-1.5: a deliberate
    change, decision-log "Org units replace the fixed tenants"; policy.EXTRA_SECTIONS)."""
    groups = with_mywork(with_agents(acct, with_modeler(acct, groups)))
    if not policy.can_page(policy.account(acct), "access", "orgs"):
        return groups
    kid = {"id": "orgs", "label": "Organisation", "sub": "Groups, companies, sites and customers", "href": "#/access/orgs"}
    return [g | {"kids": [*g["kids"], kid]} if g["id"] == "access" else g for g in groups]


def with_mywork(groups: list[dict]) -> list[dict]:
    """My work (plan 9 P9-1.8, a new page for every role: policy.EXTRA_PAGES) before the first group."""
    g = {"id": "mywork", "label": "My work", "sub": "Exceptions, approvals and questions for you", "icon": "inbox",
         "section": "", "leaf": True, "href": "#/mywork", "kids": []}  # fmt: skip
    return [g, *groups]


def with_modeler(acct: str, groups: list[dict]) -> list[dict]:
    """The Modeler page (plan 8 MVP-4.2, a new page: policy.EXTRA_PAGES) before the first group of the More section."""
    if not policy.can_page(policy.account(acct), "modeler"):
        return groups
    g = {"id": "modeler", "label": "Modeler", "sub": "Decision process and business rules", "icon": "branch",
         "section": "Integration", "leaf": True, "href": "#/modeler", "kids": []}  # fmt: skip
    at = next((i for i, x in enumerate(groups) if x["section"] == "More"), len(groups))
    return [*groups[:at], g, *groups[at:]]


def with_agents(acct: str, groups: list[dict]) -> list[dict]:
    """The Agents page (plan 8 MVP-11.8, a new page: policy.EXTRA_PAGES) after MCP & Tools (before Process
    Orchestration); both accounts that see it see MCP & Tools."""
    if not policy.can_page(policy.account(acct), "agents"):
        return groups
    g = {"id": "agents", "label": "Agents", "sub": "Registry, runs, proposals and tools", "icon": "bot",
         "section": "More", "leaf": True, "href": "#/agents", "kids": []}  # fmt: skip
    at = [x["id"] for x in groups].index("mcp") + 1
    return [*groups[:at], g, *groups[at:]]


@pytest.mark.parametrize("acct", list(NAV["accounts"]))
def test_navigation(acct):
    r = client.get("/api/screens/nav", headers=h(acct))
    assert r.status_code == 200, r.text
    out, want = r.json(), NAV["accounts"][acct]
    assert starting.strict(out["groups"]) == starting.strict(with_org_section(acct, want["navigation"]))
    tasks = want["tasks"]
    if acct == "developer":  # its stale or unconnected sources are the live Connection Fabric's (decision-log D-Fabric)
        demo_stale = sum(1 for s in common.SOURCES.values() if s["status"] in ("stale", "unavailable"))
        tasks = tasks - demo_stale + len(live_stale_sources())
    assert out["tasks"] == tasks
    b, wb = out["badges"], want["badges"]
    assert {k: b[k] for k in ("awaiting", "inbox")} == {k: wb[k] for k in ("awaiting", "inbox")}
    assert {k: b["sections"][k] for k in ("inbox", "wffail")} == {k: wb["sections"][k] for k in ("inbox", "wffail")}
    # open conflicts (B17 decision): the real conflict table, only conflicts holding up a pending decision in scope
    me = client.get("/api/auth/me", headers=h(acct)).json()
    with engine.connect() as conn:
        held = conn.execute(text(HELD_SQL), {"tenants": me["tenants"], "wh": me["warehouse"]}).scalar()
    assert b["sections"]["conf"] == held
    assert b["integration"] == (held if "conflicts" in me["pages"].get("integration", []) else 0)
    # sources stale or unavailable: the connectors' real state, not the demo's. It changes as sources sync (the demo
    # shows 2; a live database can show 1 or more), so the badge is compared with the source table, not the golden file.
    with engine.connect() as conn:
        n = conn.execute(text(ISSUE_SQL)).scalar()
    assert b["sections"]["srcissue"] == n


HELD_SQL = """
SELECT count(*) FROM conflict c JOIN case_record r ON r.data->>'assetId' = c.key
WHERE c.status IN ('open', 'escalated') AND r.stage IN ('none', 'awaiting_approval')
  AND r.owner = ANY(:tenants) AND (CAST(:wh AS text) IS NULL OR r.location = :wh)
"""


def test_held_conflicts_are_fewer_than_the_queue():
    b = client.get("/api/screens/nav", headers=h("admin")).json()["badges"]
    with engine.connect() as conn:
        queue = conn.execute(text("SELECT count(*) FROM conflict WHERE status IN ('open', 'escalated')")).scalar()
    assert 0 < b["sections"]["conf"] < queue


def test_case_scope_map():
    """Owner and location of every case, for the frontend's canRoute on record links; signing in is required."""
    assert client.get("/api/screens/nav/scope").status_code == 401
    out = client.get("/api/screens/nav/scope", headers=h("planner-b")).json()
    assert len(out) == 128 and out["RT-1048"] == ["Customer A", "Warehouse 1"]


def test_admin_senior_view():
    out = client.get("/api/screens/nav", params={"cc_mode": "senior"}, headers=h("admin")).json()
    assert starting.strict(out["groups"]) == starting.strict(with_org_section("admin", NAV["admin_senior"]))


def test_last_asset_link():
    def asset_href(acct, last):
        g = client.get("/api/screens/nav", params={"last_asset": last}, headers=h(acct)).json()["groups"]
        prod = next(x for x in g if x["id"] == "product")
        return next(k["href"] for k in prod["kids"] if k["id"] == "asset")

    assert asset_href("planner-a", "RT-1049") == "#/product/asset/RT-1049"
    # a case in another tenant falls back to the first visible case
    first = asset_href("planner-b", None)
    assert asset_href("planner-b", "RT-1048") == first != "#/product/asset/RT-1048"


def test_accounts_for_the_sign_in_page():
    r = client.get("/api/screens/nav/accounts")
    assert r.status_code == 200
    got = r.json()
    assert [a["id"] for a in got] == [a.id for a in policy.starting_accounts()]
    assert next(a for a in got if a["id"] == "planner-b")["email"] == "planner.b@northfield.example"


def test_me_carries_the_session():
    """What session.ts needs after sign-in is in /api/auth/me already."""
    me = client.get("/api/auth/me", headers=h("planner-a")).json()
    assert {"account", "home", "permissions", "pages", "tenants", "warehouse"} <= set(me)
    assert me["account"]["email"] == "planner.a@northfield.example"
