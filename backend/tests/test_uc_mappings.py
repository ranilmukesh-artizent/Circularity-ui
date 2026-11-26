"""P9-9.13 (UC-03, UC-04; registry entries I-18, I-19): the used-car pack's unsure mappings and its legacy body-shop connector.

UC-03: the lease system's mileage at return (0.77) and the inspection app's condition score (0.72) are the pack's two hints,
both under the pack's threshold 0.80, so each needs a person's choice among the five (accept, choose another field, accept with
a conversion, not needed, ask the system owner); the flow cannot be sent for approval while one has no choice, and the Compose
test run over past cars says where they stopped. UC-04: the body-shop system has no adapter: its connector is built from its
OpenAPI document (`registry.importSpec`, kind `from_spec`), the system owner approves the connection (a person's act, forbidden
to agents), discovery samples 500 records and proposes the two mappings; until the connection is live the case says "Older
damage history not connected".

The body-shop system is played by an in-process fake (httpx.MockTransport) that serves what source-sim's mock serves
(`source-sim/sim/vendors/body_shop_legacy`; `source-sim/tests/test_body_shop_legacy.py` pins the same document and rows), so
no source-sim is needed. Models are `FunctionModel`s: no test reaches a provider.
"""

# ruff: noqa: E501 - long lines in the SQL, the document and the call bodies
import copy
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from di.connectors import connection, discover, sync
from di.connectors.http import ApiKey, SourceClient
from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.services.actions.connections import imported_entry
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents import runtime
from di.services.agents.forbidden import forbidden
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.canonical import store as canonical
from di.services.canonical.schema import vin_key
from di.services.modeler.pack import load_pack
from tests import ucfixtures as uc
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ORG = "Customer A"
BASE = "http://source-sim:8100/body-shop"
NOTE = "Older damage history not connected"
KEY = "uc_bodyshop-demo-key"
AREAS = ("front bumper", "rear quarter panel", "driver door", "hood", "windshield", "roof")

# the document `GET /body-shop/openapi.json` serves (source-sim/sim/vendors/body_shop_legacy/routes.py)
_REPAIR = {
    "type": "object",
    "required": ["repairId", "vin", "damageArea", "repairDate", "cost", "insuranceClaim"],
    "properties": {
        "repairId": {"type": "string"}, "vin": {"type": "string"}, "damageArea": {"type": "string"},
        "repairDate": {"type": "string", "format": "date"}, "cost": {"type": "number"}, "insuranceClaim": {"type": "boolean"},
    },
}  # fmt: skip
BODY_SHOP_DOC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Legacy body-shop system (synthetic)", "version": "1.0.0"},
    "servers": [{"url": "/body-shop"}],
    "security": [{"apiKey": []}],
    "paths": {
        "/repairs": {
            "get": {
                "operationId": "listRepairs",
                "parameters": [
                    {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
                    {"name": "size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}},
                ],
                "responses": {
                    "200": {
                        "description": "One page of repairs",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RepairPage"}}},
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Repair": _REPAIR,
            "RepairPage": {
                "type": "object",
                "required": ["repairs", "page", "pages", "total"],
                "properties": {
                    "repairs": {"type": "array", "items": {"$ref": "#/components/schemas/Repair"}},
                    "page": {"type": "integer"},
                    "pages": {"type": "integer"},
                    "total": {"type": "integer"},
                },
            },
        },
        "securitySchemes": {"apiKey": {"type": "apiKey", "in": "header", "name": "x-api-key"}},
    },
}


def _repairs() -> list[dict[str, Any]]:
    """600 repairs over the cars ...001 to ...100, six each, as the mock's seed lays them out."""
    return [
        {"repairId": f"BS-{n:04d}", "vin": uc.vin((n - 1) % 100 + 1), "damageArea": AREAS[n % len(AREAS)],
         "repairDate": f"2026-0{1 + n % 9}-1{n % 9}", "cost": 180 + (n * 137) % 3400, "insuranceClaim": False}
        for n in range(1, 601)
    ]  # fmt: skip


REPAIRS = _repairs()


def _body_shop(req: httpx.Request) -> httpx.Response:
    assert req.headers.get("x-api-key") == KEY, "the connection signs in with its key"
    q = req.url.params
    page, size = int(q.get("page", 1)), int(q.get("size", 50))
    rows = REPAIRS[(page - 1) * size : page * size]
    return httpx.Response(200, json={"repairs": rows, "page": page, "pages": -(-len(REPAIRS) // size), "total": len(REPAIRS)})


def _fake_client(s, sid: str, handler: Callable[[httpx.Request], httpx.Response] = _body_shop) -> SourceClient:
    c = SourceClient(sid, BASE, ApiKey(header="x-api-key", key=KEY), s)
    c.http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


@pytest.fixture
def body_shop(monkeypatch):
    """The body-shop system answers discovery and the sync (the fake plays its host)."""
    monkeypatch.setattr(discover, "open_client", lambda s, sid, adapter: _fake_client(s, sid))
    monkeypatch.setattr(connection, "client_for", lambda s, sid, adapter, run_id=None, timeout=20: _fake_client(s, sid))


# ---------------------------------------------------------------- state
def _clean() -> None:
    with engine.begin() as c:
        made = list(c.execute(text("SELECT source_id FROM source_connection WHERE registry_id IS NOT NULL")).scalars())
        for t in ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM provenance WHERE source_id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM connection_approval"))
        c.execute(text("DELETE FROM work_item WHERE type LIKE 'connection_approval%' OR type LIKE 'mapping_owner%'"))
        c.execute(text("DELETE FROM adapter_registry"))
        c.execute(text("DELETE FROM mapping_decision"))
        c.execute(text("DELETE FROM raw_record WHERE source_id IN ('uc_lease', 'uc_insp')"))
        c.execute(text("DELETE FROM job WHERE kind IN ('sync.source', 'case.recordMatch')"))
        c.execute(text("DELETE FROM replay_batch"))
        c.execute(text("DELETE FROM composition_version"))
        c.execute(text("DELETE FROM composition"))
        c.execute(text("DELETE FROM customer_overlay"))


@pytest.fixture(autouse=True)
def fresh():
    uc.start()
    _clean()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)
    _clean()
    uc.finish()


def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def refused(r: dict, code: str) -> str:
    assert r.get("ok") is False and r["error"]["code"] == code, r
    return r["error"]["message"]


def _seed_samples() -> None:
    """Eight cars' records as the lease system and the inspection app serve them, stored as a discovery sample."""
    with SessionLocal() as s:
        for sid in ("uc_lease", "uc_insp"):  # each system has a system owner, who answers a question about a field
            connection.save_connection(
                s,
                sid,
                "test",
                base_url="http://fake.test/api",
                auth_kind="none",
                resources=[{"name": "x", "path": "/x", "id_field": "id"}],
            )
            connection.tag(s, sid, environment="test", system_owner="approver", registry_id="generic-rest", registry_version=1)
        for n in range(1, 9):
            for sid, (resource, payload) in uc.records(n).items():
                if sid in ("uc_lease", "uc_insp"):
                    s.execute(
                        text(
                            "INSERT INTO raw_record (source_id, resource, ext_id, payload) VALUES (:s, :r, :e, CAST(:p AS jsonb))"
                        ),
                        {"s": sid, "r": resource, "e": f"{sid}-{n}", "p": json.dumps(payload)},
                    )
        s.commit()


def _suggest(sid: str) -> dict[str, dict[str, Any]]:
    out = ok(call("mapping.suggest", {"source_id": sid}, "developer"))
    return {r["field"]: r for r in out["rows"]}


# ---------------------------------------------------------------- UC-03
def test_uc_03_unsure_mappings_need_a_person():
    _seed_samples()
    threshold = next(m["value"] for m in load_pack("used_cars").data.mappings if m["kind"] == "threshold")
    hints = {m["field"]: m for m in load_pack("used_cars").data.mappings if m["kind"] == "hint"}
    miles = _suggest("uc_lease")["odometerAtReturn"]
    score = _suggest("uc_insp")["conditionScore"]
    assert (miles["target"], miles["confidence"]) == ("asset.mileage_at_return", 0.77)
    assert (score["target"], score["confidence"]) == ("condition.condition_score", 0.72)
    assert miles["reason"] == hints["odometerAtReturn"]["reason"] == "two mileage fields; the one taken at return was picked"
    assert score["reason"] == hints["conditionScore"]["reason"] == "direction of the 1–5 scale inferred from photos and notes"
    assert miles["confidence"] < threshold and score["confidence"] < threshold == 0.8
    assert miles["band"] == score["band"] == "check" and miles["decision"] is None and score["decision"] is None
    assert miles["proposed_by"] == "rule" and miles["candidates"]  # no model: the pack's figure; the candidates are still shown
    # the other fields of the sample keep the calibrated suggestions: only the pack's two are overridden
    assert _suggest("uc_lease")["odometerLastService"]["reason"] != miles["reason"]
    # each of the five choices records for the field, the last one wins, and nothing is saved by choosing
    body = {"source_id": "uc_lease", "src": "odometerAtReturn", "resource": "lease_returns"}
    for decision, extra in (
        ("accepted", {"target": "asset.mileage_at_return"}),
        ("replaced", {"target": "asset.mileage_lease_record"}),
        ("accepted_with_rule", {"target": "asset.mileage_at_return", "rule": "int"}),
        ("not_needed", {}),
    ):
        ok(call("mapping.decide", body | {"decision": decision} | extra, "developer"))
        assert _suggest("uc_lease")["odometerAtReturn"]["decision"]["decision"] == decision
    ok(call("mapping.askOwner", body | {"question": "Which odometer reading counts for the return?"}, "developer"))
    assert _suggest("uc_lease")["odometerAtReturn"]["decision"]["decision"] == "asked_owner"
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM field_mapping WHERE source_id = 'uc_lease'")).scalar_one() == 0


def _composition() -> int:
    return ok(
        call(
            "compose.start", {"org_unit_id": ORG, "text": load_pack("used_cars").prompts[0], "pack_key": "used_cars"}, "planner-a"
        )
    )["id"]


def _done(cid: int) -> None:
    for step in ("describe", "mapping", "agents"):
        ok(call("compose.markStep", {"id": cid, "step": step}, "planner-a"))


def _choose(src_id: str, field: str, resource: str, target: str) -> None:
    ok(
        call(
            "mapping.decide",
            {"source_id": src_id, "src": field, "resource": resource, "decision": "accepted", "target": target},
            "developer",
        )
    )


def test_uc_03_cannot_submit_with_undecided_field():
    _seed_samples()
    cid = _composition()
    _done(cid)
    msg = refused(call("compose.submit", {"id": cid}, "planner-a"), "conflict")
    assert msg.startswith("Not ready to submit:")
    assert "odometerAtReturn of uc_lease" in msg and "conditionScore of uc_insp" in msg and "no decision" in msg
    _choose("uc_lease", "odometerAtReturn", "lease_returns", "asset.mileage_at_return")
    msg = refused(call("compose.submit", {"id": cid}, "planner-a"), "conflict")
    assert "odometerAtReturn" not in msg and "conditionScore of uc_insp" in msg  # one field left
    # the fifth choice does not decide it: the owner must answer first
    ok(
        call(
            "mapping.askOwner",
            {"source_id": "uc_insp", "src": "conditionScore", "resource": "inspections", "question": "Is 5 the best?"},
            "developer",
        )
    )
    assert "waiting for its owner" in refused(call("compose.submit", {"id": cid}, "planner-a"), "conflict")
    _choose("uc_insp", "conditionScore", "inspections", "condition.condition_score")  # a person's choice replaces the question
    out = ok(call("compose.submit", {"id": cid}, "planner-a"))
    assert out["status"] == "submitted"


def _csv(rows: int = 20, bad: int = 2) -> str:
    """Past cars as a history file: the pack's sample facts, the last `bad` with a route the pack does not have."""
    head = [
        "item_id",
        "class",
        "decided_at",
        "reason",
        "actual_route",
        "realised_value",
        "cost_logistics",
        "cost_refurb",
        "cost_test",
        "cost_fees",
        "market",
    ]
    facts = {
        "asset.mileage_at_return": "38000",
        "asset.book_value": "19500",
        "condition.condition_score": "4",
        "condition.recon_estimate": "1200",
    }
    cols = [*head, *(c for f in facts for c in (f"fact.{f}", f"fact.{f}.at"))]
    out = [",".join(cols)]
    for n in range(1, rows + 1):
        route = "scrap" if n > rows - bad else "retail"
        row = [
            f"UC-H{n:03d}",
            "suv",
            f"2026-09-{n:02d}T10:00:00+00:00",
            "past car",
            route,
            "20000",
            "100",
            "200",
            "0",
            "50",
            "US",
        ]
        row += [c for v in facts.values() for c in (v, f"2026-09-{n:02d}T08:00:00+00:00")]
        out.append(",".join(row))
    return "\n".join(out) + "\n"


def test_uc_03_test_run_shows_where_cases_stopped():
    cid = _composition()
    batch = ok(call("replay.import", {"pack": "used_cars", "org_unit_id": ORG, "csv": _csv()}, "planner.a"))["id"]
    out = ok(call("compose.testRun", {"id": cid, "batch_id": batch}, "planner-a"))
    stops = {s["stage"]: s for s in out["stages"]}
    assert out["total"] == 20 and [s["stage"] for s in out["stages"]][:2] == ["receive", "match"]
    assert (stops["receive"]["reached"], stops["receive"]["stopped"]) == (20, 2)  # two rows were held at import
    assert [r["reason"] for r in stops["receive"]["reasons"]] == ["held_record:route"]
    match = stops["match"]  # stage 2, title and finance: no title search on file for a past car
    assert (match["reached"], match["stopped"]) == (18, 18) and match["reasons"][0]["reason"] == "guardrail:G-VEH-TITLE"
    assert out["decided"] == 0 and sum(s["stopped"] for s in out["stages"]) == out["total"]
    assert "20 past items" in out["text"] and "G-VEH-TITLE" in out["text"]


# ---------------------------------------------------------------- UC-04
def _entry(user: str = "developer") -> dict[str, Any]:
    """The connector entry: the document imported (a draft), saved as tested for the org and released by someone else."""
    doc = copy.deepcopy(BODY_SHOP_DOC)
    body = {
        "name": "Legacy body-shop system",
        "system_type": "uc_bodyshop",
        "vendor_family": "Legacy",
        "document": doc,
        "base_url": BASE,
    }
    out = ok(call("registry.importSpec", body, user))
    assert out["needs_fixes"] is False and out["checks"] == [] and [r["name"] for r in out["resources"]] == ["repairs"]
    entry, _ = imported_entry(body)
    assert entry["kind"] == "from_spec" and entry["auth_methods"] == ["api_key"] and entry["system_type"] == "uc_bodyshop"
    saved = ok(call("registry.saveEntry", {"entry": entry | {"status": "tested", "org_unit_id": ORG}}, user))
    ok(call("registry.release", {"id": saved["id"], "version": saved["version"]}, "admin"))
    return saved


def _connect(user: str = "developer") -> str:
    e = _entry(user)
    body = {"registry_id": e["id"], "version": e["version"], "name": "Legacy body-shop system", "org_unit_id": ORG,
            "system_owner": "approver", "test_base_url": BASE, "auth": "api_key", "secret": KEY}  # fmt: skip
    return ok(call("connection.create", body, user))["source_id"]


def _env(sid: str) -> str | None:
    with engine.connect() as c:
        return c.execute(text("SELECT environment FROM source_connection WHERE source_id = :i"), {"i": sid}).scalar()


def test_uc_04_connector_from_spec_needs_owner(body_shop):
    sid = _connect()
    assert _env(sid) == "test"
    with SessionLocal() as s:
        conn = connection.connection_for(s, sid)
        assert conn is not None and conn.registry_id and conn.base_url == BASE
        assert [(r["name"], r["path"], r["id_field"], r["data_selector"]) for r in conn.resources] == [
            ("repairs", "/repairs", "repairId", "repairs")
        ]
        assert conn.paging["type"] == "page_number" and conn.paging["max_size"] == 100
        row = s.execute(
            text("SELECT kind, status, system_type FROM adapter_registry WHERE id = :i"), {"i": conn.registry_id}
        ).first()
        assert row is not None and tuple(row)[:1] == ("from_spec",) and row.system_type == "uc_bodyshop"
        assert s.execute(text("SELECT count(*) FROM source_secret WHERE source_id = :i"), {"i": sid}).scalar_one() == 1
    # the secret is never shown again
    assert KEY not in json.dumps(call("connection.approvals", {"source_id": sid}, "developer"))
    rid = ok(call("connection.requestOwner", {"source_id": sid, "environment": "production", "access": "read"}, "developer"))[
        "id"
    ]
    # an agent's approval is refused whatever it says, and so is the maker's
    assert forbidden("connection.ownerApprove")
    for confirmed in (False, True):
        with SessionLocal() as s:
            pctx = load_context(s)
            ctx = CallContext(
                actor=Actor(account=policy.account("approver", pctx), ctx=pctx),
                session=s,
                preparer="integration-assistant",
                confirmed=confirmed,
            )
            r = invoke("connection.ownerApprove", {"id": rid}, ctx)
            s.rollback()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    assert "Maker-checker" in refused(call("connection.ownerApprove", {"id": rid}, "developer"), "conflict")
    assert _env(sid) == "test"
    # discovery samples 500 records and proposes the two mappings
    found = ok(call("connection.discover", {"source_id": sid}, "developer"))
    assert found["counts"] == {"repairs": 500}
    assert ok(call("connection.ownerApprove", {"id": rid}, "approver"))["status"] == "approved"
    rows = _suggest(sid)
    area, day = rows["damageArea"], rows["repairDate"]
    assert (area["target"], area["resource"]) == ("condition.damage_history", "repairs") and area["rule"] == "list"
    assert day["target"] == "condition.damage_repair_date" and day["rule"] == "date"
    assert area["band"] != "none" and day["band"] != "none" and area["decision"] is None
    assert rows["vin"]["target"] is None or rows["vin"]["band"] != "pre_ticked"  # a key is a person's choice


def test_uc_04_cases_say_not_connected(body_shop):
    car = uc.open_car(1)
    case = client.get(f"/api/screens/case/{car['id']}", headers=h("planner-a")).json()
    assert case["notConnected"] == [NOTE]
    assert (
        client.get("/api/screens/case/RT-1048", headers=h("admin")).json()["notConnected"] == []
    )  # the industrial demo is unchanged
    sid = _connect()
    rid = ok(call("connection.requestOwner", {"source_id": sid, "environment": "production", "access": "read"}, "developer"))[
        "id"
    ]
    ok(call("connection.ownerApprove", {"id": rid}, "approver"))
    ok(call("connection.discover", {"source_id": sid}, "developer"))
    screen = lambda: client.get(f"/api/screens/case/{car['id']}", headers=h("planner-a")).json()["notConnected"]  # noqa: E731
    assert screen() == [NOTE]  # a test connection is not live
    ok(call("mapping.apply", {"source_id": sid, "rows": [
        {"src": "vin", "target": "condition.key", "rule": f"prefix:{ORG}", "resource": "repairs"},
        {"src": "damageArea", "target": "condition.damage_history", "rule": "list", "resource": "repairs"},
        {"src": "repairDate", "target": "condition.damage_repair_date", "rule": "date", "resource": "repairs"},
    ]}, "developer"))  # fmt: skip
    assert screen() == [NOTE]  # and a mapping is not a connection
    ok(call("connection.promote", {"source_id": sid, "secret": KEY}, "developer"))
    assert screen() == []  # live: the note is gone
    run = sync.run_sync(sid)
    assert run["status"] == "ok" and run["records_read"] == 600, run
    with SessionLocal() as s:
        rec = canonical.get(s, "condition", vin_key(ORG, uc.vin(1)))
    assert rec is not None and rec["data"]["damage_history"] and isinstance(rec["data"]["damage_history"], list)
    assert rec["provenance"]["damage_history"][0]["source_id"] == sid and "damage_repair_date" in rec["data"]
    assert rec["provenance"]["damage_history"][0]["resource"] == "repairs"
