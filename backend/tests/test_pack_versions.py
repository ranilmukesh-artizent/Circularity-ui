"""P9-1.6 (I-1, stories X-01 and X-03; R21): pack versions through the pipeline with maker-checker
(di.services.actions.packs): import a pack as a draft, submit, approve (published, the previous version retired, the
customer overlays rebased) or return it, and open a case with an imported pack, with no code changed. Every test ends
with the starting state."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import packs as repo
from di.repositories.overlays import get as get_overlay
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.modeler.pack import PACKS_DIR
from tests import starting
from tests.helpers import call, client, h

MAKER_CHECKER = "Maker-checker: you made these changes, so you cannot approve them."
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "packs" / "device_eu.json"
LOT = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12}
TIGHTEN = {"id": "op-1", "op": "tighten", "target": "GR-D2", "field": "floor", "value": 0.60, "seen": 0.55}


def _device() -> dict[str, Any]:
    return json.loads((PACKS_DIR / "device.json").read_text(encoding="utf-8"))


def _doc(version: str, *, floor: float | None = None, wipe: bool = False) -> dict[str, Any]:
    """The device pack at `version`, with the GR-D2 floor and the data-wipe gate as asked."""
    d = copy.deepcopy(_device())
    d["version"] = version
    for g in d["guardrails"]:
        if g["id"] == "GR-D2" and floor is not None:
            g["param"]["value"] = floor
    if wipe:
        d["gates"] = [{"id": "G-DEV-WIPE", "params": {}, "active": True}]
    return d


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    _clean()
    starting.reset()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _import(doc: dict, user: str = "admin", **more: Any) -> int:
    return int(ok(call("pack.import", {"doc": doc} | more, user))["id"])


def _publish(doc: dict, maker: str = "admin") -> int:
    pid = _import(doc, maker)
    ok(call("pack.submit", {"id": pid}, maker))
    ok(call("pack.approve", {"id": pid}, "approver"))
    return pid


def _row(pid: int) -> Any:
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM pack_version WHERE id = :i"), {"i": pid}).mappings().one()


def _open(asset: str, key: str, user: str = "planner-a") -> dict:
    body = {"org_unit_id": "Customer A", "template_key": key, "asset_key": asset, "reason": "manual", "facts": LOT}
    return call("case.open", body, user)


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def test_x_01_pack_imports_through_pipeline():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pid = _import(doc)
    row = _row(pid)
    assert (row["key"], row["version"], row["status"], row["maker"]) == ("device_eu", "1.0.0", "draft", "admin")
    assert row["impact"] is not None and row["org_unit_id"] is None
    assert _open("EU-0", "device_eu")["error"]["code"] == "validation_error"  # a draft is not a template yet
    assert ok(call("pack.submit", {"id": pid}, "planner-a"))["status"] == "review"
    assert ok(call("pack.approve", {"id": pid}, "approver"))["status"] == "pub"
    row = _row(pid)
    assert (row["status"], row["checker"]) == ("pub", "approver") and row["published_at"] is not None
    with SessionLocal() as s:
        assert repo.published_keys(s) == {"device_eu"}
    opened = ok(_open("EU-1", "device_eu"))
    same = ok(_open("EU-2", "device"))
    c = _case(opened["case_id"])
    assert c["template"] == "device_eu" and c["recommendation"] is not None and c["stage"] == "awaiting_approval"
    assert opened["recommendation"] == same["recommendation"]  # the same pack content decides the same route


def test_x_01_missing_part_refused():
    doc = _doc("2.8.0")
    del doc["routes"]
    r = call("pack.import", {"doc": doc}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert (r["error"]["part"], r["error"]["part_name"]) == (5, "routes")
    assert r["error"]["message"] == "Pack device v2.8.0: part 5 (routes): Field required"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pack_version")).scalar() == 0


def test_x_03_gate_change_needs_approval():
    pid = _import(_doc("2.8.0", wipe=True))
    ok(call("pack.submit", {"id": pid}, "planner-a"))
    before = _case(ok(_open("GT-1", "device"))["case_id"])
    assert before.get("gateHold") is None and before["recommendation"] is not None  # the draft changes nothing
    ok(call("pack.approve", {"id": pid}, "approver"))
    assert _case(before["id"]).get("gateHold") is None  # a case opened before is not held
    after = _case(ok(_open("GT-2", "device"))["case_id"])
    assert after["stage"] == "none" and after["gateHold"]["gates"] == ["G-DEV-WIPE"]


def test_x_03_agent_cannot_publish_gate_change():
    assert forbidden("pack.approve") and forbidden("pack.reject")
    agent = h("admin") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post("/api/actions/pack.import", json={"doc": _doc("2.8.0", wipe=True)}, headers=agent)
    assert r.status_code == 200 and r.json()["ok"], r.json()
    pid = int(r.json()["output"]["id"])
    assert _row(pid)["status"] == "draft"
    ok(call("pack.submit", {"id": pid}, "planner-a"))
    for extra in ({}, {"X-Circularity-Confirmed": "true"}):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"} | extra
        r = client.post("/api/actions/pack.approve", json={"id": pid}, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", r.json()
    assert _row(pid)["status"] == "review"


def test_pack_maker_cannot_approve():
    pid = _import(_doc("2.8.0"), "admin")
    ok(call("pack.submit", {"id": pid}, "admin"))
    r = call("pack.approve", {"id": pid}, "admin")
    assert r == {"ok": False, "error": {"code": "conflict", "message": MAKER_CHECKER}}
    assert _row(pid)["status"] == "review"
    assert ok(call("pack.approve", {"id": pid}, "approver"))["status"] == "pub"


def test_pack_submitter_cannot_approve():
    pid = _import(_doc("2.8.0"), "admin")
    ok(call("pack.submit", {"id": pid}, "planner-a"))
    assert call("pack.approve", {"id": pid}, "planner-a")["error"]["code"] == "out_of_scope"  # no approve.packs
    ok(call("pack.reject", {"id": pid, "reason": "Floor too high for this quarter."}, "approver"))
    assert _row(pid)["status"] == "draft" and "Floor too high" in _row(pid)["note"]
    ok(call("pack.submit", {"id": pid}, "admin"))  # admin only sends it on: still its maker
    assert call("pack.approve", {"id": pid}, "admin")["error"]["message"] == MAKER_CHECKER


def test_pack_agent_cannot_approve():
    pid = _import(_doc("2.8.0"))
    ok(call("pack.submit", {"id": pid}, "admin"))
    for action, body in (("pack.approve", {"id": pid}), ("pack.reject", {"id": pid, "reason": "Not for this quarter, sorry."})):
        hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"}
        r = client.post(f"/api/actions/{action}", json=body, headers=hdr)
        assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", (action, r.json())
    assert _row(pid)["status"] == "review"


def test_pack_tenant_boundary():
    r = call("pack.import", {"doc": _doc("2.8.0"), "org_unit_id": "Customer B"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"
    assert r["error"]["message"] == "Customer B is a tenant you cannot see. Request tenant access first."
    r = call("pack.import", {"doc": _doc("2.8.0")}, "planner-a")
    assert r["error"] == {"code": "out_of_scope", "message": "Only Admin imports a pack for every org."}
    own = ok(call("pack.import", {"doc": _doc("2.8.0"), "org_unit_id": "Customer A"}, "planner-a"))
    assert _row(int(own["id"]))["org_unit_id"] == "Customer A"
    other = _import(_doc("2.9.0"), org_unit_id="Customer B")
    assert call("pack.submit", {"id": other}, "planner-a")["error"]["code"] == "tenant_boundary"
    ok(call("pack.submit", {"id": other}, "admin"))
    assert call("pack.reject", {"id": other, "reason": "A reason long enough."}, "planner-a")["ok"] is False
    assert _row(other)["status"] == "review"


def test_pack_org_version_is_used_by_its_org_only():
    pid = _import(_doc("2.8.0", wipe=True), org_unit_id="Customer A")
    ok(call("pack.submit", {"id": pid}, "planner-a"))
    ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        assert repo.active_pack(s, "device", "Customer A").version == "2.8.0"
        assert repo.active_pack(s, "device", "Customer B").version == "2.7.0"
        assert repo.active_pack(s, "device", "workspace").version == "2.7.0"


def test_pack_publish_retires_the_previous_version():
    first = _publish(_doc("2.8.0"))
    second = _publish(_doc("2.9.0"))
    assert (_row(first)["status"], _row(second)["status"]) == ("retired", "pub")
    with SessionLocal() as s:
        assert repo.active_pack(s, "device", "Customer A").version == "2.9.0"
        assert [v["version"] for v in repo.versions(s, "device")] == ["2.9.0", "2.8.0"]


def _floor(pack: Any) -> float:
    return next(g.param.value for g in pack.guardrails if g.id == "GR-D2" and g.param)


def test_pack_publish_rebases_overlays():
    ok(call("overlay.save", {"pack_key": "device", "org_unit_id": "Customer A", "ops": [TIGHTEN]}, "planner-a"))
    ok(call("overlay.submit", {"pack_key": "device", "org_unit_id": "Customer A"}, "planner-a"))
    ok(call("overlay.approve", {"pack_key": "device", "org_unit_id": "Customer A"}, "approver"))
    _publish(_doc("2.8.0", floor=0.58))
    with SessionLocal() as s:
        row = get_overlay(s, "device", "Customer A")
    assert row is not None and (row.status, row.conflicts, row.draft_base_version) == ("draft", [], "2.8.0")
    assert row.draft is not None and row.draft[0]["value"] == 0.60 and row.draft[0]["seen"] == 0.58
    assert row.published[0]["value"] == 0.60 and row.base_version == "2.7.0"  # what runs is unchanged
    _publish(_doc("2.9.0", floor=0.65))
    with SessionLocal() as s:
        row = get_overlay(s, "device", "Customer A")
        assert _floor(repo.active_pack(s, "device", "Customer A")) == 0.65
    assert row is not None and row.draft == [] and row.draft_base_version == "2.9.0"
    assert row.notes == ["GR-D2: the pack is now stricter (0.65); your change is no longer needed."]


def test_pack_publish_notes_a_new_locked_gate_on_a_rebased_overlay():
    no_wipe = _doc("2.7.5")  # the base device pack has the data-wipe gate since P9-6.x: start from a version without it
    no_wipe["gates"] = [g for g in no_wipe["gates"] if g["id"] != "G-DEV-WIPE"]
    _publish(no_wipe)
    ok(call("overlay.save", {"pack_key": "device", "org_unit_id": "Customer A", "ops": [TIGHTEN]}, "planner-a"))
    ok(call("overlay.submit", {"pack_key": "device", "org_unit_id": "Customer A"}, "planner-a"))
    ok(call("overlay.approve", {"pack_key": "device", "org_unit_id": "Customer A"}, "approver"))
    _publish(_doc("2.8.0", wipe=True))
    with SessionLocal() as s:
        row = get_overlay(s, "device", "Customer A")
    assert row is not None and "Data-wipe certificate added by the pack" in row.notes


def test_x_01_industrial_demo_pack_is_not_imported():
    doc = json.loads((PACKS_DIR / "industrial.json").read_text(encoding="utf-8"))
    doc["version"] = "99.0.0"
    r = call("pack.import", {"doc": doc}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"] == "The industrial demo pack is not imported in plan 9."


def test_x_01_a_pack_version_keeps_its_valuer_kind():
    doc = json.loads((PACKS_DIR / "tool_fleet.json").read_text(encoding="utf-8"))
    doc["key"], doc["version"] = "device", "9.0.0"  # a tool-fleet valuer under the device key
    r = call("pack.import", {"doc": doc}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"
    assert r["error"]["message"].startswith("A pack version keeps its valuer kind")


def test_version_must_increase():
    r = call("pack.import", {"doc": _doc("2.7.0")}, "admin")
    assert r["error"] == {"code": "conflict", "message": "Pack device 2.7.0 is not newer than 2.7.0."}
    _import(_doc("2.8.0"))
    for version, newest in (("2.8.0", "2.8.0"), ("2.7.5", "2.8.0")):
        got = call("pack.import", {"doc": _doc(version)}, "admin")["error"]["message"]
        assert got == f"Pack device {version} is not newer than {newest}."
    assert ok(call("pack.import", {"doc": _doc("2.10.0")}, "admin"))["status"] == "draft"  # semver, not text order


def test_pack_permissions():
    assert call("pack.import", {"doc": _doc("2.8.0")}, "approver")["error"]["code"] == "out_of_scope"
    assert call("pack.import", {"doc": _doc("2.8.0")}, "exec")["error"]["code"] == "out_of_scope"
    pid = _import(_doc("2.8.0"))
    assert call("pack.submit", {"id": pid}, "approver")["error"]["code"] == "out_of_scope"
    assert call("pack.approve", {"id": pid}, "approver")["error"]["code"] == "conflict"  # still a draft


def test_x_01_impact_counts_the_open_cases_and_the_sample_queue():
    ok(_open("IM-1", "device"))
    pid = _import(_doc("2.8.0", wipe=True))
    impact = _row(pid)["impact"]
    assert set(impact) == {"changed", "total", "dv"} and impact["total"] >= 1
    assert impact["changed"] >= 1  # a lot with no wipe record is held under the new gate


def test_x_01_screen_lists_versions_and_the_template_picker():
    pid = _import(json.loads(FIXTURE.read_text(encoding="utf-8")))
    url = "/api/screens/modeler"
    out = client.get(url, params={"template": "device", "org": "Customer A"}, headers=h("planner-a")).json()
    assert [t["key"] for t in out["packs"]["templates"]] == ["industrial", "tool_fleet", "device"]  # a draft is not offered
    packs = {p["key"]: p for p in out["packs"]["keys"]}
    assert packs["device_eu"]["versions"][0]["status"] == "draft"
    assert packs["device_eu"]["versions"][0]["parts"] == {"ok": 13, "total": 13}
    assert out["packs"]["can"] == {"import": True, "approve": False}
    ok(call("pack.submit", {"id": pid}, "admin"))
    ok(call("pack.approve", {"id": pid}, "approver"))
    out = client.get(url, params={"template": "device", "org": "Customer A"}, headers=h("approver")).json()
    assert [t["key"] for t in out["packs"]["templates"]] == ["industrial", "tool_fleet", "device", "device_eu"]
    assert out["packs"]["can"] == {"import": False, "approve": True}
