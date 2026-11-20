"""B14: the Audit page's data (GET /api/screens/audit and its provenance and comments) gives the demo's answers, for all
11 accounts and three top-bar tenant filters (fixtures/golden/screens/audit.json, from
apps/web/scripts/golden/analytics_audit.mjs).

The golden file holds every entry once, in full (as the Admin sees them); per account it holds the ids of the entries
it sees, in order, and its evidence gaps. Each entry the server returns must equal the demo's entry with that id:
the fetch entries with their full provenance record (provFor), the event entries with the event.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.engine.jsmath import js_round
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/audit")
ENTRIES = {x["id"]: x for x in G["entries"]}
CASES = {c["id"]: c for c in golden.load("cases")}
_tokens: dict[str, dict] = {}


@pytest.fixture(scope="module", autouse=True)
def _start():
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
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


VIEWS = [pytest.param(acct, top, v, id=f"{acct}-{top}") for acct, tops in G["accounts"].items() for top, v in tops.items()]
_cache: dict[tuple[str, str], dict] = {}


def audit(acct: str, top: str) -> dict:
    if (acct, top) not in _cache:
        r = client.get("/api/screens/audit", params={"tenant_filter": top}, headers=h(acct))
        assert r.status_code == 200, r.text
        _cache[acct, top] = r.json()
    return _cache[acct, top]


@pytest.mark.parametrize(("acct", "top", "view"), VIEWS)
def test_entries(acct, top, view):
    out = audit(acct, top)["entries"]
    assert [x["id"] for x in out] == view["entry_ids"]
    for x in out:
        assert norm(x) == norm(ENTRIES[x["id"]]), x["id"]


@pytest.mark.parametrize(("acct", "top", "view"), VIEWS)
def test_gaps(acct, top, view):
    out = audit(acct, top)["gaps"]
    assert [[g["c"]["id"], g["e"]["k"]] for g in out] == view["gaps"]
    for g in out:
        c = CASES[g["c"]["id"]]
        assert g["c"]["assetId"] == c["assetId"]
        assert norm(g["e"]) == norm(next(e for e in c["evidence"] if e["k"] == g["e"]["k"]))


def test_gap_provenance():
    gaps = audit("admin", "All")["gaps"]
    assert norm([g["p"] for g in gaps]) == norm(G["gap_provenance"])


@pytest.mark.parametrize("acct", list(G["accounts"]))
def test_comments(acct):
    """The demo starts with no comments (S.cm = {})."""
    assert audit(acct, "All")["comments"] == G["comments"]


def test_provenance_of():
    """The data trace (provenanceOf): the record behind a fetch entry, and the reason for a gap."""
    fetch = next(x for x in G["entries"] if x["kind"] == "fetch" and x["status"] == "partial")
    r = client.get("/api/screens/audit/provenance", params={"case_id": fetch["caseId"], "key": fetch["key"]}, headers=h("admin"))
    assert r.status_code == 200, r.text
    assert norm(r.json()["p"]) == norm(fetch["p"])
    assert r.json()["c"]["id"] == fetch["caseId"]
    gap = audit("admin", "All")["gaps"][0]
    r = client.get("/api/screens/audit/provenance", params={"case_id": gap["c"]["id"], "key": gap["e"]["k"]}, headers=h("admin"))
    assert norm(r.json()["p"]) == norm(G["gap_provenance"][0])


def test_provenance_tenant_boundary():
    r = client.get("/api/screens/audit/provenance", params={"case_id": "RT-1048", "key": "insp"}, headers=h("planner-b"))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "tenant_boundary"


def test_comments_by_key():
    r = client.get("/api/screens/audit/comments", params={"key": "au:none"}, headers=h("finance"))
    assert r.status_code == 200
    assert r.json() == []


def test_every_account_is_covered():
    assert len(G["accounts"]) == 11
    assert sum(1 for x in G["entries"] if x["kind"] == "fetch") > 1000
