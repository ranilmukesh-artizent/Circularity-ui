"""P9-8.9 (story X-10): OIDC sign-in beside the demo sign-in, against an in-process provider (tests/oidc_fake.py).

The provider is a fake: nothing here calls source-sim. The lead's smoke runs the same flow against the directory mock.
"""

from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from sqlalchemy import text

from di.core import policy, state
from di.core.auth import load_context
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services import oidc
from di.services.actions import pipeline
from tests import helpers
from tests.oidc_fake import CLIENT_ID, CLIENT_SECRET, INTERNAL, ISSUER, REDIRECT, FakeIdp

ENDED = "Your session has ended. Sign in again."
PLANNER_B_GROUP = "circ-planners-customer-b"


@pytest.fixture
def idp(monkeypatch):
    f = FakeIdp()
    st = get_settings()
    for k, v in {"oidc_issuer": ISSUER, "oidc_internal_url": INTERNAL, "oidc_client_id": CLIENT_ID,
                 "oidc_redirect_uri": REDIRECT, "oidc_groups_claim": "groups"}.items():  # fmt: skip
        monkeypatch.setattr(st, k, v)
    from pydantic import SecretStr

    monkeypatch.setattr(st, "oidc_client_secret", SecretStr(CLIENT_SECRET))
    monkeypatch.setattr(oidc, "HTTP_TRANSPORT", f.transport())
    yield f
    _clean()


def _clean() -> None:
    """Remove what a joiner's sign-in adds (the accounts and directory users of this test), so parity tests stay green."""
    with SessionLocal() as s:
        for coll in ("accounts", "idp_users"):
            for item in state.items(s, coll):
                if str(item["id"]).startswith("sso-"):
                    state.delete(s, coll, item["id"])
        journal = "SELECT seq FROM action_journal WHERE action = 'access.provisionUser'"
        s.execute(text(f"DELETE FROM domain_event WHERE seq IN ({journal})"))  # noqa: S608 - a constant
        s.execute(text("DELETE FROM action_journal WHERE action = 'access.provisionUser'"))
        s.execute(text("DELETE FROM state_item WHERE collection = 'events' AND data->>'type' = 'user.provisioned'"))
        s.execute(text("DELETE FROM oidc_login"))
        s.commit()


def _start() -> str:
    with SessionLocal() as s:
        return oidc.start(s)


def _callback(idp: FakeIdp, email: str, groups: list[str], **overrides):
    url = _start()
    code = idp.authorize(url, email, groups=groups, **overrides)
    state_ = parse_qs(urlparse(url).query)["state"][0]
    return helpers.client.get("/api/auth/oidc/callback", params={"state": state_, "code": code}, follow_redirects=False), state_


def _sso_code(r) -> str:
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"].split("#", 1)[1]).query)["sso"][0]


def _sign_in(idp: FakeIdp, email: str, groups: list[str]) -> dict:
    r, _ = _callback(idp, email, groups)
    out = helpers.client.post("/api/auth/oidc/exchange", json={"code": _sso_code(r)})
    assert out.status_code == 200, out.text
    return out.json()


def _email(account_id: str) -> str:
    return next(u["email"] for u in policy.starting_idp_users() if u["id"] == account_id)


def test_x_10_oidc_sign_in_maps_groups(idp):
    me = _sign_in(idp, _email("planner-b"), [PLANNER_B_GROUP])
    assert me["account"]["id"] == "planner-b" and me["account"]["role"] == "Planner"
    assert me["tenants"] == ["Customer B"] and me["token_type"] == "bearer"
    headers = {"Authorization": "Bearer " + me["access_token"]}
    assert helpers.client.get("/api/auth/me", headers=headers).json()["account"]["id"] == "planner-b"
    assert set(idp.hosts) == {"idp-internal.test"}  # server to server calls use the internal address
    assert "id_token" not in me


def test_x_10_oidc_joiner_provisioned_by_group(idp):
    me = _sign_in(idp, "joiner.one@example.com", [PLANNER_B_GROUP])
    assert me["account"]["role"] == "Planner" and me["tenants"] == ["Customer B"]
    with SessionLocal() as s:
        accounts = [a for a in state.items(s, "accounts") if a["id"] == me["account"]["id"]]
        row = s.execute(text("SELECT input, role FROM action_journal WHERE action = 'access.provisionUser'")).one()
        events = [e for e in state.items(s, "events") if e.get("type") == "user.provisioned"]
    assert accounts and accounts[0]["tenant"] == "Customer B"
    assert row.input["via_group"] == PLANNER_B_GROUP and row.input["email"] == "joiner.one@example.com" and row.role == "System"
    assert events and events[0]["by"] == "directory sync"
    again = _sign_in(idp, "joiner.one@example.com", [PLANNER_B_GROUP])  # the second sign-in finds the account
    assert again["account"]["id"] == me["account"]["id"]
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM action_journal WHERE action = 'access.provisionUser'")).scalar() == 1


def test_x_10_admin_never_from_group(idp, monkeypatch):
    monkeypatch.setitem(policy.IDP_GROUPS, "admin", "circ-admins")
    r, _ = _callback(idp, "boss@example.com", ["circ-admins"])
    assert r.status_code == 302 and "sso_error" in r.headers["location"] and "sso=" not in r.headers["location"]
    assert "not mapped to a Circularity role" in unquote(r.headers["location"])
    with SessionLocal() as s:
        assert oidc.resolve_directory_user(s, "boss@example.com", ["circ-admins"]) is None
        assert not [a for a in state.items(s, "accounts") if a["id"].startswith("sso-")]


def test_x_10_unmapped_group_gives_no_account(idp):
    r, _ = _callback(idp, "nobody@example.com", ["some-other-group"])
    assert "sso_error" in r.headers["location"]
    with SessionLocal() as s:
        assert not [a for a in state.items(s, "accounts") if a["id"].startswith("sso-")]


@pytest.mark.parametrize("claim", ["nonce", "iss", "aud"])
def test_oidc_rejects_wrong_nonce_issuer_or_audience(idp, claim):
    r, _ = _callback(idp, "joiner.one@example.com", [PLANNER_B_GROUP], **{claim: "tampered"})
    assert r.status_code == 401 and r.json()["error"]["message"] == ENDED
    with SessionLocal() as s:
        assert not [a for a in state.items(s, "accounts") if a["id"].startswith("sso-")]
        assert s.execute(text("SELECT count(*) FROM oidc_login WHERE code IS NOT NULL")).scalar() == 0


def test_oidc_state_single_use_and_expiry(idp):
    r, st = _callback(idp, _email("planner-b"), [PLANNER_B_GROUP])
    assert r.status_code == 302
    again = helpers.client.get("/api/auth/oidc/callback", params={"state": st, "code": "x"}, follow_redirects=False)
    assert again.status_code == 401 and again.json()["error"]["message"] == ENDED
    url = _start()
    st2 = parse_qs(urlparse(url).query)["state"][0]
    with SessionLocal() as s:
        s.execute(text("UPDATE oidc_login SET created_at = now() - interval '11 minutes' WHERE state = :s"), {"s": st2})
        s.commit()
    code = idp.authorize(url, _email("planner-b"), groups=[PLANNER_B_GROUP])
    old = helpers.client.get("/api/auth/oidc/callback", params={"state": st2, "code": code}, follow_redirects=False)
    assert old.status_code == 401
    unknown = helpers.client.get("/api/auth/oidc/callback", params={"state": "never-issued", "code": "x"}, follow_redirects=False)
    assert unknown.status_code == 401


def test_oidc_exchange_code_is_single_use_and_expires(idp):
    r, _ = _callback(idp, _email("planner-b"), [PLANNER_B_GROUP])
    code = _sso_code(r)
    first = helpers.client.post("/api/auth/oidc/exchange", json={"code": code})
    assert first.status_code == 200
    assert helpers.client.post("/api/auth/oidc/exchange", json={"code": code}).status_code == 401
    r2, _ = _callback(idp, _email("planner-b"), [PLANNER_B_GROUP])
    code2 = _sso_code(r2)
    with SessionLocal() as s:
        s.execute(
            text("UPDATE oidc_login SET code_expires_at = :t WHERE code = :c"),
            {"t": datetime(2020, 1, 1, tzinfo=UTC), "c": code2},
        )
        s.commit()
    assert helpers.client.post("/api/auth/oidc/exchange", json={"code": code2}).status_code == 401
    assert helpers.client.post("/api/auth/oidc/exchange", json={"code": "nope"}).status_code == 401


def test_oidc_config_when_configured(idp):
    body = helpers.client.get("/api/auth/oidc/config").json()
    assert body["enabled"] is True and body["label"]
    assert CLIENT_SECRET not in str(body)
    url = _start()
    q = parse_qs(urlparse(url).query)
    assert (
        url.startswith(ISSUER + "/authorize")
        and q["code_challenge_method"] == ["S256"]
        and q["scope"] == ["openid email profile"]
    )
    assert q["redirect_uri"] == [REDIRECT]


def test_oidc_off_when_unconfigured(monkeypatch):
    st = get_settings()
    for k in ("oidc_issuer", "oidc_internal_url", "oidc_client_id", "oidc_redirect_uri"):  # the dev compose turns it on
        monkeypatch.setattr(st, k, "")
    assert helpers.client.get("/api/auth/oidc/config").json() == {"enabled": False}
    assert helpers.client.get("/api/auth/oidc/start", follow_redirects=False).status_code == 404
    assert helpers.client.get("/api/auth/oidc/callback", params={"state": "a", "code": "b"}).status_code == 404
    assert helpers.client.post("/api/auth/oidc/exchange", json={"code": "x"}).status_code == 404
    ok = helpers.client.post("/api/auth/login", json={"username": "planner.b@northfield.example", "password": "x"})
    assert ok.status_code == 200 and ok.json()["account"]["id"] == "planner-b"


def test_x_10_start_redirects_to_the_provider(idp):
    r = helpers.client.get("/api/auth/oidc/start", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith(ISSUER + "/authorize?")


def test_x_10_provision_user_is_only_for_the_system(idp):
    body = {"email": "x@example.com", "name": "X", "role": "Planner", "tenant": "Customer B", "via_group": PLANNER_B_GROUP}
    with SessionLocal() as s:
        admin = policy.account("admin")
        assert admin is not None
        for preparer in (None, "coordinator"):
            actor = pipeline.Actor(account=admin, ctx=load_context(s))
            res = pipeline.invoke("access.provisionUser", body, pipeline.CallContext(actor=actor, session=s, preparer=preparer))
            assert res["ok"] is False and res["error"]["code"] == "out_of_scope"
        assert not [a for a in state.items(s, "accounts") if a["id"].startswith("sso-")]
