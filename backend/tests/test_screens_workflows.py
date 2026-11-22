"""B14: the Workflow Studio's reads give the demo's answers (fixtures/golden/screens/workflows.json), for every account.

The studio starts from demo state (the demo's S.wf, seeded into the "workflows" and "workflow_runs" collections), so the
list, the recent runs, the attention list and every workflow's history and last run must match the demo exactly. The
step counts and failed records are asserted as behaviour instead (plan 6 C5): they come from real runs only, and the
seeded runs never ran. Accounts without the Workflow Studio section get 403 out_of_scope.

**History: only runs that happened (plan 6 C8, a deliberate change).** The demo's history (frWfHistory) added up to 30
earlier runs derived from a workflow's counts; those never happened, so the server lists only the run records (or the
workflow's recorded last run when it has none). The history is compared with the demo's entries that were real
(`real_history`), and the rest is asserted as behaviour in tests/test_workflow_extras.py.
"""

import os

import pytest

from di.core import golden
from tests import starting
from tests.helpers import client, h, norm

G = golden.load("screens/workflows")
ACCOUNTS = list(G["accounts"])


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def studio(acct: str) -> bool:
    pages = G["accounts"][acct]["pages"]["integration"]
    return bool(pages and "studio" in pages)


def real_history(hist: list[dict]) -> list[dict]:
    """The demo's history without the runs it derived from the counts: its real runs or, when it had none, the
    workflow's last run (the newest entry; the derived ones are all earlier)."""
    real = [x for x in hist if x.get("real")]
    return real or hist[:1]


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
    assert norm(got["history"]) == norm(real_history(want["history"]))
    assert len(got["history"]) <= 1 or all(x.get("real") for x in got["history"])
    assert norm(got["run_from_last"]) == norm(want["run_from_last"])
    # behaviour, no longer the demo's numbers (plan 6 C5, decision D-Fabric): the step counts and failed records are
    # what a real run counted and held; the seeded last runs never ran, so they have none
    assert got["run_counts"] == {} and got["failed_rows"] == []
    assert got["saved"]["graph"] == w["graph"]


def test_detail_refusals():
    assert client.get("/api/screens/workflows/WF-999", headers=h("admin")).status_code == 404
    r = client.get("/api/screens/workflows/WF-101", headers=h("planner-a"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
    assert client.get("/api/screens/workflows").status_code == 401
