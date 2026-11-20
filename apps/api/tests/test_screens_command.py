"""B14: the Command Center reads give what the facade (apps/web/src/api/command.ts) gives today, for all 11 accounts,
with the page's filters (tenant, site, class, route, time horizon; the table's view, due window, reason and search) and
view settings (Admin's senior view, the widened operational scope).

Golden data: fixtures/golden/screens/command.json (apps/web/scripts/golden/home_command.mjs), from the starting state.
Floats were rounded to 1e-6 and an unlimited approval limit written as "Infinity" by the golden script; the server's
answer is rounded the same way and sends null for no limit. Booleans compare strictly.

One value is not compared, by design (di/screens/command.py): kpis.counts.workflows. The demo counts its workflows only
once a page has opened them (S.wf is created lazily, so the count depends on what the session visited first); the server
always counts the catalogue. It is checked against the demo's catalogue size instead.
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden
from di.engine.jsmath import js_round
from di.main import app
from tests import starting

client = TestClient(app)
CMD = golden.load("screens/command")
ACCOUNTS = sorted(CMD)
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


def get(path: str, user: str, **params):
    r = client.get("/api/screens/command" + path, params=params, headers=h(user))
    assert r.status_code == 200, r.text
    return r.json()


def plain(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [plain(v) for v in x]
    return x


def expected(x):
    """The golden value, with "Infinity" (no approval limit) read as the server's null."""
    if x == "Infinity":
        return None
    if isinstance(x, dict):
        return {k: expected(v) for k, v in x.items()}
    if isinstance(x, list):
        return [expected(v) for v in x]
    return x


def same(got, want) -> None:
    assert starting.strict(plain(got)) == starting.strict(expected(want))


def case_params(kind: str):
    return [
        pytest.param(acct, i, id=f"{acct}-{i}-{'-'.join(f'{k}={v}' for k, v in x['filters'].items()) or 'none'}")
        for acct in ACCOUNTS
        for i, x in enumerate(CMD[acct][kind])
    ]


def test_every_account_is_in_the_golden_file():
    assert len(ACCOUNTS) == 11


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_layout(acct):
    for mode, want in CMD[acct]["layout"].items():
        same(get("/layout", acct, mode=mode), want)


KPI_CASES = [
    pytest.param(acct, mode, i, id=f"{acct}-{mode}-{i}")
    for acct in ACCOUNTS
    for mode, xs in CMD[acct]["kpis"].items()
    for i in range(len(xs))
]


@pytest.mark.parametrize(("acct", "mode", "i"), KPI_CASES)
def test_key_figures(acct, mode, i):
    want = CMD[acct]["kpis"][mode][i]
    got = get("/kpis", acct, mode=mode, **want["filters"])
    assert got["counts"].pop("workflows") == 35  # the demo's catalogue (docstring)
    want = {k: v for k, v in want.items() if k != "filters"}
    want["counts"] = {k: v for k, v in want["counts"].items() if k != "workflows"}
    same(got, want)


@pytest.mark.parametrize(("acct", "i"), case_params("charts"))
def test_charts(acct, i):
    want = CMD[acct]["charts"][i]
    same(get("/charts", acct, **want["filters"]), {k: v for k, v in want.items() if k != "filters"})


@pytest.mark.parametrize(("acct", "i"), case_params("exceptions"))
def test_exceptions(acct, i):
    want = CMD[acct]["exceptions"][i]
    same(get("/exceptions", acct, **want["filters"]), {k: v for k, v in want.items() if k != "filters"})


@pytest.mark.parametrize(("acct", "i"), case_params("actions"))
def test_actions_to_prioritise(acct, i):
    want = CMD[acct]["actions"][i]
    got = get("/actions", acct, **want["filters"])
    assert got["total"] == len(want["rows"])
    same(got["rows"], want["rows"])


@pytest.mark.parametrize("widen", [False, True])
@pytest.mark.parametrize("acct", ACCOUNTS)
def test_actions_on_me_and_handed_off(acct, widen):
    want = CMD[acct]["op_scopes"]["all" if widen else "default"]
    aome = get("/aome", acct, all=str(widen).lower())
    same(aome, {"items": want["aome"], "scope": want["scope"]})
    same(
        get("/handed", acct, all=str(widen).lower()),
        {"handed": want["handed"], "awaiting": want["awaiting"], "scope": want["scope"]},
    )


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_outcomes_to_confirm(acct):
    same(get("/outcomes", acct), CMD[acct]["outcomes"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_approvals_inbox(acct):
    same(get("/inbox", acct), CMD[acct]["inbox"])


TENANT_CASES = [pytest.param(acct, t, id=f"{acct}-{t}") for acct in ACCOUNTS for t in CMD[acct]["in_tenant"]]


@pytest.mark.parametrize(("acct", "tenant"), TENANT_CASES)
def test_the_tenant_menu_narrows_the_queues(acct, tenant):
    want = CMD[acct]["in_tenant"][tenant]
    same(get("/aome", acct, tenant=tenant), {"items": want["aome"], "scope": want["scope"]})
    same(get("/handed", acct, tenant=tenant), {"handed": want["handed"], "awaiting": want["awaiting"], "scope": want["scope"]})
    same(get("/outcomes", acct, tenant=tenant), want["outcomes"])
    got = get("/inbox", acct, tenant=tenant)
    same(
        {"decisions_awaiting": got["decisions_awaiting"], "cards": got["cards"]},
        {k: want[k] for k in ("decisions_awaiting", "cards")},
    )


def test_pre_approval_checks(session):
    """Nothing is submitted at the start, so the approval cards are empty; their checks (the demo's afRisks) are compared
    for every case with a recommendation instead."""
    from di import policy
    from di.actions.pipeline import Actor, CallContext
    from di.cases import store
    from di.reads import cases as case_reads
    from di.reads.workspace import af_risks

    want = CMD["admin"]["risks"]
    ctx = CallContext(actor=Actor(account=policy.account("admin")), session=session)
    got = {}
    for c in store.all_cases(session):
        if c["id"] in want:
            rt = case_reads.case_routes({"case_id": c["id"]}, ctx)
            ev = case_reads.case_evidence({"case_id": c["id"]}, ctx)
            got[c["id"]] = af_risks(c, rt, ev)
    assert len(got) == len(want) > 0
    same(got, want)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_integration_health(acct):
    same(get("/health", acct), CMD[acct]["health"])


def test_signed_out_is_refused():
    assert client.get("/api/screens/command/kpis").status_code == 401
