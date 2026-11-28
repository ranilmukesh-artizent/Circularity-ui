"""P9-8.11 (story X-10): SCIM 2.0 provisioning (RFC 7643 schemas, RFC 7644 protocol) into the access actions.

The directory is the caller here, so nothing is faked beyond the bearer token. Each write is an action run as the system
actor; the actions are named access.scimUpsertUser, access.scimDeactivateUser and access.scimPatchGroup.
"""

import pytest
from sqlalchemy import text

from di.core import policy, state
from di.core.auth import issue_token, load_context
from di.core.db import SessionLocal
from di.services.agents.forbidden import forbidden
from tests import helpers
from tests.scim_helpers import BEARER, JOINER, PLANNER_B, PLANNER_C, TOKEN, clean, set_token

USER = "urn:ietf:params:scim:schemas:core:2.0:User"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"


@pytest.fixture(autouse=True)
def fresh():
    clean()
    set_token()
    yield
    clean()


def _new(email: str = JOINER, group: str = PLANNER_C, **extra) -> dict:
    return {"schemas": [USER], "externalId": "ext-" + email, "userName": email, "displayName": "Joiner One",
            "emails": [{"value": email, "primary": True}], "active": True,
            "groups": [{"value": group, "display": group}], **extra}  # fmt: skip


def _post(body: dict, headers=BEARER):
    return helpers.client.post("/scim/v2/Users", json=body, headers=headers)


def _waiting(req_id: str, assigned_to: str) -> dict:
    """A tenant request waiting for `assigned_to` to decide it."""
    return {"id": req_id, "kind": "tenant", "status": "pending", "by": "x", "byId": "planner-b", "at": "x",
            "tenant": "Customer A", "reason": "r", "assignedTo": assigned_to}  # fmt: skip


def _account(account_id: str) -> policy.Account | None:
    with SessionLocal() as s:
        return policy.account(account_id, load_context(s))


def _token_of(account_id: str) -> dict:
    acct = _account(account_id)
    assert acct is not None
    return {"Authorization": "Bearer " + issue_token(acct)[0]}


def test_x_10_scim_create_user_provisions():
    r = _post(_new())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["userName"] == JOINER and body["active"] is True and body["meta"]["resourceType"] == "User"
    assert r.headers["location"].endswith("/scim/v2/Users/" + body["id"])
    assert r.headers["content-type"].startswith("application/scim+json")
    acct = _account(body["id"])
    assert acct is not None and acct.role == "Planner" and acct.tenant == "Customer C"
    assert [g["display"] for g in body["groups"]] == [PLANNER_C]
    again = _post(_new())  # the same userName: SCIM 409 uniqueness
    assert again.status_code == 409 and again.json()["scimType"] == "uniqueness"


def test_scim_unmapped_group_gives_a_listed_user_and_no_account():
    r = _post(_new(group="some-other-group"))
    assert r.status_code == 201
    with SessionLocal() as s:
        assert not [a for a in state.items(s, "accounts") if a["id"].startswith("sso-")]
        assert [u for u in state.items(s, "idp_users") if u["email"] == JOINER and u["acct"] is None]


def test_scim_never_gives_admin():
    with SessionLocal() as s:
        assert "Admin" not in policy.idp_roles() and policy.group_role("circ-admins", load_context(s)) is None
    r = _post(_new(group="circ-admins"))
    assert r.status_code == 201 and _account(r.json()["id"]) is None


def test_x_10_scim_deactivate_removes_access():
    uid = _post(_new()).json()["id"]
    token = _token_of(uid)
    assert helpers.client.get("/api/auth/me", headers=token).status_code == 200
    with SessionLocal() as s:  # a live grant, and a request waiting for them with a delegate set
        s.execute(
            text("INSERT INTO tenant_grant (account_id, tenant, granted_by) VALUES (:a, 'Customer A', 'admin')"), {"a": uid}
        )
        idp = state.need(s, "access_settings", "idp", for_update=True)
        idp["ooo"] = [{"email": "approver@example.com", "from": "2026-10-20", "until": "2026-10-31"}]
        state.put(s, "access_settings", "idp", idp)
        state.put(s, "requests", "REQ-999", _waiting("REQ-999", uid))
        s.commit()
    patch = {"schemas": [PATCH], "Operations": [{"op": "replace", "path": "active", "value": False}]}
    r = helpers.client.patch(f"/scim/v2/Users/{uid}", json=patch, headers=BEARER)
    assert r.status_code == 200 and r.json()["active"] is False
    assert helpers.client.get("/api/auth/me", headers=token).status_code == 401  # the existing JWT
    with SessionLocal() as s:
        grant = s.execute(text("SELECT revoked_at FROM tenant_grant WHERE account_id = :a"), {"a": uid}).one()
        req = state.need(s, "requests", "REQ-999")
        users = [u for u in state.items(s, "idp_users") if u["id"] == uid]
    assert grant.revoked_at is not None and req["assignedTo"] == "approver" and req["status"] == "pending"
    assert not users and _account(uid) is not None  # deactivated, never deleted
    assert helpers.client.get(f"/scim/v2/Users/{uid}", headers=BEARER).json()["active"] is False


def test_scim_deactivate_without_a_delegate_moves_requests_to_the_approver_role():
    uid = _post(_new()).json()["id"]
    with SessionLocal() as s:
        state.put(s, "requests", "REQ-998", _waiting("REQ-998", uid))
        s.commit()
    r = helpers.client.delete(f"/scim/v2/Users/{uid}", headers=BEARER)  # DELETE deactivates; nothing is removed
    assert r.status_code == 204
    with SessionLocal() as s:
        req = state.need(s, "requests", "REQ-998")
    assert req["assignedTo"] is None and req["assignedRole"] == "Approver"
    assert _account(uid) is not None


def test_scim_deactivate_refuses_admin():
    r = helpers.client.patch(
        "/scim/v2/Users/admin",
        json={"schemas": [PATCH], "Operations": [{"op": "replace", "value": {"active": False}}]},
        headers=BEARER,
    )
    assert r.status_code == 409 and r.json()["schemas"] == [ERROR]
    assert _account("admin") is not None


def test_scim_patch_group_adds_and_removes_members():
    uid = _post(_new(group="some-other-group")).json()["id"]
    assert _account(uid) is None
    ops = {"schemas": [PATCH], "Operations": [{"op": "add", "path": "members", "value": [{"value": uid}]}]}
    r = helpers.client.patch(f"/scim/v2/Groups/{PLANNER_B}", json=ops, headers=BEARER)
    assert r.status_code == 200 and uid in [m["value"] for m in r.json()["members"]]
    acct = _account(uid)
    assert acct is not None and acct.tenant == "Customer B"
    drop = {"schemas": [PATCH], "Operations": [{"op": "remove", "path": f'members[value eq "{uid}"]'}]}
    r = helpers.client.patch(f"/scim/v2/Groups/{PLANNER_B}", json=drop, headers=BEARER)
    assert r.status_code == 200 and uid not in [m["value"] for m in r.json()["members"]]


def test_scim_groups_are_read_from_the_group_map():
    r = helpers.client.get("/scim/v2/Groups", headers=BEARER)
    names = [g["displayName"] for g in r.json()["Resources"]]
    assert r.status_code == 200 and PLANNER_B in names and r.json()["schemas"] == [LIST]
    assert helpers.client.get(f"/scim/v2/Groups/{PLANNER_B}", headers=BEARER).json()["displayName"] == PLANNER_B
    assert (
        helpers.client.post("/scim/v2/Groups", json={"displayName": "x"}, headers=BEARER).status_code == 501
    )  # groups are the map's
    assert helpers.client.get("/scim/v2/Groups/nope", headers=BEARER).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic " + TOKEN}])
def test_scim_requires_token(headers):
    for path in ("/scim/v2/Users", "/scim/v2/Groups", "/scim/v2/ServiceProviderConfig"):
        r = helpers.client.get(path, headers=headers)
        assert r.status_code == 401 and r.json()["schemas"] == [ERROR] and r.json()["status"] == "401"
        assert r.headers["content-type"].startswith("application/scim+json")
    assert _post(_new(), headers).status_code == 401
    with SessionLocal() as s:
        assert not [a for a in state.items(s, "accounts") if a["id"].startswith("sso-")]


def test_scim_without_a_stored_token_refuses_everyone():
    with SessionLocal() as s:
        s.execute(text("DELETE FROM source_secret WHERE source_id = 'idp'"))
        s.commit()
    assert helpers.client.get("/scim/v2/Users", headers=BEARER).status_code == 401
    assert helpers.client.get("/scim/v2/Users", headers={"Authorization": "Bearer "}).status_code == 401


def test_scim_token_is_never_in_the_journal():
    uid = _post(_new()).json()["id"]
    helpers.client.get("/scim/v2/Users", headers={"Authorization": "Bearer " + TOKEN + "x"})
    helpers.client.delete(f"/scim/v2/Users/{uid}", headers=BEARER)
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT input::text AS i, output_ref::text AS o FROM action_journal WHERE action LIKE 'access.scim%'")
        ).all()
        events = s.execute(text("SELECT payload::text AS p FROM domain_event WHERE type LIKE 'action.access.scim%'")).all()
        notes = [str(e) for e in state.items(s, "events")]
    assert rows and not [x for r in rows for x in (r.i, r.o) if TOKEN in x]
    assert not [e for e in events if TOKEN in e.p] and not [n for n in notes if TOKEN in n]


def test_scim_service_provider_config():
    r = helpers.client.get("/scim/v2/ServiceProviderConfig", headers=BEARER)
    cfg = r.json()
    assert r.status_code == 200 and cfg["patch"]["supported"] is True
    assert cfg["filter"] == {"supported": True, "maxResults": 200}
    assert cfg["bulk"]["supported"] is False and cfg["changePassword"]["supported"] is False
    assert cfg["authenticationSchemes"][0]["type"] == "oauthbearertoken"
    assert helpers.client.get("/scim/v2/Schemas", headers=BEARER).json()["totalResults"] >= 2
    kinds = [x["name"] for x in helpers.client.get("/scim/v2/ResourceTypes", headers=BEARER).json()["Resources"]]
    assert kinds == ["User", "Group"]


def test_scim_filter_eq_email():
    _post(_new())
    _post(_new("other.joiner@example.com", PLANNER_B))
    r = helpers.client.get("/scim/v2/Users", params={"filter": f'emails[value eq "{JOINER}"]'}, headers=BEARER)
    assert r.status_code == 200 and r.json()["totalResults"] == 1
    assert r.json()["Resources"][0]["userName"] == JOINER
    by_name = helpers.client.get("/scim/v2/Users", params={"filter": f'userName eq "{JOINER.upper()}"'}, headers=BEARER)
    assert by_name.json()["totalResults"] == 1  # userName is case-insensitive (RFC 7643 4.1.1)
    bad = helpers.client.get("/scim/v2/Users", params={"filter": "emails co x"}, headers=BEARER)
    assert bad.status_code == 400 and bad.json()["scimType"] == "invalidFilter"


def test_scim_list_pages_with_start_index_and_count():
    r = helpers.client.get("/scim/v2/Users", params={"startIndex": 2, "count": 3}, headers=BEARER)
    j = r.json()
    assert j["startIndex"] == 2 and j["itemsPerPage"] == 3 and len(j["Resources"]) == 3 and j["totalResults"] >= 12
    assert helpers.client.get("/scim/v2/Users", params={"count": 0}, headers=BEARER).json()["Resources"] == []


def test_scim_rejects_bad_bodies_with_scim_errors():
    r = helpers.client.post("/scim/v2/Users", content=b"{not json", headers=BEARER | {"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["scimType"] == "invalidSyntax"
    r = _post({"schemas": [USER], "userName": "no-email"})  # a userName that is not an email and no emails
    assert r.status_code == 400 and r.json()["scimType"] == "invalidValue"
    assert helpers.client.get("/scim/v2/Users/missing", headers=BEARER).status_code == 404


def test_scim_actions_are_system_only_and_never_an_agents():
    for action in ("access.scimUpsertUser", "access.scimDeactivateUser", "access.scimPatchGroup"):
        assert forbidden(action)
        out = helpers.call(action, {"external_id": "x", "email": "a@example.com", "name": "n", "active": True, "groups": [],
                                    "group_id": "g"}, "admin")  # fmt: skip
        assert out["ok"] is False and out["error"]["code"] == "out_of_scope"


def test_x_10_scim_email_change_of_an_admin_is_ignored():
    """Review P9-8.23 F1: SCIM never moves the Admin account's sign-in email, so OIDC with the new email is not Admin."""
    from di.services import oidc

    with SessionLocal() as s:
        old = next(u["email"] for u in state.items(s, "idp_users") if u.get("acct") == "admin")
    body = {"schemas": [USER], "userName": "evil@example.com", "emails": [{"value": "evil@example.com", "primary": True}],
            "displayName": "Admin", "active": True}  # fmt: skip
    r = helpers.client.put("/scim/v2/Users/admin", json=body, headers=BEARER)
    assert r.status_code == 200, r.text
    with SessionLocal() as s:
        assert next(u["email"] for u in state.items(s, "idp_users") if u.get("acct") == "admin") == old
        got = oidc.resolve_directory_user(s, "evil@example.com", [])
        assert got is None or got.role != "Admin"
        back = oidc.resolve_directory_user(s, old, [])
        assert back is not None and back.role == "Admin"
        notes = s.execute(text("SELECT data->>'note' FROM state_item WHERE collection = 'events'")).scalars().all()
    assert any("SCIM email change ignored for an Admin account" in (n or "") for n in notes)
