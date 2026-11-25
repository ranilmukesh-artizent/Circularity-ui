"""P9-8.11 (story X-10): the directory pull sync, and `access.syncDirectory` with and without a directory source.

The directory is an in-process fake (tests/scim_helpers.py FakeDirectory) and the sign-in provider is tests/oidc_fake.py:
nothing here calls source-sim. The lead runs the same flows against the real mock after the merge.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from di.core import policy, state
from di.core.auth import load_context
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services import directory_sync, oidc
from tests import helpers
from tests.oidc_fake import CLIENT_ID, CLIENT_SECRET, INTERNAL, ISSUER, REDIRECT, FakeIdp
from tests.scim_helpers import JOINER, PLANNER_B, FakeDirectory, clean


@pytest.fixture(autouse=True)
def fresh():
    clean()
    yield
    clean()


@pytest.fixture
def directory(monkeypatch):
    d = FakeDirectory()
    d.connect(monkeypatch)
    return d


@pytest.fixture
def idp(monkeypatch):
    f = FakeIdp()
    st = get_settings()
    for k, v in {"oidc_issuer": ISSUER, "oidc_internal_url": INTERNAL, "oidc_client_id": CLIENT_ID,
                 "oidc_redirect_uri": REDIRECT, "oidc_groups_claim": "groups"}.items():  # fmt: skip
        monkeypatch.setattr(st, k, v)
    monkeypatch.setattr(st, "oidc_client_secret", SecretStr(CLIENT_SECRET))
    monkeypatch.setattr(oidc, "HTTP_TRANSPORT", f.transport())
    return f


def _test_user(email: str) -> dict:
    return helpers.call("access.testUser", {"email": email}, "admin")["output"]


def _sync() -> dict:
    out = helpers.call("access.syncDirectory", {}, "admin")
    assert out["ok"], out
    return out["output"]


def _sync_text() -> str:
    with SessionLocal() as s:
        notes = [e["note"] for e in state.items(s, "events", newest_first=True) if e.get("type") == "directory.synced"]
    return notes[0]


def _sign_in(idp: FakeIdp, email: str, groups: list[str]) -> dict:
    with SessionLocal() as s:
        url = oidc.start(s)
    code = idp.authorize(url, email, groups=groups)
    state_ = parse_qs(urlparse(url).query)["state"][0]
    r = helpers.client.get("/api/auth/oidc/callback", params={"state": state_, "code": code}, follow_redirects=False)
    sso = parse_qs(urlparse(r.headers["location"].split("#", 1)[1]).query)["sso"][0]
    out = helpers.client.post("/api/auth/oidc/exchange", json={"code": sso})
    assert out.status_code == 200, out.text
    return out.json()


def test_x_10_joiner_access_on_next_sync(directory, idp):
    directory.add(JOINER, [PLANNER_B])
    before = _test_user(JOINER)
    assert before["found"] is False
    out = _sync()
    assert out["joiners"] == [JOINER] and out["leavers"] == []
    after = _test_user(JOINER)
    assert after["found"] is True and after["role"] == "Planner" and after["tenants"] == ["Customer B"]
    assert after["via_group"] == PLANNER_B and after["source"] == "directory"
    me = _sign_in(idp, JOINER, [PLANNER_B])  # the joiner can sign in through OIDC
    assert me["account"]["role"] == "Planner" and me["tenants"] == ["Customer B"]
    again = _sync()  # nothing new the second time
    assert again["joiners"] == [] and again["leavers"] == []


def test_directory_sync_text_names_joiners_leavers_and_mappings(directory):
    directory.add(JOINER, [PLANNER_B])
    _ = _sync()
    with SessionLocal() as s:
        n_users = len(state.items(s, "idp_users"))
        maps = len(load_context(s).group_map or {})
    assert _sync_text() == f"Directory sync: {n_users} users, 1 joiners, 0 leavers, {maps} mappings"


def test_directory_sync_pages_through_users_and_groups(directory):
    _ = _sync()
    assert directory.paths.count("/directory/api/users") >= 6  # 13 users, two to a page
    assert "/directory/api/groups" in directory.paths


def test_directory_sync_deactivates_a_leaver(directory):
    directory.add(JOINER, [PLANNER_B])
    _ = _sync()
    joiner = next(u for u in _users() if u["email"] == JOINER)
    directory.remove("u-joiner-one")
    out = _sync()
    assert out["leavers"] == [JOINER] and out["joiners"] == []
    assert not [u for u in _users() if u["email"] == JOINER]
    with SessionLocal() as s:
        assert policy.account(joiner["id"], load_context(s)) is not None  # deactivated, never deleted
        assert state.get(s, "account_revoked", joiner["id"]) is not None


def test_directory_sync_never_deactivates_admin(directory):
    directory.remove("admin")
    out = _sync()
    assert out["leavers"] == []
    assert [u for u in _users() if u["id"] == "admin"]


def test_directory_sync_leaves_users_it_never_saw_alone(directory):
    with SessionLocal() as s:  # a local user the directory has never reported: no external id, so never a leaver
        state.add(s, "idp_users", "local-1", {"id": "local-1", "email": "local@example.com", "acct": None, "role": "Planner"})
        s.commit()
    out = _sync()
    assert out["leavers"] == [] and [u for u in _users() if u["id"] == "local-1"]


def test_directory_sync_refuses_when_the_directory_is_down(directory, monkeypatch):
    import httpx

    monkeypatch.setattr(directory_sync, "HTTP_TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    out = helpers.call("access.syncDirectory", {}, "admin")
    assert out["ok"] is False and "directory" in out["error"]["message"].lower()
    assert [u for u in _users() if u["id"] == "admin"]  # nothing was deactivated on a failed read


def test_sync_directory_parity_without_directory():
    out = helpers.call("access.syncDirectory", {}, "admin")
    with SessionLocal() as s:
        n = len(state.items(s, "idp_users"))
        maps = len(load_context(s).group_map or {})
    assert out["output"] == {"users": n}
    assert _sync_text() == f"Directory sync: {n} users, {maps} mappings"


def _users() -> list[dict]:
    with SessionLocal() as s:
        return state.items(s, "idp_users")


def test_sync_directory_journal_has_no_secret(directory):
    _ = _sync()
    with SessionLocal() as s:
        rows = s.execute(text("SELECT input::text AS i FROM action_journal WHERE action LIKE 'access.scim%'")).all()
    assert rows and not [r for r in rows if "Bearer" in r.i]
