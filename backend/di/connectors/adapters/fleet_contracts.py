"""Fleet contract system (fleet, plan 9 P9-3.1): the lease contracts, their lines, returns and renewals. Read only.

Written against source-sim's synthetic fleet mock (source-sim/sim/generic/specs/fleet_contracts.py): no real contract
system is connected. API key in `x-api-key`; offset paging (`items`, `next`, `total`); `?updated_since=` delta reads.

Not one of the demo's 21 sources: it starts unregistered (no source_system row), so every demo screen and count is
unchanged. di.connectors.extra registers it and source.reconnect connects it (as plm_wc, Windchill). It implements no
registry entry of its own: it fills the canonical models `contract`, `contract_line` and the named lease demand that
the tool-fleet pack reads.

Resources and facts (snake case of the source's camelCase fields)
    contracts   contract.<contractId>       every contract field except `lineIds`' ordering (kept as `line_ids`)
    lines       contract_line.<serial>      every line field; the key is the tool's serial, not the line id
    renewals    demand.<demandId>           kind (lease), need_by, lease_rate, term_months, renew, site, tool_class,
                                            buyer (the customer), contract_ref
    returns     no fact: the open returns are read by the tool-return intake (P9-3.4) from the raw records
    history     no fact: the ended contracts are read by the renewal work (Phase 5) from the raw records
`proposals` and `draftLines` are written by Phase 5 (P9-5.5), never read here. Nothing is ever written to the source.
"""

from collections.abc import Iterator
from typing import Any

from di.connectors.base import Record, Resource
from di.connectors.generic import GenericAdapter, keep
from di.connectors.http import SourceClient
from di.services.canonical.store import Fact

CONTRACT = {
    "contractId": "contract_id", "customer": "customer", "market": "market", "startDate": "start_date",
    "endDate": "end_date", "noticeDate": "notice_date", "termMonths": "term_months", "status": "status",
    "rateCardVersion": "rate_card_version", "feeMonth": "fee_month", "keyAccount": "key_account", "ownerOrg": "owner_org",
    "renewalStatus": "renewal_status", "lineIds": "line_ids", "updatedAt": "updated_at",
}  # fmt: skip
LINE = {
    "lineId": "line_id", "contractId": "contract_id", "serial": "serial", "toolClass": "tool_class", "model": "model",
    "status": "status", "returnReason": "return_reason", "theftClaimOpen": "theft_claim_open", "claimRef": "claim_ref",
    "damageChargeOpen": "damage_charge_open", "chargeRef": "charge_ref", "feeMonth": "fee_month", "coverType": "cover_type",
    "coverActive": "cover_active", "coverUntil": "cover_until", "swapAllowed": "swap_allowed",
    "nonReturnFee": "non_return_fee", "monthsOnContract": "months_on_contract", "updatedAt": "updated_at",
}  # fmt: skip
DEMAND = {
    "kind": "kind", "needBy": "need_by", "rateMonth": "lease_rate", "termMonths": "term_months", "renew": "renew",
    "site": "site", "toolClass": "tool_class", "customer": "buyer", "contractId": "contract_ref",
}  # fmt: skip


def facts_of(model: str, key: str, doc: dict[str, Any], names: dict[str, str], transform: str) -> list[Fact]:
    return keep([Fact(model, key, to, doc.get(src), src, doc.get(src), transform) for src, to in names.items()])


class FleetContractsAdapter(GenericAdapter):
    source_id = "fleet"
    base_path = "/fleet/api/v1"
    auth_kind = "api_key"
    api_key_header = "x-api-key"
    provisioned = False  # no demo source: registered and connected by a person (di.connectors.extra)
    extra = True
    vendor = "Fleet contract system (synthetic)"
    source_type = "fleet"
    interval = 60
    owner = "Integration Engineering"

    def resources(self):
        return [
            Resource("contracts", self.read("contracts", "/contracts", "contractId")),
            Resource("lines", self.read("lines", "/contract-lines", "lineId")),
            Resource("returns", self.read("returns", "/returns", "returnId")),
            Resource("renewals", self.read("renewals", "/renewals", "demandId")),
            Resource("history", self.read("history", "/contract-history", "contractId")),
        ]

    def read(self, name: str, path: str, id_field: str):
        def reader(client: SourceClient, since: str | None) -> Iterator[Record]:
            return self.flat(client, name, path, id_field, since)

        return reader

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "contracts":
            return facts_of("contract", p["contractId"], p, CONTRACT, "Camel case to snake case")
        if record.resource == "lines":
            return facts_of("contract_line", p["serial"], p, LINE, "Camel case to snake case")
        if record.resource == "renewals":
            return facts_of("demand", p["demandId"], p, DEMAND, "Named lease demand")
        return []  # returns and history are read from the raw records


ADAPTER = FleetContractsAdapter()
