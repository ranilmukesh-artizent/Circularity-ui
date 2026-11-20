"""Helpers shared by the api tests: one in-process client, signed-in headers per account, the actions call, and the
normalisations used to compare answers with the golden files (fixtures/golden, read with `di.golden.load`).

`conftest.py` also offers `client` and `login` as fixtures for tests that prefer them.
"""

from fastapi.testclient import TestClient

from di.engine.jsmath import js_round
from di.main import app

client = TestClient(app)
_headers: dict[str, dict] = {}


def h(user: str) -> dict:
    """The Authorization header for `user` (any demo account id), signed in once per test session."""
    if user not in _headers:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _headers[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _headers[user]


def call(action: str, body: dict, user: str) -> dict:
    """POST /api/actions/{action} as `user`; the JSON answer."""
    return client.post(f"/api/actions/{action}", json=body, headers=h(user)).json()


def strict(x):
    """Booleans tagged, so True and 1 differ when two structures are compared with == (JSON and the demo keep them
    apart; Python does not)."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, dict):
        return {k: strict(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [strict(v) for v in x]
    return x


def norm(x):
    """The golden dump's normalisation (numbers to 1e-6), with booleans kept strict."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x
