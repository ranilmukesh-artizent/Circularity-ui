"""Plan 3 task 2: the resource registry and the generic /api/v1 router (di.resources). A test-only resource stands
in for the real ones (task 3); writes must go through pipeline.invoke with the registered action id."""

import pytest

from di.core.errors import ApiError
from di.resources import REGISTRY, Resource, register
from tests.helpers import client, h

ROWS = [{"id": f"P-{n}", "name": f"probe {n}", "kind": "a" if n % 2 else "b"} for n in range(1, 8)]
CALLS: list[tuple[str, dict]] = []


def _list(ctx, q):
    return [r for r in ROWS if not q.get("kind") or r["kind"] == q["kind"]]


def _get(ctx, rid):
    return next((r for r in ROWS if r["id"] == rid), None)


@pytest.fixture(autouse=True)
def probe(monkeypatch):
    CALLS.clear()

    def fake_invoke(action, body, ctx):
        CALLS.append((action, body))
        if body.get("name") == "boom":
            return {"ok": False, "error": {"code": "conflict", "message": "no"}}
        return {"ok": True, "output": {"id": body.get("id", "P-9"), "echo": body}}

    monkeypatch.setattr("di.resources.router.invoke", fake_invoke)
    register(
        Resource(
            name="probes", list=_list, get=_get, create="probe.make", update="probe.change", delete=None,
            fields=("name", "kind"), filters=("kind",), why_not={"delete": "Probes are kept."},
        )
    )  # fmt: skip
    register(Resource(name="readonly-probes", list=_list, get=_get, create=None, update=None, delete=None,
                      why_not={"create": "Read only."}))  # fmt: skip
    yield
    for n in ("probes", "readonly-probes", "denied"):
        REGISTRY.pop(n, None)


U = "/api/v1/probes"


def test_signed_out_is_401():
    assert client.get(U).status_code == 401


def test_list_pages_with_a_cursor():
    r = client.get(U, params={"limit": 3}, headers=h("admin"))
    assert r.status_code == 200
    b = r.json()
    assert [x["id"] for x in b["items"]] == ["P-1", "P-2", "P-3"] and b["next_cursor"] == "3"
    b2 = client.get(U, params={"limit": 3, "cursor": b["next_cursor"]}, headers=h("admin")).json()
    assert [x["id"] for x in b2["items"]] == ["P-4", "P-5", "P-6"]
    last = client.get(U, params={"limit": 3, "cursor": b2["next_cursor"]}, headers=h("admin")).json()
    assert [x["id"] for x in last["items"]] == ["P-7"] and last["next_cursor"] is None


def test_list_takes_the_resource_filters():
    b = client.get(U, params={"kind": "b"}, headers=h("admin")).json()
    assert [x["id"] for x in b["items"]] == ["P-2", "P-4", "P-6"]


def test_get_and_404():
    assert client.get(f"{U}/P-2", headers=h("admin")).json()["name"] == "probe 2"
    r = client.get(f"{U}/nope", headers=h("admin"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_an_unknown_resource_is_404():
    assert client.get("/api/v1/nothing-here", headers=h("admin")).status_code == 404


def test_create_calls_the_pipeline_with_the_action_id():
    r = client.post(U, json={"name": "x"}, headers=h("admin"))
    assert r.status_code == 201, r.text
    assert CALLS == [("probe.make", {"name": "x"})]


def test_update_passes_the_id_and_the_fields():
    r = client.patch(f"{U}/P-2", json={"name": "y"}, headers=h("admin"))
    assert r.status_code == 200, r.text
    assert CALLS == [("probe.change", {"id": "P-2", "name": "y"})]


def test_update_of_a_missing_id_is_404_and_calls_nothing():
    assert client.patch(f"{U}/nope", json={"name": "y"}, headers=h("admin")).status_code == 404
    assert CALLS == []


def test_an_unknown_field_is_422_naming_it_and_calls_nothing():
    r = client.patch(f"{U}/P-2", json={"colour": "red"}, headers=h("admin"))
    assert r.status_code == 422 and "colour" in r.json()["error"]["message"]
    r = client.post(U, json={"colour": "red"}, headers=h("admin"))
    assert r.status_code == 422 and "colour" in r.json()["error"]["message"]
    assert CALLS == []


def test_a_verb_without_an_action_is_405_with_the_reason():
    r = client.delete(f"{U}/P-2", headers=h("admin"))
    assert r.status_code == 405 and r.json()["error"] == {"code": "not_supported", "message": "Probes are kept."}
    r = client.post("/api/v1/readonly-probes", json={}, headers=h("admin"))
    assert r.status_code == 405 and r.json()["error"]["message"] == "Read only."
    r = client.patch("/api/v1/readonly-probes/P-1", json={}, headers=h("admin"))
    assert r.status_code == 405 and r.json()["error"]["code"] == "not_supported"
    assert CALLS == []


def test_a_pipeline_refusal_keeps_its_status():
    r = client.post(U, json={"name": "boom"}, headers=h("admin"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_patch_runs_the_named_action_with_the_id_under_its_own_key_and_the_row_fields():
    register(
        Resource(
            name="dispatch", list=_list, get=_get, create=None, update=None, delete="dispatch.drop", id_field="pid",
            update_actions={"rename": "dispatch.rename", "ping": "dispatch.ping"},
            id_keys={"dispatch.ping": "", "dispatch.drop": "target"}, from_row={"kind": "kind"},
        )
    )  # fmt: skip
    try:
        assert client.patch("/api/v1/dispatch/P-1", json={"action": "rename", "name": "z"}, headers=h("admin")).status_code == 200
        assert client.patch("/api/v1/dispatch/P-1", json={"action": "ping"}, headers=h("admin")).status_code == 200
        assert client.delete("/api/v1/dispatch/P-2", headers=h("admin")).status_code == 200
        assert CALLS == [
            ("dispatch.rename", {"name": "z", "kind": "a", "pid": "P-1"}),
            ("dispatch.ping", {"kind": "a"}),
            ("dispatch.drop", {"kind": "b", "target": "P-2"}),
        ]
        r = client.patch("/api/v1/dispatch/P-1", json={"action": "nope"}, headers=h("admin"))
        assert r.status_code == 422 and "ping, rename" in r.json()["error"]["message"]
        r = client.patch("/api/v1/dispatch/P-1", json={"name": "z"}, headers=h("admin"))
        assert r.status_code == 422 and "Say which action" in r.json()["error"]["message"]
        assert len(CALLS) == 3
    finally:
        REGISTRY.pop("dispatch", None)


def test_an_api_error_in_a_read_is_answered_with_its_status():
    def deny(ctx, q):
        raise ApiError("out_of_scope", "Not for you.", 403)

    register(Resource(name="denied", list=deny, get=_get, create=None, update=None, delete=None))
    r = client.get("/api/v1/denied", headers=h("admin"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
