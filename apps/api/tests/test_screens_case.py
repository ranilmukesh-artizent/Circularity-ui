"""B14: the case pages give the demo's answers (fixtures/golden/screens/case.json), for every account.

For the 22 cases of the read fixture (every hero, RT-1062, RT-1044 and generated cases of each stage and readiness),
called over HTTP as the frontend will:
- GET /api/screens/case/{id}: the run, each stage's tag and summary (stData without its HTML tabs), the landing stage,
  the next step, the active clock and the approval role and limit, per account; the case record and stage summaries
  are the same for every account that may see the case.
- GET /api/screens/case/{id}/analysis: provenance, confidence and cost trace per route, ranking, tie-break, flips,
  life and demand, pool, plan, move, what-if, preparation, lease trail, rationale, spend, instruction, journal, events
  and the evidence pack.
Refusals: 403 out_of_scope without case pages, 403 tenant_boundary outside the account's tenants or warehouse.

Normalisation (`norm`): numbers rounded to 1e-6 as the golden file's `plain()` does; booleans strict; `null` and a
missing key are the same (the demo's `undefined` is dropped by JSON, the API sends null); an unlimited approval limit
is the golden "Infinity", sent as null.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.engine.jsmath import js_round
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/case")
ACCOUNTS = list(G["accounts"])
IDS = list(G["cases"])
_tokens: dict[str, dict] = {}


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def h(user: str) -> dict:
    if user not in _tokens:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _tokens[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _tokens[user]


def norm(x):
    if isinstance(x, bool):
        return ("bool", x)
    if x == "Infinity":
        return None
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items() if v is not None and norm(v) is not None}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


def diff(got, want, path="$"):
    """The first difference, for a readable failure."""
    if isinstance(want, dict) and isinstance(got, dict):
        for k in sorted(set(want) | set(got)):
            if k not in got or k not in want:
                return f"{path}.{k}: got {got.get(k, '<missing>')!r} want {want.get(k, '<missing>')!r}"
            d = diff(got[k], want[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(want, list) and isinstance(got, list):
        if len(got) != len(want):
            return f"{path}: {len(got)} items, want {len(want)}"
        for i, (a, b) in enumerate(zip(got, want, strict=True)):
            d = diff(a, b, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if got == want else f"{path}: got {got!r} want {want!r}"


def same(got, want):
    g, w = norm(got), norm(want)
    assert g == w, diff(g, w)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_case_page(acct):
    for cid in IDS:
        want = G["accounts"][acct][cid]
        r = client.get(f"/api/screens/case/{cid}", headers=h(acct))
        if "refused" in want:
            assert r.status_code == 403 and r.json()["detail"]["code"] == want["refused"], (cid, r.text)
            continue
        assert r.status_code == 200, (cid, r.text)
        got = r.json()
        for k in ("run", "tags", "landing", "next", "clock", "approval"):
            same(got[k], want[k])
        same(got["stages"], G["cases"][cid]["stages"])
        same(got["case"], G["cases"][cid]["case"])


@pytest.mark.parametrize("cid", IDS)
def test_analysis(cid):
    acct = next(a for a in ACCOUNTS if "refused" not in G["accounts"][a][cid])
    r = client.get(f"/api/screens/case/{cid}/analysis", headers=h(acct))
    assert r.status_code == 200, r.text
    got, want = r.json(), G["cases"][cid]["analysis"]
    for k in want:
        same(got[k], want[k])


def test_refusals():
    r = client.get("/api/screens/case/RT-9999", headers=h("admin"))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    r = client.get("/api/screens/case/RT-1048/analysis", headers=h("planner-b"))
    assert r.status_code == 403 and r.json()["detail"] == {
        "code": "tenant_boundary",
        "message": "RT-1048 belongs to Customer A, a tenant you cannot see. Request tenant access first.",
    }
    r = client.get("/api/screens/case/RT-1048", headers=h("wm-2"))
    assert r.json()["detail"]["message"] == "RT-1048 is at Warehouse 1, outside your warehouse."
    assert client.get("/api/screens/case/RT-1048", headers=h("developer")).json()["detail"]["code"] == "out_of_scope"
    assert client.get("/api/screens/case/RT-1048").status_code == 401
