"""P9-13.9: per-agent credentials (client credentials) and what an agent token may do (R21).

An agent token acts as its owner's account, prepared by the agent: never approves, never confirms, limited to the
agent's tools, held when the agent's autonomy is propose. Revoking the credential or deactivating the owner stops it.
"""

import base64
from datetime import UTC, datetime

import jwt
import pytest
from sqlalchemy import text

from di.core import state
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services import agent_credentials
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
EVIDENCE = {"case_id": "RT-1051"}
SCOPED = "cred-scoped"  # tools: evidence.request only
HELD = "cred-held"  # autonomy propose


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_credential"))
        s.execute(text("DELETE FROM agent_identity WHERE id IN (:a, :b)"), {"a": SCOPED, "b": HELD})
        for i, auto in ((SCOPED, "act"), (HELD, "propose")):
            s.execute(
                text("INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES (:i, :i, 'external', :t, :a)"),
                {"i": i, "t": ["evidence.request"], "a": auto},
            )
        s.commit()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_credential"))
        s.execute(text("DELETE FROM agent_identity WHERE id IN (:a, :b)"), {"a": SCOPED, "b": HELD})
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()
    starting.reset()


def issue(agent: str, owner: str = "planner-a") -> tuple[str, str]:
    with SessionLocal() as s:
        out = agent_credentials.issue(s, agent, owner)
        s.commit()
    return out["client_id"], out["client_secret"]


def token_of(agent: str, owner: str = "planner-a") -> str:
    cid, secret = issue(agent, owner)
    r = client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def bearer(tok: str, **more: str) -> dict:
    return {"Authorization": f"Bearer {tok}", **more}


def act(action: str, body: dict, tok: str, **headers: str) -> object:
    return client.post(f"/api/actions/{action}", json=body, headers=bearer(tok, **headers))


def test_agent_credential_issues_token():
    cid, secret = issue(SCOPED)
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    r = client.post("/oauth/token", data={"grant_type": "client_credentials"}, headers={"Authorization": f"Basic {basic}"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    claims = jwt.decode(
        body["access_token"], get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"], audience="di", issuer="di-api"
    )
    assert claims["sub"] == f"agent:{SCOPED}" and claims["aud"] == "di" and claims["azp"] == cid
    assert claims["own"] == "planner-a" and claims["exp"] - claims["iat"] == 900
    bad = client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": cid, "client_secret": "nope"})
    assert bad.status_code == 401 and bad.json()["error"] == "invalid_client"


def test_agent_token_sets_preparer():
    tok = token_of(SCOPED)
    assert act("evidence.request", EVIDENCE, tok, **{"X-Circularity-Preparer": "gap"}).status_code == 409
    r = act("evidence.request", EVIDENCE, tok)
    assert r.status_code == 200, r.text
    with SessionLocal() as s:
        prep = s.execute(text("SELECT preparer FROM action_journal WHERE action = 'evidence.request' ORDER BY seq DESC")).scalar()
    assert prep == SCOPED


def test_agent_token_never_approves():
    tok = token_of(SCOPED, "approver")
    body = {"case_id": "RT-1048", "rationale": "Redeploy to Site 3 as recommended; evidence reviewed.", "reviewed": True}
    r = act("decision.approve", body, tok, **{"X-Circularity-Confirmed": "true"})
    assert r.json()["error"]["code"] == "approval_required", r.text


def test_agent_token_writes_hold():
    tok = token_of(HELD)
    r = act("evidence.request", EVIDENCE, tok)
    assert r.status_code == 200 and "held" in r.json()["output"], r.text
    with SessionLocal() as s:
        row = s.execute(text("SELECT agent, requested_by, status FROM agent_proposal")).first()
    assert tuple(row) == (HELD, "planner-a", "pending")


def test_agent_token_limited_to_tools():
    tok = token_of(SCOPED)
    r = act("note.add", {"case_id": "RT-1051", "text": "x"}, tok)
    assert r.json()["error"]["code"] == "out_of_scope"


def test_revoked_credential_refused():
    cid, secret = issue(SCOPED)
    form = {"grant_type": "client_credentials", "client_id": cid, "client_secret": secret}
    tok = client.post("/oauth/token", data=form).json()["access_token"]
    assert act("evidence.request", EVIDENCE, tok).status_code == 200
    with SessionLocal() as s:
        agent_credentials.revoke(s, cid)
        s.commit()
    r = client.post("/oauth/token", data=form)
    assert r.status_code == 401 and r.json()["error"] == "invalid_client"
    assert act("evidence.request", EVIDENCE, tok).status_code == 401


def test_secret_shown_once_and_hashed():
    cid, secret = issue(SCOPED)
    with SessionLocal() as s:
        stored = s.execute(text("SELECT secret_hash FROM agent_credential WHERE client_id = :c"), {"c": cid}).scalar()
    assert stored.startswith("scrypt$") and secret not in stored
    out = call("agent.credentials", {"agent_id": SCOPED}, "admin")
    assert out["ok"] is True
    rows = out["output"]["credentials"]
    assert [r["client_id"] for r in rows] == [cid]
    assert secret not in str(out) and "secret_hash" not in str(out) and "scrypt" not in str(out)


def test_issue_and_revoke_actions_through_admin():
    out = call("agent.issueCredential", {"agent_id": SCOPED}, "admin")
    assert out["ok"] is True and out["output"]["client_secret"] and out["output"]["client_id"]
    assert call("agent.issueCredential", {"agent_id": SCOPED}, "planner.a")["error"]["code"] == "out_of_scope"
    done = call("agent.revokeCredential", {"client_id": out["output"]["client_id"]}, "admin")
    assert done["ok"] is True
    assert call("agent.credentials", {"agent_id": SCOPED}, "admin")["output"]["credentials"][0]["revoked_at"]


def test_agent_cannot_issue_credential():
    assert "agent." in FORBIDDEN_ACTIONS
    for action, body in (("agent.issueCredential", {"agent_id": SCOPED}), ("agent.revokeCredential", {"client_id": "x"})):
        r = client.post(
            f"/api/actions/{action}",
            json=body,
            headers=h("admin") | {"X-Circularity-Preparer": SCOPED, "X-Circularity-Confirmed": "true"},
        )
        assert r.json()["error"]["code"] == "approval_required", action
    # and the agent's own token, owned by an Admin, cannot either
    tok = token_of(SCOPED, "admin")
    assert (
        act("agent.issueCredential", {"agent_id": SCOPED}, tok, **{"X-Circularity-Confirmed": "true"}).json()["error"]["code"]
        == "approval_required"
    )


def test_agent_token_never_changes_access():
    tok = token_of(SCOPED, "admin")
    body = {"tenant": "Customer B", "reason": "needed for the audit"}
    r = act("access.requestTenant", body, tok, **{"X-Circularity-Confirmed": "true"})
    assert r.json()["error"]["code"] in ("approval_required", "out_of_scope"), r.text


def test_owner_deactivated_credential_stops():
    cid, secret = issue(SCOPED)
    form = {"grant_type": "client_credentials", "client_id": cid, "client_secret": secret}
    tok = client.post("/oauth/token", data=form).json()["access_token"]
    with SessionLocal() as s:
        state.put(s, "account_revoked", "planner-a", {"active": False, "revoked_after": datetime.now(UTC).isoformat()})
        s.commit()
    try:
        assert act("evidence.request", EVIDENCE, tok).status_code == 401
        assert client.post("/oauth/token", data=form).json()["error"] == "invalid_client"
    finally:
        with SessionLocal() as s:
            state.put(s, "account_revoked", "planner-a", {"active": True})
            s.commit()


def test_disabled_agent_token_refused():
    tok = token_of(SCOPED)
    with SessionLocal() as s:
        s.execute(text("UPDATE agent_identity SET enabled = false WHERE id = :i"), {"i": SCOPED})
        s.commit()
    assert act("evidence.request", EVIDENCE, tok).status_code == 401


def test_mcp_agent_token_names_the_agent_and_refuses_another():
    from di.mcp import policy
    from di.mcp.tools import TOOLS

    tok, tool = token_of(SCOPED), next(iter(TOOLS))
    with SessionLocal() as s:
        other = policy.call_tool(s, policy.Caller(tok, "gap", None), tool, {})
        mine = policy.call_tool(s, policy.Caller(tok, None, None), tool, {})
    assert other["ok"] is False and other["error"]["code"] == "conflict"
    assert mine["agent"] == SCOPED
    assert policy.effective_agent(tok, "gap") == SCOPED


def test_p9_13_14_f1_agent_token_refused_on_write_routes_outside_actions():
    """Review 13 F1 (rule 10): an agent's own token, owned by Admin, cannot use the write routes that are not actions."""
    tok = token_of(SCOPED, "admin")
    refused = [
        client.put("/api/access/delegations/decisions", json={"enabled": False}, headers=bearer(tok)),
        client.post("/api/sources/nope/connect", headers=bearer(tok)),
        client.post("/api/sources/nope/disconnect", headers=bearer(tok)),
        client.post("/api/journal/undo", json={"seqs": [999999999]}, headers=bearer(tok)),
        client.post("/api/v1/tasks", json={"kind": "noop"}, headers=bearer(tok)),
        client.patch("/api/v1/tasks/999999999", json={"action": "cancel"}, headers=bearer(tok)),
        client.delete("/api/v1/tasks/999999999", headers=bearer(tok)),
        client.post("/api/auth/stream-ticket", headers=bearer(tok)),
    ]
    for r in refused:
        assert r.status_code == 403, (r.request.method, r.request.url.path, r.status_code, r.text)
        assert r.json()["error"] == {"code": "out_of_scope", "message": "Agents cannot call this route."}
    person = client.put("/api/access/delegations/decisions", json={"enabled": True}, headers=h("admin"))
    assert person.status_code == 200, person.text
