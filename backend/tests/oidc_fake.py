"""An in-process OpenID provider for tests (P9-8.9): an httpx MockTransport, so no network and no source-sim.

Owns: discovery, jwks and the token endpoint (client_secret_basic, PKCE S256, single-use codes), and `authorize()`,
which stands in for the person pressing a button at the provider. Never does: anything with a real identity product;
the key pair and the client secret are test values made here.
"""

import base64
import hashlib
import secrets
import time
from urllib.parse import parse_qs, urlparse

import httpx2
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "http://idp.test/directory"
INTERNAL = "http://idp-internal.test/directory"
CLIENT_ID = "circularity"
CLIENT_SECRET = "test-client-secret"
REDIRECT = "http://localhost:5173/api/auth/oidc/callback"


class FakeIdp:
    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, {"kid": "k1", "use": "sig", "alg": "RS256"})
        self.codes: dict[str, dict] = {}
        self.hosts: list[str] = []  # the host of every request the api made

    def authorize(self, url: str, email: str, name: str = "Test User", groups: list[str] | None = None, **claim_overrides) -> str:
        """The code the provider would hand back for this authorize URL (state and nonce are read from it)."""
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["code_challenge_method"] == "S256" and q["response_type"] == "code" and q["client_id"] == CLIENT_ID
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": email, "email": email, "name": name, "groups": groups or [],
                  "nonce": q["nonce"]} | claim_overrides  # fmt: skip
        code = secrets.token_urlsafe(16)
        self.codes[code] = {"challenge": q["code_challenge"], "claims": claims}
        return code

    def _id_token(self, claims: dict) -> str:
        now = int(time.time())
        return jwt.encode({"alg": "RS256", "kid": "k1"}, {"iat": now, "exp": now + 300} | claims, self.key)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.hosts.append(request.url.host)
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx2.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize", "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks", "userinfo_endpoint": f"{ISSUER}/userinfo",
            })  # fmt: skip
        if path.endswith("/jwks"):
            return httpx2.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if path.endswith("/token"):
            return self._token(request)
        return httpx2.Response(404)

    def _token(self, request: httpx2.Request) -> httpx2.Response:
        want = "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        if request.headers.get("authorization") != want:
            return httpx2.Response(401, json={"error": "invalid_client"})
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        entry = self.codes.pop(form.get("code", ""), None)
        digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
        if entry is None or base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != entry["challenge"]:
            return httpx2.Response(400, json={"error": "invalid_grant"})
        return httpx2.Response(200, json={"access_token": "at-" + secrets.token_hex(4), "token_type": "Bearer",
                                         "expires_in": 300, "id_token": self._id_token(entry["claims"])})  # fmt: skip

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handle)
