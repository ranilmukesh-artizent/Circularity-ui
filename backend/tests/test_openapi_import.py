"""P9-8.6 (story: enabler, 01 section 2 "a connector built once from an API specification"; D 1.2 importer 1): the OpenAPI
importer and the static checks of a spec, and the `registry.importSpec` action that saves a draft.

The documents are fixtures (tests/fixtures/openapi), laid out as FastAPI exports its /openapi.json; no source-sim is
called: the generic-mock equivalence test reads through an in-process fake (httpx.MockTransport).
"""
# ruff: noqa: E501 - long lines in the call bodies

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from di.connectors.configured import ConfiguredAdapter
from di.connectors.connection import Connection
from di.connectors.http import Auth, SourceClient
from di.connectors.openapi_import import import_openapi
from di.connectors.spec_check import check_spec
from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents.forbidden import forbidden
from tests.helpers import call

FIX = Path(__file__).parent / "fixtures" / "openapi"


def doc(name: str) -> dict[str, Any]:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def clean_registry():
    def wipe() -> None:
        with engine.begin() as c:
            c.execute(text("DELETE FROM adapter_registry WHERE id LIKE 'p98-%'"))

    wipe()
    yield
    wipe()


def test_openapi_import_generic_mock():
    r = import_openapi(doc("generic_mock"), "http://source-sim:8100/mock")
    assert [x["name"] for x in r.resources] == ["parts", "orders"]  # one per list path; the by-id read is not a resource
    assert [x["path"] for x in r.resources] == ["/parts", "/orders"]  # relative to the connection's base URL
    assert [x["id_field"] for x in r.resources] == ["part_id", "order_id"]
    assert all(x["data_selector"] == "items" for x in r.resources)
    p = r.spec["paging"]
    assert p["type"] == "offset" and (p["limit_param"], p["offset_param"], p["next_key"], p["total_key"]) == (
        "limit",
        "offset",
        "next",
        "total",
    )
    assert p["max_size"] == 200
    assert r.spec["auth_kind"] == "none" and r.auth_methods == ["none"]
    assert check_spec(r.spec, "source-sim") == []


def test_openapi_import_generic_mock_reads_like_the_hand_written_spec():
    """The imported spec and the hand-written one (what source-sim's generic mock is configured with) read the same records."""
    imported = import_openapi(doc("generic_mock"), "http://source-sim:8100/mock").spec
    by_hand = {
        "resources": [{"name": "parts", "path": "/parts", "id_field": "part_id"}],
        "paging": {
            "style": "offset",
            "limit_param": "limit",
            "offset_param": "offset",
            "items_key": "items",
            "next_key": "next",
            "total_key": "total",
            "max_size": 200,
        },
    }
    records = [{"part_id": f"P{n:03d}", "qty": n} for n in range(450)]

    def handler(req: httpx.Request) -> httpx.Response:
        limit, offset = int(req.url.params["limit"]), int(req.url.params.get("offset", 0))
        nxt = offset + limit if offset + limit < len(records) else None
        return httpx.Response(200, json={"items": records[offset : offset + limit], "next": nxt, "total": len(records)})

    def read(spec: dict[str, Any]) -> list[dict[str, Any]]:
        conn = Connection("fake", "http://fake.test/mock", "rest", "none", {}, spec["paging"], spec["resources"][:1])
        with SessionLocal() as s:
            c = SourceClient("fake", conn.base_url, Auth(), s)
            c.http = httpx.Client(transport=httpx.MockTransport(handler))
            try:
                return [row for row, _ in ConfiguredAdapter(conn).pages(c, conn.resources[0], None)]
            finally:
                c.close()
                s.rollback()

    assert read(imported) == read(by_hand) == records


def test_openapi_import_link_header():
    r = import_openapi(doc("link_header"))
    assert r.spec["paging"]["type"] == "header_link"
    assert r.spec["paging"]["limit_param"] == "per_page"
    assert r.resources == [{"name": "items", "path": "/items", "id_field": "id", "data_selector": "$"}]
    assert any("api.example.com/v2" in n for n in r.notes)  # the server the document names is reported, not stored as a host


def test_openapi_import_body_next_link_and_dependent_resource():
    r = import_openapi(doc("body_next_api_key"))
    assert r.spec["paging"]["type"] == "json_link" and r.spec["paging"]["next_url_path"] == "meta.next_url"
    assets, events = r.resources
    assert assets["data_selector"] == "data" and assets["id_field"] == "id"
    assert events["path"] == "/v1/assets/{resources.assets.id}/events" and events["include_from_parent"] == ["id"]
    assert events["id_field"] == "event_id"


def test_openapi_import_api_key_scheme():
    r = import_openapi(doc("body_next_api_key"))
    assert r.auth_methods == ["api_key"]
    assert r.spec["auth_kind"] == "api_key" and r.spec["auth_params"] == {"header": "x-api-key"}
    assert check_spec(r.spec, "api.example.com") == []  # no key value anywhere in the spec


@pytest.mark.parametrize(
    ("scheme", "kind", "params"),
    [
        ({"type": "http", "scheme": "bearer"}, "bearer", {}),
        ({"type": "http", "scheme": "basic"}, "basic", {}),
        (
            {"type": "oauth2", "flows": {"clientCredentials": {"tokenUrl": "https://api.example.com/oauth/token", "scopes": {}}}},
            "oauth_cc",
            {"token_path": "/oauth/token"},
        ),
    ],
)
def test_openapi_import_auth_schemes(scheme, kind, params):
    d = doc("body_next_api_key")
    d["components"]["securitySchemes"] = {"S": scheme}
    d["security"] = [{"S": []}]
    r = import_openapi(d)
    assert (r.spec["auth_kind"], r.auth_methods) == (kind, [kind])
    assert (r.spec.get("auth_params") or {}) == params
    assert check_spec(r.spec, "api.example.com") == []


def test_openapi_import_unsupported_listed():
    r = import_openapi(doc("link_header"))
    text_ = " ".join(r.unsupported)
    assert "createItem" in text_ and "exportXml" in text_  # a write, and an XML-only response
    assert "XML" in text_ or "application/xml" in text_
    assert [x["name"] for x in r.resources] == ["items"]


def test_openapi_import_refuses_what_is_not_openapi():
    with pytest.raises(ValueError, match="OpenAPI"):
        import_openapi({"swagger": "2.0", "paths": {}})
    with pytest.raises(ValueError, match="paths"):
        import_openapi({"openapi": "3.1.0"})


def test_spec_check_refuses_other_host():
    spec = import_openapi(doc("link_header")).spec
    spec["resources"][0]["path"] = "https://evil.example.net/items"
    errs = check_spec(spec, "api.example.com")
    assert any("evil.example.net" in e.message and e.field == "resources[0].path" for e in errs)


def test_spec_check_refuses_secret_in_spec():
    spec = import_openapi(doc("body_next_api_key")).spec
    spec["auth_params"]["api_key"] = "abc-very-secret"
    errs = check_spec(spec, "api.example.com")
    assert any(e.field == "auth_params.api_key" for e in errs)
    assert "abc-very-secret" not in json.dumps([(e.field, e.message) for e in errs])  # the value is never echoed


def test_spec_check_reads_only_and_paging_ends_and_ids_present():
    spec = copy.deepcopy(import_openapi(doc("generic_mock"), "http://source-sim:8100/mock").spec)
    spec["resources"][0]["method"] = "POST"
    del spec["resources"][1]["id_field"]
    del spec["resources"][1]["data_selector"]
    spec["paging"].pop("next_key")
    spec["paging"].pop("total_key")
    fields = {e.field for e in check_spec(spec, "source-sim")}
    assert {"resources[0].method", "resources[1].id_field", "resources[1].data_selector", "paging"} <= fields


# ---------------------------------------------------------------- registry.importSpec
def _import(document: Any, user: str = "developer", **extra: Any) -> dict[str, Any]:
    return call(
        "registry.importSpec",
        {"name": "p98 Items API", "system_type": "erp", "vendor_family": "Items", "document": document, **extra},
        user,
    )


def test_import_spec_saves_a_draft_with_notes_and_checks(clean_registry):
    r = _import(json.dumps(doc("link_header")), base_url="https://api.example.com/v2")
    assert r["ok"], r
    out = r["output"]
    assert out["id"] == "p98-items-api" and out["status"] == "draft" and out["needs_fixes"] is False and out["checks"] == []
    assert [x["name"] for x in out["resources"]] == ["items"] and out["unsupported"]
    entry = next(
        e for e in call("registry.list", {"kind": "from_spec"}, "developer")["output"]["entries"] if e["id"] == out["id"]
    )
    assert entry["status"] == "draft" and entry["kind"] == "from_spec" and entry["auth_methods"] == ["none"]
    assert entry["spec"]["paging"]["type"] == "header_link" and entry["spec"]["import"]["unsupported"]


def test_import_spec_with_check_errors_is_saved_marked_needs_fixes(clean_registry):
    d = doc("link_header")
    d["components"]["schemas"]["Item"]["properties"] = {"name": {"type": "string"}}  # no id field to find
    r = _import(d)
    assert r["ok"], r
    out = r["output"]
    assert out["needs_fixes"] is True and any(c["field"] == "resources[0].id_field" for c in out["checks"])
    assert out["status"] == "draft"


def test_import_spec_refuses_an_unreadable_document(clean_registry):
    r = _import("this is not an api description")
    assert not r["ok"] and r["error"]["code"] == "validation_error"
    r = _import({"swagger": "2.0", "paths": {}})
    assert not r["ok"] and "OpenAPI 3" in r["error"]["message"]


def test_import_spec_is_a_draft_agents_may_prepare(clean_registry):
    assert not forbidden("registry.importSpec")
    with SessionLocal() as s:
        pctx = load_context(s)
        ctx = CallContext(actor=Actor(account=policy.account("developer", pctx), ctx=pctx), session=s, preparer="assembler")
        r = invoke(
            "registry.importSpec",
            {"name": "p98 Items API", "system_type": "erp", "vendor_family": "Items", "document": doc("link_header")},
            ctx,
        )
        s.commit()
    assert r["ok"] is True or r["error"]["code"] == "held", r
