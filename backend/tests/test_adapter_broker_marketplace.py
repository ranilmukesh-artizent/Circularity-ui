"""Plan 9, P9-10.5: the broker marketplace (source `tn_broker`) adapter against source-sim's synthetic mock.

Starts unregistered like every extra source. The mapping tests run on literal records; the sync test is skipped, with the
reason, when source-sim does not serve the mock (restart it, R14).
"""

import httpx
import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.connectors.sync import run_sync
from di.core.config import get_settings
from di.core.db import SessionLocal, engine
from di.services.canonical import store
from di.services.canonical.schema import MODEL_FIELDS, check_fact
from tests import starting
from tests.helpers import call

SIM = get_settings().source_sim_url
SID = "tn_broker"
API = SIM + "/broker-market/api"
KEY = {"x-api-key": "tn_broker-demo-key"}
ORG = "Customer A"

BIDS = [
    {"bidId": "BID-4410-A", "model": "RRU-4410", "qty": 25, "unitPrice": 3400, "buyerCountry": "US", "domestic": True,
     "endUserScreening": {"result": "clear", "ref": "EUS-0101"}},
    {"bidId": "BID-4410-B", "model": "RRU-4410", "qty": 60, "unitPrice": 3250, "buyerCountry": "US", "domestic": True,
     "endUserScreening": {"result": "clear", "ref": "EUS-0102"}},
]  # fmt: skip
CLEARED = {"model": "RRU-4410", "price": 3350, "soldAt": "2026-09-20", "sales": 2}


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = :s"), {"s": SID})
        conn.execute(text("DELETE FROM canonical WHERE model = 'market' AND key IN ('RRU-4410', 'BBU-2200', 'RAD-7700')"))


def setup_module():
    starting.reset()
    _forget()


def teardown_module():
    starting.reset()
    _forget()


def served() -> bool:
    try:
        return httpx.get(API + "/bids", headers=KEY, timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


needs_mock = pytest.mark.skipif(not served(), reason="source-sim does not serve the broker mock: restart it (R14)")


def test_broker_fields_exist():
    assert MODEL_FIELDS["market"]["broker_bids"].type == "list"
    assert MODEL_FIELDS["market"]["cleared_price"].type == "number"


def test_adapter_broker_marketplace_maps_bids_per_model():
    assert ADAPTERS[SID].extra and ADAPTERS[SID].source_type == "broker_marketplace"
    facts = ADAPTERS[SID].map(Record("bids", "RRU-4410", {"model": "RRU-4410", "bids": BIDS}))
    assert [(f.model, f.key, f.field) for f in facts] == [("market", "RRU-4410", "broker_bids")]
    assert facts[0].value == BIDS and check_fact(facts[0]) is None


def test_adapter_broker_marketplace_maps_the_cleared_price():
    facts = ADAPTERS[SID].map(Record("cleared", "RRU-4410", CLEARED))
    assert [(f.model, f.key, f.field, f.value) for f in facts] == [("market", "RRU-4410", "cleared_price", 3350)]
    assert check_fact(facts[0]) is None


def test_broker_starts_unregistered():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = :i"), {"i": SID}).scalar_one() == 0
    assert run_sync(SID, "manual")["status"] == "skipped"


@needs_mock
def test_adapter_broker_marketplace_sync():
    with SessionLocal() as s:
        assert extra.register(s, SID, ORG) == SID
        s.commit()
    r = call("source.reconnect", {"source_id": SID}, "developer")
    assert r["ok"], r
    out = run_sync(SID, "manual", full=True)
    assert out["status"] == "ok" and out["records_failed"] == 0, out
    with SessionLocal() as s:
        rru, bbu, rad = (store.get(s, "market", m) for m in ("RRU-4410", "BBU-2200", "RAD-7700"))
    assert rru is not None and rru["data"]["broker_bids"][0]["unitPrice"] == 3400 and rru["data"]["cleared_price"] > 0
    assert bbu is not None and bbu["data"]["broker_bids"][0]["unitPrice"] == 1450
    assert rad is not None and rad["data"]["broker_bids"][0]["bidId"] == "BID-7700-OS"
