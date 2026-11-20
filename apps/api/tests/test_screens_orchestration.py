"""B14: Process orchestration gives the demo's answers (fixtures/golden/screens/orchestration.json), for every account.

- /cases: the cases the page can show for each top-bar tenant filter, in brief, and the case shown first.
- /run/{id} for the 22 read-fixture cases: the run model (ten stages and their activity lines), the timeline, the
  signature and the models per stage (the same for every account that may see the case); the next step and the
  escalation draft per account; the journal and the events. The failure drill (?fail=0..9) for three cases.
Refusals: 403 tenant_boundary outside the account's tenants or warehouse.

Normalisation as in test_screens_case. `agent_calls` is always empty: the demo's come from agent runs in the browser
session (none at the start) and the server has none yet.
"""

import os

import pytest

from di import golden
from tests import starting
from tests.helpers import client, h
from tests.test_screens_case import same

G = golden.load("screens/orchestration")
ACCOUNTS = list(G["accounts"])
TENANT_FILTERS = ["All", "Customer A", "Customer B", "Customer C"]


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_cases(acct):
    for t in TENANT_FILTERS:
        r = client.get("/api/screens/orchestration/cases", params={"tenant": t}, headers=h(acct))
        assert r.status_code == 200, r.text
        got, want = r.json(), G["accounts"][acct]["cases"][t]
        assert [x["id"] for x in got["cases"]] == want["ids"]
        same(got["cases"], [G["rows"][i] for i in want["ids"]])
        assert got["default"] == want["default"]


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_run(acct):
    for cid, want in G["accounts"][acct]["run"].items():
        r = client.get(f"/api/screens/orchestration/run/{cid}", headers=h(acct))
        if "refused" in want:
            assert r.status_code == 403 and r.json()["error"]["code"] == want["refused"], (cid, r.text)
            continue
        assert r.status_code == 200, (cid, r.text)
        got = r.json()
        for k, v in G["runs"][cid].items():
            if k == "stage_models":  # B17 adds each card's validation line (test_stage_model_validation)
                got[k] = [[{"key": m["key"], "version": m["version"]} for m in ms] for ms in got[k]]
            same({k: got[k]}, {k: v})
        same({"next": got["next"], "escalation": got["escalation"]}, want)
        same(got["journal"], G["journal"][cid])
        same(got["events"], G["events"][cid])
        assert got["agent_calls"] == []
        assert got["trace_id"].startswith("trace-")


def test_agents_and_validation():
    """B17: /cases lists the agents (the page's Agents and services table); each model card has its validation line."""
    got = client.get("/api/screens/orchestration/cases", headers=h("admin")).json()
    assert [a["id"] for a in got["agents"]] == [a["id"] for a in golden.load("tools")["agents"]]
    assert set(got["agents"][0]) == {"id", "name", "step", "scopes", "limit"}
    run = client.get("/api/screens/orchestration/run/RT-1048", headers=h("admin")).json()
    cards = {m["key"]: m for ms in run["stage_models"] for m in ms}
    assert cards and all(m["validation"] for m in cards.values())
    if "condition-vision" in cards:
        assert cards["condition-vision"]["validation"] == "accuracy 94.2% · macro-F1 0.91"
    if "resale-price" in cards:
        assert cards["resale-price"]["validation"].startswith(("MAE $", "validation pending"))


@pytest.mark.parametrize("cid", ["RT-1048", "RT-1052", "RT-1003"])
def test_failure_drill(cid):
    for k, want in G["drills"][cid].items():
        got = client.get(f"/api/screens/orchestration/run/{cid}", params={"fail": k}, headers=h("admin")).json()
        same({"model": got["model"], "timeline": got["timeline"], "sig": got["sig"]}, want)
