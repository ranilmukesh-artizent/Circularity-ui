"""B11: the case reads give the demo's answers (fixtures/golden/reads.json), for every account the golden file covers.

case.get, case.evidence, case.routes, case.trace, demand.find and asset.compare: 5 accounts x 22 cases each.
cases.list: 15 filter and sort inputs x 11 accounts. Each is called over HTTP, as the frontend does, from the
starting state (cases reopened, delegations on, no tenant grants).
"""

import pytest
from sqlalchemy import text

from di import golden, state
from di.cases import store
from di.db import engine
from tests.helpers import client, h, strict

READS = golden.load("reads")
CASE_ACTIONS = ["case.get", "case.evidence", "case.routes", "case.trace", "demand.find", "asset.compare"]


def call(action: str, body: dict, user: str) -> dict:
    r = client.post(f"/api/actions/{action}", json=body, headers=h(user))
    out = r.json()
    if out.get("ok"):
        return {"ok": True, "output": out["output"]}
    return {"ok": False, "error": out["error"]}


def setup_module():
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))
        # the starting state has an empty journal: the case run reads who acted from it
        conn.execute(text("DELETE FROM domain_event"))
        conn.execute(text("DELETE FROM case_stage_log WHERE seq IS NOT NULL"))
        conn.execute(text("DELETE FROM action_journal"))
    store.reset()
    state.reset()  # the workspace collections (events, notes ...) back to their starting values


def _case_params(action: str):
    return [
        pytest.param(acct, cid, id=f"{acct}-{cid}")
        for acct, by_case in READS["case_reads"].items()
        for cid in READS["case_ids"]
        if action in by_case[cid]
    ]


def _check(action: str, body: dict, user: str, expected: dict):
    got = call(action, body, user)
    assert strict(got) == strict(expected)


@pytest.mark.parametrize(("acct", "case_id"), _case_params("case.get"))
def test_case_get(acct, case_id):
    _check("case.get", {"case_id": case_id}, acct, READS["case_reads"][acct][case_id]["case.get"])


@pytest.mark.parametrize(("acct", "case_id"), _case_params("case.evidence"))
def test_case_evidence(acct, case_id):
    _check("case.evidence", {"case_id": case_id}, acct, READS["case_reads"][acct][case_id]["case.evidence"])


@pytest.mark.parametrize(("acct", "case_id"), _case_params("case.routes"))
def test_case_routes(acct, case_id):
    _check("case.routes", {"case_id": case_id}, acct, READS["case_reads"][acct][case_id]["case.routes"])


@pytest.mark.parametrize(("acct", "case_id"), _case_params("case.trace"))
def test_case_trace(acct, case_id):
    _check("case.trace", {"case_id": case_id}, acct, READS["case_reads"][acct][case_id]["case.trace"])


@pytest.mark.parametrize(("acct", "case_id"), _case_params("demand.find"))
def test_demand_find(acct, case_id):
    _check("demand.find", {"case_id": case_id}, acct, READS["case_reads"][acct][case_id]["demand.find"])


@pytest.mark.parametrize(("acct", "case_id"), _case_params("asset.compare"))
def test_asset_compare(acct, case_id):
    _check("asset.compare", {"case_id": case_id}, acct, READS["case_reads"][acct][case_id]["asset.compare"])


LIST_READS = [
    pytest.param(acct, x["input"], x["result"], id=f"{acct}-{k}")
    for acct, reads in READS["other_reads"].items()
    for k, x in enumerate(reads)
    if x["action"] == "cases.list"
]


@pytest.mark.parametrize(("acct", "body", "expected"), LIST_READS)
def test_cases_list(acct, body, expected):
    _check("cases.list", body, acct, expected)


def test_every_golden_read_is_covered():
    assert set(READS["case_reads"]) == {"admin", "planner-a", "planner-b", "wm-1", "executive"}
    assert all(set(CASE_ACTIONS) <= set(r) for by_case in READS["case_reads"].values() for r in by_case.values())
    assert len(LIST_READS) == 15 * 11
