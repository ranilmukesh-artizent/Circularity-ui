"""B14: the product screens give the demo's answers (fixtures/golden/screens/product.json), for every account.

- Returned assets: the rows in view for each top-bar tenant filter (All and each customer), the Expected toggle's
  count and the account's open notifications.
- Expected returns: the rows in view for each tenant filter, the count and the Contract Management source.
- The journey strip: visible or not, the run's stage and what steps 0 and 1 established, for the 22 read-fixture cases.
- Asset intelligence for the 22 cases: the per-case figures (the same for every account that may see the case) and the
  account's fleet, related assets, units and SKU counts; the default asset.
- Pools: hidden (403) while the demo's FEAT.pools is off.
Refusals: 403 out_of_scope without the page, 403 tenant_boundary outside the account's tenants or warehouse.

Normalisation as in test_screens_case: numbers to 1e-6, strict booleans, null equals a missing key (the demo's
undefined).
"""

import os

import pytest
from fastapi.testclient import TestClient

from di import golden, policy
from di.main import app
from tests import starting
from tests.test_screens_case import h, same

client = TestClient(app)
G = golden.load("screens/product")
ACCOUNTS = list(G["accounts"])
TENANT_FILTERS = ["All", "Customer A", "Customer B", "Customer C"]


def setup_module():
    if os.environ.get("B14_PARALLEL") != "1":
        starting.reset()


def page(acct: str, section: str) -> bool:
    return policy.can_page(policy.account(acct), "product", section)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_returned(acct):
    want = G["accounts"][acct]
    for t in TENANT_FILTERS:
        r = client.get("/api/screens/product/returned", params={"tenant": t}, headers=h(acct))
        if not page(acct, "received"):
            assert r.status_code == 403 and r.json()["error"]["code"] == "out_of_scope"
            return
        assert r.status_code == 200, r.text
        got = r.json()
        assert [x["id"] for x in got["cases"]] == want["returned"][t]
        same(got["cases"], [G["rows"][i] for i in want["returned"][t]])
        assert got["expected_count"] == want["expected_count"]
        same(got["notes"], want["notes"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_expected(acct):
    want = G["accounts"][acct]
    rows = {e["id"]: e for e in G["expected_rows"]}
    for t in TENANT_FILTERS:
        r = client.get("/api/screens/product/expected", params={"tenant": t}, headers=h(acct))
        if not page(acct, "expected"):
            assert r.status_code == 403
            return
        got = r.json()
        same(got["rows"], [rows[i] for i in want["expected"][t]])
        assert got["count"] == want["expected_count"]
        same(got["source"], want["source"])


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_journey(acct):
    for cid, want in G["accounts"][acct]["journey"].items():
        r = client.get(f"/api/screens/product/journey/{cid}", headers=h(acct))
        assert r.status_code == 200, r.text
        same(r.json(), want)


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_asset(acct):
    for cid, want in G["accounts"][acct]["asset"].items():
        r = client.get(f"/api/screens/product/asset/{cid}", headers=h(acct))
        if "refused" in want:
            assert r.status_code == 403 and r.json()["error"]["code"] == want["refused"], (cid, r.text)
            continue
        assert r.status_code == 200, (cid, r.text)
        got = r.json()
        for k, v in G["asset"][cid].items():
            same({k: got[k]}, {k: v})
        same(got["fleet"], [G["rows"][i] for i in want["fleet"]])
        for k in ("related", "units", "models", "customers", "journey"):
            same({k: got[k]}, {k: want[k]})


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_default_asset(acct):
    r = client.get("/api/screens/product/asset", headers=h(acct))
    if not page(acct, "asset"):
        assert r.status_code == 403
        return
    assert r.json()["case"]["id"] == G["accounts"][acct]["default_asset"]


@pytest.mark.parametrize("acct", ACCOUNTS)
def test_pools_hidden(acct):
    """The pool optimiser is off in the demo (FEAT.pools), so canPage('product', 'pools') is false for everyone."""
    assert client.get("/api/screens/product/pools", headers=h(acct)).status_code == 403


def test_unknown_case():
    assert client.get("/api/screens/product/asset/RT-9999", headers=h("admin")).status_code == 404
    assert client.get("/api/screens/product/journey/RT-9999", headers=h("admin")).json() == {"visible": False}
