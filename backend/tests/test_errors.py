"""D1: one error envelope, {"ok": false, "error": {"code", "message", ...}}, for every refusal and failure.

ApiError, FastAPI/Starlette's HTTPException (detail {code, message} or a plain string), request validation errors and
unhandled exceptions all answer with it, at their own status; the codes and messages stay what they were.
"""

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from di.core.errors import ApiError
from di.main import app
from tests.helpers import h


class _Body(BaseModel):
    name: str
    count: int


@app.get("/api/_test/errors/api-error")
def _api_error():
    raise ApiError("conflict", "Already decided.", status=409, extra={"case_id": "RT-1048"})


@app.get("/api/_test/errors/api-error-default")
def _api_error_default():
    raise ApiError("validation_error", "Enter a case.")


@app.get("/api/_test/errors/http-dict")
def _http_dict():
    raise HTTPException(403, {"code": "out_of_scope", "message": "Not for you."}, headers={"X-Probe": "1"})


@app.get("/api/_test/errors/http-string")
def _http_string():
    raise HTTPException(404, "Nothing here.")


@app.post("/api/_test/errors/validate")
def _validate(body: _Body):
    return body


@app.get("/api/_test/errors/boom")
def _boom():
    raise RuntimeError("database password is hunter2")  # must not reach the caller


client = TestClient(app, raise_server_exceptions=False)


def test_api_error_with_status_and_extra():
    r = client.get("/api/_test/errors/api-error")
    assert r.status_code == 409
    assert r.json() == {"ok": False, "error": {"code": "conflict", "message": "Already decided.", "case_id": "RT-1048"}}
    r = client.get("/api/_test/errors/api-error-default")
    assert r.status_code == 400
    assert r.json() == {"ok": False, "error": {"code": "validation_error", "message": "Enter a case."}}


def test_http_exception_with_code_and_message_keeps_both_and_its_headers():
    r = client.get("/api/_test/errors/http-dict")
    assert r.status_code == 403 and r.headers["x-probe"] == "1"
    assert r.json() == {"ok": False, "error": {"code": "out_of_scope", "message": "Not for you."}}


def test_http_exception_with_a_string_and_unknown_routes():
    r = client.get("/api/_test/errors/http-string")
    assert r.status_code == 404 and r.json() == {"ok": False, "error": {"code": "not_found", "message": "Nothing here."}}
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404 and r.json() == {"ok": False, "error": {"code": "not_found", "message": "Not Found"}}


def test_validation_error_names_the_first_bad_field():
    r = client.post("/api/_test/errors/validate", json={"name": "x"})
    assert r.status_code == 422
    assert r.json()["ok"] is False and r.json()["error"]["code"] == "validation_error"
    assert "count" in r.json()["error"]["message"]
    r = client.post("/api/auth/login", json={"password": "x"})
    assert r.status_code == 422 and "username" in r.json()["error"]["message"]


def test_an_unhandled_exception_is_a_generic_500():
    r = client.get("/api/_test/errors/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False and body["error"]["code"] == "internal_error"
    assert "hunter2" not in r.text


def test_sign_in_refusals_keep_their_codes_messages_and_challenge():
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401 and r.json()["error"] == {
        "code": "unknown_account",
        "message": "We could not find that account. Check the email or user ID.",
    }
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert r.json() == {"ok": False, "error": {"code": "unauthenticated", "message": "Sign in first."}}


def test_source_endpoints_refuse_roles_without_the_pages():
    planner = h("planner.a")  # no integration pages
    for path in ("/api/sources", "/api/sources/erp"):
        r = client.get(path, headers=planner)
        assert r.status_code == 403 and r.json()["error"] == {
            "code": "out_of_scope",
            "message": "Not available for the Planner view.",
        }, (path, r.text)
    assert client.get("/api/sources", headers=h("developer")).status_code == 200
    r = client.get("/api/canonical/asset/nope", headers=h("developer"))  # integration models, no product pages
    assert r.status_code == 404 and r.json()["error"] == {"code": "not_found", "message": "No asset nope."}
