"""Plan 8 UI gaps (Gaps-D): the reads behind the Access page's Organisation section and the Connect dialog's org field.

    GET /api/screens/orgs                    the org units the account may see (Connect dialog, Organisation section),
                                             with pilot mode per unit for accounts that may manage orgs or read reports
    GET /api/screens/orgs/{unit}/pilot       the pilot report (org.pilotReport) and the instructions held, i.e. what
                                             would have been sent
    org.previewPack (read, manageOrgs)       what importing a pack would create; changes nothing

Units a test makes start with "t-org-"; the instruction a test inserts has idem_key "t-org-screens-%"; pilot settings
are removed afterwards. The seeded tree (workspace, Customer A/B/C) is never changed.
"""

import copy
import json
from typing import Any

import pytest
from sqlalchemy import text

from di.core import state
from di.core.db import SessionLocal, engine
from di.services.actions import org_pilot
from tests.helpers import call, client, h

PILOT = "/api/screens/orgs/{}/pilot"


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM instruction WHERE idem_key LIKE 't-org-screens-%'"))
        conn.execute(text("DELETE FROM org_unit WHERE id LIKE 't-org-%'"))
    with SessionLocal() as s:
        for x in state.items(s, org_pilot.COLLECTION):
            state.delete(s, org_pilot.COLLECTION, x["id"])
        s.commit()


@pytest.fixture(autouse=True)
def clean():
    _cleanup()
    yield
    _cleanup()


def _screen(user: str) -> dict:
    r = client.get("/api/screens/orgs", headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def _ok(r: dict) -> dict:
    assert r["ok"], r
    return r["output"]


# ---------------------------------------------------------------- the units
def test_admin_sees_every_unit_with_pilot_mode():
    out = _screen("admin")
    assert [(u["id"], u["depth"]) for u in out["units"]] == [
        ("workspace", 0), ("Customer A", 1), ("Customer B", 1), ("Customer C", 1),
    ]  # fmt: skip
    a = next(u for u in out["units"] if u["id"] == "Customer A")
    assert (a["parent_id"], a["kind"], a["name"]) == ("workspace", "customer", "Customer A")
    assert out["can"] == {"manage": True, "report": True}
    assert all(u["pilot"] is False and u["pilot_via"] is None for u in out["units"])


def test_scoped_account_sees_its_units_without_pilot():
    out = _screen("planner-a")
    assert [u["id"] for u in out["units"]] == ["Customer A"]
    assert out["can"] == {"manage": False, "report": False}
    assert all("pilot" not in u for u in out["units"])


def test_pilot_inherited_from_a_parent():
    _ok(call("org.setPilot", {"org_unit_id": "workspace", "on": True}, "admin"))
    units = {u["id"]: u for u in _screen("admin")["units"]}
    assert (units["workspace"]["pilot"], units["workspace"]["pilot_via"]) == (True, "workspace")
    assert (units["Customer B"]["pilot"], units["Customer B"]["pilot_via"]) == (True, "workspace")
    _ok(call("org.setPilot", {"org_unit_id": "workspace", "on": False}, "admin"))
    assert not any(u["pilot"] for u in _screen("admin")["units"])


def test_renamed_unit_shows_its_new_name():
    _ok(call("org.create", {"id": "t-org-east", "parent_id": "workspace", "kind": "group", "name": "East"}, "admin"))
    _ok(call("org.update", {"id": "t-org-east", "name": "East region"}, "admin"))
    east = next(u for u in _screen("admin")["units"] if u["id"] == "t-org-east")
    assert east["name"] == "East region"
    refused = call("org.update", {"id": "t-org-east", "name": "X"}, "planner-a")
    assert refused["ok"] is False and refused["error"]["code"] == "out_of_scope"


# ---------------------------------------------------------------- the pilot report
def _held_instruction() -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, detail, status, simulated) "
                "VALUES ('RT-1048', 't-ref', 0, 'allocate', 'oms', 't-org-screens-1', CAST(:d AS jsonb), 'sent', true) "
                "RETURNING id"
            ),
            {"d": json.dumps({"held": True, "note": "Pilot mode: not sent to IBM Sterling OMS"})},
        ).scalar_one()


def test_pilot_report_lists_what_would_have_been_sent():
    iid = _held_instruction()
    r = client.get(PILOT.format("Customer A"), headers=h("admin"))
    assert r.status_code == 200, r.text
    out = r.json()
    report = _ok(call("org.pilotReport", {"org_unit_id": "Customer A"}, "admin"))
    assert {k: out[k] for k in report} == report
    assert out["instructions_held"] == 1 and out["pilot"] is False
    (held,) = out["held"]
    assert held["id"] == iid and held["case_id"] == "RT-1048" and held["system"] == "oms"
    assert held["kind"] == "allocate" and held["note"] == "Pilot mode: not sent to IBM Sterling OMS"
    assert held["target"]  # the system's vendor name
    assert client.get(PILOT.format("Customer B"), headers=h("admin")).json()["held"] == []


def test_pilot_report_access_is_enforced():
    assert client.get(PILOT.format("Customer A"), headers=h("planner-a")).status_code == 403
    assert client.get(PILOT.format("Nowhere"), headers=h("admin")).status_code == 404
    assert client.get(PILOT.format("workspace"), headers=h("approver")).status_code == 200


# ---------------------------------------------------------------- the import preview
def _pack() -> dict:
    return _ok(call("org.exportPack", {"org_unit_id": "Customer A"}, "admin"))


def _counts() -> tuple[int, int]:
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT count(*) FROM source_system")).scalar_one(),
            conn.execute(text("SELECT count(*) FROM decision_flow")).scalar_one(),
        )


def test_preview_changes_nothing_and_names_new_ids():
    pack = copy.deepcopy(_pack())
    src: dict[str, Any] = {
        "id": "erp",
        "name": "ERP copy",
        "type": "erp",
        "vendor": "SAP S/4HANA",
        "connection": None,
        "config": {},
    }
    pack["sources"] = [src, dict(src, name="ERP copy 2")]
    pack["mappings"] = {"erp": [["a", "", "asset.id", "", "copy"]]}
    pack["workflows"] = []
    before = _counts()
    out = _ok(call("org.previewPack", {"pack": pack, "target_org_unit_id": "Customer B"}, "admin"))
    assert _counts() == before
    assert out["target_org_unit_id"] == "Customer B" and out["origin"] == "Customer A"
    assert [(x["id"], x["new_id"]) for x in out["sources"]] == [("erp", "erp_2"), ("erp", "erp_3")]
    assert out["mappings"] == ["erp_2", "erp_3"]
    assert out["needs"] == ["credentials for ERP copy", "credentials for ERP copy 2"]
    assert {f["template"] for f in out["flows"]} == set(pack["flows"])
    assert all(f["fork"] is True for f in out["flows"])  # Customer B has no flow of its own yet


def test_preview_is_refused_like_the_import():
    pack = _pack()
    r = call("org.previewPack", {"pack": pack, "target_org_unit_id": "Customer B"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    r = call("org.previewPack", {"pack": {"version": 2}, "target_org_unit_id": "Customer B"}, "admin")
    assert r["error"]["code"] == "validation_error"
    r = call("org.previewPack", {"pack": pack, "target_org_unit_id": "Nowhere"}, "admin")
    assert r["error"]["code"] == "not_found"


# ---------------------------------------------------------------- the Connect dialog's org field
def test_connect_checks_the_org_unit():
    body = {"mode": "catalog", "id": "", "d": {"catalog": "postgres", "auth": "key", "scopes": ["read"]}, "maps": [],
            "ops": {}, "org_unit_id": "t-org-nowhere"}  # fmt: skip
    r = call("source.update", body, "developer")
    assert r["ok"] is False and r["error"] == {"code": "validation_error", "message": "No org unit t-org-nowhere."}
