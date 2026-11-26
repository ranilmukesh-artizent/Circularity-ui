"""Plan 9, P9-13.2 (story X-13): a leased used car or medical device carries the lease's residual to the close, where the case
shows the gain or loss of the sale against it. The residual is the lease contract's (evidence type `lease_residual`); the
proceeds are the ERP's retirement answer. An industrial lease contract states no residual and nothing changes for it.

The ERP client is stubbed (see test_x13_asset_retirement): nothing calls the shared source-sim.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.store import Fact
from di.services.execution.residual import Residual, evidence, residual_result
from di.services.modeler.pack import load_pack
from tests import ucfixtures as uc
from tests.test_uc_follow_through import _approve, _open, _run
from tests.test_x13_asset_retirement import fresh  # noqa: F401 - the autouse stub of the ERP and the dealer system

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

NOW = datetime(2026, 10, 20, tzinfo=UTC)


def _case(**asset) -> dict:
    recs = evidence(asset, NOW) if asset else []
    return {"id": "RT-1", "evidenceRecords": recs}


LEASE = {"lease_ref": "LC-900001", "lease_residual": 18000, "lease_residual_currency": "USD"}


def test_x_13_lease_residual_gain_loss():
    r = residual_result(_case(**LEASE), {"proceeds": 19250.00})
    assert r == Residual("LC-900001", Decimal("18000.00"), Decimal("19250.00"), Decimal("1250.00"), "USD")


def test_x_13_lease_residual_loss():
    r = residual_result(_case(**LEASE), {"proceeds": 16400.00})
    assert r is not None and r.gain_loss == Decimal("-1600.00") and r.contract_ref == "LC-900001"


def test_x_13_no_residual_no_line():
    assert residual_result(_case(), {"proceeds": 19250.00}) is None  # no lease evidence
    assert residual_result(_case(lease_ref="LC-1"), {"proceeds": 1}) is None  # a lease that states no residual
    assert residual_result(_case(**LEASE), None) is None  # no ERP answer yet


def test_x_13_industrial_lease_untouched():
    """An industrial contract's document has no residual fields, so the adapter writes no residual fact; one that states a
    residual (a used-car or medical lease) writes it, in its own currency."""
    adapter = ADAPTERS["lease"]
    doc = {
        "LEASE_CONTRACT_ID": "LC-004417",
        "ASSET_NUMBER": "MTR-2041",
        "CONTRACT_END_DATE": "2026-12-31",
        "LESSEE_NAME": "CUSTOMER_A",
        "CONTRACT_STATUS": "BOOKED",
        "TERM_MONTHS": 36,
        "MONTHLY_RENTAL": 2400.0,
        "CURRENCY_CODE": "USD",
    }
    assert not [f for f in adapter.map(Record("leaseContracts", "LC-004417", doc)) if f.field.startswith("lease_residual")]
    got = {f.field: f.value for f in adapter.map(Record("leaseContracts", "LC-900001", doc | {"RESIDUAL_VALUE": 18000.0}))}
    assert got["lease_residual"] == 18000.0 and got["lease_residual_currency"] == "USD"


def test_x_13_packs_with_residual_are_the_leased_ones():
    on = {k for k in ("used_cars", "medical_rental", "telecom_network", "tool_fleet", "device", "industrial")
          if load_pack(k).close.lease_residual}  # fmt: skip
    assert on == {"used_cars", "medical_rental"}


def test_x_13_resale_stores_residual_on_case():
    key = uc.vin_key(uc.ORG, uc.vin(1))
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("asset", key, f, v) for f, v in LEASE.items()])
        s.commit()
    c = _open(1)
    sale = sum(t["amt"] for t in c["recommendation"]["terms"] if t["kind"] == "sale")
    _approve(c)
    _run(c["id"], 4)
    after = uc.get(c["id"])
    res = after["finance"]["residual"]
    # the dealer lease system (uc_lease) names the contract on file when the car is opened
    assert res["contract_ref"] == "LS-0001" and res["residual"] == 18000.0 and res["proceeds"] == sale
    assert res["gain_loss"] == round(sale - 18000, 2)
