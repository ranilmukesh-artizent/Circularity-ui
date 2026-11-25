"""Plan 9 P9-8.8 (story X-10) contract tests: the synthetic directory mock answers as an OpenID Connect provider.

Follows OpenID Connect Discovery 1.0 and Core 1.0 (authorization code flow, PKCE S256 per RFC 7636) and checks the
ID token signature against the published JWKS. All users are synthetic.
"""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from sim.main import app

BASIC = {"Authorization": "Basic " + base64.b64encode(b"circularity:circularity-demo-secret").decode()}
VERIFIER = "v" * 50
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
REDIRECT = "http://localhost:8000/api/auth/oidc/callback"


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fresh(client):
    client.post("/directory/_admin/reset").raise_for_status()


def authorize(client, hint="planner-b", challenge=CHALLENGE, method="S256"):
    params = {
        "response_type": "code",
        "client_id": "circularity",
        "redirect_uri": REDIRECT,
        "state": "st-1",
        "nonce": "n-1",
        "code_challenge": challenge,
        "code_challenge_method": method,
        "scope": "openid email profile",
        "login_hint": hint,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.get("/directory/authorize", params=params, follow_redirects=False)


def query_of(r) -> dict[str, list[str]]:
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)


def code_of(r) -> str:
    q = query_of(r)
    assert q["state"] == ["st-1"]
    return q["code"][0]


def exchange(client, code, verifier=VERIFIER, headers=BASIC):
    return client.post(
        "/directory/token",
        data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "redirect_uri": REDIRECT},
        headers=headers,
    )


def all_users(client) -> list[dict]:
    return client.get("/directory/api/users", params={"limit": 100}).json()["data"]


def test_directory_discovery_document(client):
    d = client.get("/directory/.well-known/openid-configuration").json()
    base = d["issuer"]
    assert base.endswith("/directory")
    assert d["authorization_endpoint"] == f"{base}/authorize"
    assert d["token_endpoint"] == f"{base}/token"
    assert d["jwks_uri"] == f"{base}/jwks"
    assert d["userinfo_endpoint"] == f"{base}/userinfo"
    assert "S256" in d["code_challenge_methods_supported"] and "RS256" in d["id_token_signing_alg_values_supported"]


def test_directory_code_flow_with_pkce(client):
    r = exchange(client, code_of(authorize(client)))
    assert r.status_code == 200, r.text
    body = r.json()
    head_b, pay_b, sig_b = body["id_token"].split(".")
    claims = json.loads(b64d(pay_b))
    assert claims["groups"] == ["circ-planners-customer-b"]
    assert claims["nonce"] == "n-1" and claims["aud"] == "circularity" and claims["sub"] == "planner-b"
    assert claims["iss"].endswith("/directory") and claims["email"].endswith("@example.com")
    assert claims["exp"] > claims["iat"] and claims["name"]
    jwk = client.get("/directory/jwks").json()["keys"][0]
    assert json.loads(b64d(head_b)) == {"alg": "RS256", "typ": "JWT", "kid": jwk["kid"]}
    numbers = rsa.RSAPublicNumbers(int.from_bytes(b64d(jwk["e"]), "big"), int.from_bytes(b64d(jwk["n"]), "big"))
    numbers.public_key().verify(b64d(sig_b), f"{head_b}.{pay_b}".encode(), padding.PKCS1v15(), hashes.SHA256())
    info = client.get("/directory/userinfo", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert info["sub"] == "planner-b" and info["groups"] == ["circ-planners-customer-b"]
    assert client.get("/directory/userinfo").status_code == 401


def test_directory_wrong_verifier_invalid_grant(client):
    r = exchange(client, code_of(authorize(client)), verifier="w" * 50)
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_directory_code_single_use(client):
    code = code_of(authorize(client))
    assert exchange(client, code).status_code == 200
    again = exchange(client, code)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


def test_directory_client_auth_required(client):
    code = code_of(authorize(client))
    assert exchange(client, code, headers={}).status_code == 401
    bad = {"Authorization": "Basic " + base64.b64encode(b"circularity:nope").decode()}
    assert exchange(client, code, headers=bad).json()["error"] == "invalid_client"


def test_directory_pkce_required(client):
    r = authorize(client, challenge=None, method=None)
    assert query_of(r)["error"] == ["invalid_request"]
    assert query_of(authorize(client, method="plain"))["error"] == ["invalid_request"]


def test_directory_authorize_page_lists_users(client):
    r = authorize(client, hint=None)
    assert r.status_code == 200 and "planner.customer-b@example.com" in r.text
    assert "login_hint=planner-b" in r.text
    assert authorize(client, hint="nobody").status_code == 400


def test_directory_admin_has_no_group(client):
    assert next(u for u in all_users(client) if u["id"] == "admin")["groups"] == []


def test_directory_joiner_admin(client):
    emails = lambda: [u["email"] for u in all_users(client)]  # noqa: E731
    assert "joiner.one@example.com" not in emails()
    body = {"email": "joiner.one@example.com", "groups": ["circ-planners-customer-b"]}
    r = client.post("/directory/_admin/users", json=body)
    assert r.status_code == 201, r.text
    assert "joiner.one@example.com" in emails()
    uid = r.json()["id"]
    assert client.delete(f"/directory/_admin/users/{uid}").status_code == 204
    assert "joiner.one@example.com" not in emails()
    assert client.delete(f"/directory/_admin/users/{uid}").status_code == 404


def test_directory_users_and_groups_paged(client):
    p1 = client.get("/directory/api/users", params={"offset": 0, "limit": 5}).json()
    assert len(p1["data"]) == 5 and p1["next"] == 5
    seen = list(p1["data"])
    off = p1["next"]
    while off is not None:
        p = client.get("/directory/api/users", params={"offset": off, "limit": 5}).json()
        seen += p["data"]
        off = p["next"]
    assert len(seen) == 13  # 11 accounts + 2 deputies; the joiner is not active
    groups = client.get("/directory/api/groups").json()["data"]
    g = next(x for x in groups if x["name"] == "circ-planners-customer-b")
    assert g["members"] == ["planner-b"]
