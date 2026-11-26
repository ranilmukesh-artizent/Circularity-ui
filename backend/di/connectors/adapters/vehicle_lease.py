"""Vehicle lease system (uc_lease, plan 9 P9-9.2): the lease returns of the used-car segment. Read only.

Written against source-sim's synthetic vehicle lease mock (source-sim/sim/vendors/vehicle_lease): no real lease system is
connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`); `?updatedSince=` delta reads.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it (as plm_wc, Windchill). It implements no
registry entry of its own: it fills the canonical models `asset` and `condition` for a car, keyed by the source's org
unit (schema.vin_key), which the used-car pack's intake trigger (resource `lease-returns`, status `returned`) and
gates read. It reads only; the charge to the lessee (`lessee_charge`, P9-9.20) is written by the instruction writer.

Resource and facts (snake case of the source's camelCase fields)
    lease_returns   asset.<vin key>      vin, return_kind (always `lease_end`), lease_ref (leaseId), book_value (the
                                         residual value), mileage_at_return (odometerAtReturn), mileage_lease_record
                                         (odometerLastService), contract_mileage (contractMileage: the excess-mileage
                                         charge's base, P9-9.20), model_year, segment, powertrain, return_center,
                                         seller_fleet_size
                    condition.<vin key>  odometer_statement_ref, odometer_not_actual
The two mileage fields exist on purpose: the lease record's reading and the reading taken at return are different
facts, and the pack's mapping hint (UC-03) picks `mileage_at_return`. `lesseeRef` (a code),
`leaseEnd` and `status` stay in the raw record: no fact.
"""

from collections.abc import Iterator

from sqlalchemy import text

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.schema import vin_key
from di.services.canonical.store import Fact

ASSET = {
    "vin": "vin", "leaseId": "lease_ref", "residualValue": "book_value", "odometerAtReturn": "mileage_at_return",
    "odometerLastService": "mileage_lease_record", "contractMileage": "contract_mileage", "modelYear": "model_year",
    "segment": "segment",
    "powertrain": "powertrain", "returnCenter": "return_center", "sellerFleetSize": "seller_fleet_size",
}  # fmt: skip
CONDITION = {"odometerStatementRef": "odometer_statement_ref", "odometerNotActual": "odometer_not_actual"}


def _org(client: SourceClient) -> str | None:
    """The org unit the source is bound to (None: shared)."""
    return client.session.execute(text("SELECT org_unit_id FROM source_system WHERE id = :i"), {"i": client.source_id}).scalar()


class VehicleLeaseAdapter(GenericAdapter):
    source_id = "uc_lease"
    base_path = "/vehicle-lease/api/v1"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    since_param = "updatedSince"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Vehicle lease system (synthetic)"
    source_type = "lease"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        def lease_returns(client: SourceClient, since: str | None) -> Iterator[Record]:
            org = _org(client)
            for r in self.flat(client, "lease_returns", "/lease-returns", "leaseId", since):
                yield Record(r.resource, r.ext_id, r.payload | {"org_unit_id": org}, r.request, r.changed)

        return [Resource("lease_returns", lease_returns)]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        key = vin_key(p.get("org_unit_id"), p["vin"])
        facts = [Fact("asset", key, "return_kind", "lease_end", "status", p.get("status"), "Lease return: kind lease_end")]
        facts += [Fact("asset", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in ASSET.items()]
        facts += [
            Fact("condition", key, to, p.get(src), src, p.get(src), "Camel case to snake case") for src, to in CONDITION.items()
        ]
        return keep(facts)


ADAPTER = VehicleLeaseAdapter()
