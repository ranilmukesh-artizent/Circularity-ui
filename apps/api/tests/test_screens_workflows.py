"""B14: the Workflow Studio's reads give the demo's answers (fixtures/golden/screens/workflows.json), for every account.

The studio is pure demo state (the demo's S.wf, seeded into the "workflows" and "workflow_runs" collections), so the
list, the recent runs, the attention list and every workflow's history, step counts, last run and failed records must
match the demo exactly. Accounts without the Workflow Studio section get 403 out_of_scope.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.engine.jsmath import js_round
from di.main import app
from tests import starting

client = TestClient(app)
G = golden.load("screens/workflows")
ACCOUNTS = list(G["accounts"])
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
    """The golden file's normalisation (numbers to 1e-6), with booleans kept strict."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


def studio(acct: str) -> bool:
    pages = G["accounts"][acct]["pages"]["integration"]
    return bool(pages and "studio" in pages)


def stat(w: dict) -> str:
    return "failing" if w["status"] == "published" and w.get("last") and w["last"]["state"] == "failed" else w["status"]


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_list(acct):
    r = client.get("/api/screens/workflows", headers=h(acct))
    if not studio(acct):
        assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
        return
    assert r.status_code == 200, r.text
    got = r.json()
    want = [{k: v for k, v in w.items() if k not in ("graph", "saved", "tpl")} | {"stat": stat(w)} for w in G["starting"]]
    assert norm(got["workflows"]) == norm(want)
    assert norm(got["runs"]) == norm(G["runs"])
    assert got["attention"] == G["attention"]
    c = got["counts"]
    assert c["total"] == len(G["starting"]) == c["published"] + c["draft"] + c["paused"] + c["failing"]
    assert c["failing"] == sum(1 for w in G["starting"] if stat(w) == "failing")


def test_list_filters():
    hd = h("developer")
    failing = client.get("/api/screens/workflows", params={"status": "failing"}, headers=hd).json()["workflows"]
    assert [w["id"] for w in failing] == [w["id"] for w in G["starting"] if stat(w) == "failing"]
    ingest = client.get("/api/screens/workflows", params={"cat": "Ingest", "src": "erp"}, headers=hd).json()["workflows"]
    assert [w["name"] for w in ingest] == ["Ingest · SAP S/4HANA"]
    found = client.get("/api/screens/workflows", params={"q": "depot"}, headers=hd).json()["workflows"]
    assert found and all(w["src"] == "repair" for w in found)


@pytest.mark.parametrize("wid", [w["id"] for w in G["starting"]])
def test_detail(wid):
    r = client.get(f"/api/screens/workflows/{wid}", headers=h("admin"))
    assert r.status_code == 200, r.text
    got, want = r.json(), G["detail"][wid]
    w = next(x for x in G["starting"] if x["id"] == wid)
    assert norm(got["workflow"]) == norm(w | {"stat": want["stat"]})
    assert norm(got["template"]) == norm(want["template"])
    assert norm(got["history"]) == norm(want["history"])
    assert norm(got["run_counts"]) == norm(want["run_counts"])
    assert norm(got["run_from_last"]) == norm(want["run_from_last"])
    assert got["failed_rows"] == want["failed_rows"]
    assert got["saved"]["graph"] == w["graph"]


def test_detail_refusals():
    assert client.get("/api/screens/workflows/WF-999", headers=h("admin")).status_code == 404
    r = client.get("/api/screens/workflows/WF-101", headers=h("planner-a"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
    assert client.get("/api/screens/workflows").status_code == 401
