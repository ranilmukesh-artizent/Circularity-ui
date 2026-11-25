"""Synthetic directory with OpenID Connect sign-in and a users API (plan 9, P9-8.8, story X-10).

Owns: the mock `directory` (source id `directory`), mounted at /directory: OIDC discovery, authorize (a page that
lists the seeded users, or an immediate redirect with `login_hint`), token (authorization code with PKCE S256,
client_secret_basic), jwks, userinfo; `api/users` and `api/groups` for a pull sync; `_admin` routes to add a joiner,
remove a leaver or reset. Never does: persist anything (see models.py), name or imitate a real identity product, or
hold real people: every user is synthetic with an @example.com email.

Not a demo source: it is not in sim/core/registry.py and has no Postgres schema, so the demo's 21 systems and its
counts stay as they were. Mocks are discovered at start-up, so adding this package registers it; restart source-sim.

Documentation followed
    OpenID Connect Discovery 1.0 (provider metadata at /.well-known/openid-configuration).
    OpenID Connect Core 1.0 (authorization code flow, ID token claims iss/sub/aud/exp/iat/nonce, UserInfo, JWKS).
    RFC 7636 (PKCE, S256), RFC 7517 (JWK), RFC 6749 section 5.2 (token error bodies).

Demo client: `circularity` / `circularity-demo-secret` (HTTP Basic), a demo credential, not a secret.
Issuer: DIRECTORY_ISSUER, default http://localhost:8100/directory.

ASSUMPTION: any redirect_uri is accepted (a mock, never exposed); the token call must repeat the same one.
ASSUMPTION: the `groups` claim is always present (empty for the admin); `email_verified` is true.
"""

from sim.core.mock import Mock
from sim.vendors.directory.routes import router
from sim.vendors.directory.seed import ensure, reset

MOCK = Mock("directory", router, ensure, reset, "Directory (OIDC)")
