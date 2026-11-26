"""Plan 9, P9-9.6: the vehicle pricing guide (source `uc_price`) adapter against source-sim's synthetic mock.

`uc_price` is no demo source: it starts unregistered. Registered and synced it fills `market.retail_guide_price` and
`market.wholesale_guide_price` for each car of its org unit already in the store (the lease or dealer system's `vin`
fact), keyed `vin_key(org unit, vin)`. The joint sync test of the auction and pricing mocks is
`test_adapters_auction_pricing_map_facts` in test_adapter_vehicle_auction.py; this file runs the mapping and the
no-cars case on literal records.
"""

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.services.canonical.schema import check_fact, vin_key

SID = "uc_price"
ORG = "Customer A"


def vin(n: int) -> str:
    return f"SYNUC{n:012d}"


VALUE = {
    "vin": vin(1), "retail": 24000, "wholesale": 21500, "segment": "suv", "band": "0-40k", "asOf": "2026-10-07T09:00:00+00:00",
    "org_unit_id": ORG,
}  # fmt: skip


def test_adapter_vehicle_pricing_maps_the_guide_values():
    facts = ADAPTERS[SID].map(Record("values", vin(1), VALUE))
    assert {f.model for f in facts} == {"market"} and {f.key for f in facts} == {vin_key(ORG, vin(1))}
    assert {f.field: f.value for f in facts} == {"retail_guide_price": 24000, "wholesale_guide_price": 21500}
    assert [(f.field, check_fact(f)) for f in facts if check_fact(f)] == []


def test_adapter_vehicle_pricing_writes_no_empty_fact():
    facts = ADAPTERS[SID].map(Record("values", vin(1), VALUE | {"wholesale": None}))
    assert {f.field for f in facts} == {"retail_guide_price"}


def test_adapter_vehicle_pricing_is_an_extra_source_that_starts_unregistered():
    a = ADAPTERS[SID]
    assert (a.extra, a.provisioned, a.base_path) == (True, False, "/vehicle-pricing/v3")
    assert a.vendor == "Vehicle pricing guide (synthetic)"
