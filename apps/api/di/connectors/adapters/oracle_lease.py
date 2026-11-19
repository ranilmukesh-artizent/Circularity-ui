"""Oracle Lease and Finance Management (lease): contracts, lease assets, renewals (the demo's SOURCES.lease). Read only.

Also home of `GenericAdapter`, the base of the adapters for source-sim's generic, spec-driven mocks (B5): OAuth client
credentials, API key or Basic auth with the spec's demo credentials, the spec's paging (offset, page or cursor), and
`?updated_since=` deltas.

Delta cursor: the generic mocks stamp each document's change time but do not return it, so `Record.changed` is the
source's clock when the read started (an upper bound of every change it can contain). The next delta read asks for
everything changed after that, so an unchanged system answers with nothing and nothing changed during a read is missed.

Facts (lease has authority over ownership, lessee and contract term)
    asset.<ASSET_NUMBER>   lease_ref, contract_end, contract_start, owner_tenant, lessee (tenant key: CUSTOMER_A →
                           Customer A), lease_rate (USD per month), lease_term_months, contract_status, renewal_option;
                           from /leaseAssets: lease_status, ownership_type, original_cost, returned_on (and the owner
                           of assets not on a contract, e.g. MTR-2077 of the demo's conflict CF-31)
    demand.<LEASE_OPPORTUNITY_ID>   kind re_lease, asset_ref, lease_ref, need_by (option expiry), status, site,
                           proposed_term_months, proposed_rental
The demo's mapping: LEASE_CONTRACT_ID LC-004417 → asset.lease_ref (Pass-through); CONTRACT_END_DATE 2026-12-31
(ISO date); LESSEE_NAME CUSTOMER_A → asset.owner_tenant Customer A (Tenant key); MONTHLY_RENTAL 2400.00 USD → $2,400 /
month (Currency + period normalised).
"""

from decimal import Decimal

from di.canonical.store import Fact
from di.connectors.base import Record, Resource
from di.connectors.generic import (  # noqa: F401
    EUR_PER_USD,
    FX_NOTE,
    INR_PER_USD,
    GenericAdapter,
    iso_z,
    keep,
    tenant_name,
    to_usd,
)


class OracleLeaseAdapter(GenericAdapter):
    source_id = "lease"
    base_path = "/oracle-lease/fscmRestApi"
    items_key, next_key, next_param, size_param, page_size = "items", "nextOffset", "offset", "limit", 500

    def resources(self):
        return [
            Resource("leaseContracts", lambda c, s: self.flat(c, "leaseContracts", "/leaseContracts", "LEASE_CONTRACT_ID", s)),
            Resource("leaseAssets", lambda c, s: self.flat(c, "leaseAssets", "/leaseAssets", "ASSET_NUMBER", s)),
            Resource("leaseRenewals", lambda c, s: self.flat(c, "leaseRenewals", "/leaseRenewals", "RENEWAL_ID", s)),
        ]

    def map(self, record: Record) -> list[Fact]:
        p = record.payload
        if record.resource == "leaseContracts":
            return keep(self._contract(p))
        if record.resource == "leaseAssets":
            return keep(self._asset(p))
        if record.resource == "leaseRenewals":
            return keep(self._renewal(p))
        return []

    def _contract(self, p: dict) -> list[Fact]:
        key = p["ASSET_NUMBER"]
        cur = p.get("CURRENCY_CODE") or "USD"
        rental = p.get("MONTHLY_RENTAL")
        freq = (p.get("BILLING_FREQUENCY") or "MONTHLY").upper()
        per_month = {"MONTHLY": 1, "QUARTERLY": Decimal(1) / 3, "ANNUAL": Decimal(1) / 12, "YEARLY": Decimal(1) / 12}[freq]
        facts = [
            Fact("asset", key, "lease_ref", p["LEASE_CONTRACT_ID"], "LEASE_CONTRACT_ID", p["LEASE_CONTRACT_ID"], "Pass-through"),
            Fact("asset", key, "contract_end", p["CONTRACT_END_DATE"], "CONTRACT_END_DATE", p["CONTRACT_END_DATE"], "ISO date"),
            Fact(
                "asset",
                key,
                "contract_start",
                p.get("CONTRACT_START_DATE"),
                "CONTRACT_START_DATE",
                p.get("CONTRACT_START_DATE"),
                "ISO date",
            ),
            Fact("asset", key, "owner_tenant", tenant_name(p["LESSEE_NAME"]), "LESSEE_NAME", p["LESSEE_NAME"], "Tenant key"),
            Fact("asset", key, "lessee", tenant_name(p["LESSEE_NAME"]), "LESSEE_NAME", p["LESSEE_NAME"], "Tenant key"),
            Fact("asset", key, "lease_term_months", p.get("TERM_MONTHS"), "TERM_MONTHS", p.get("TERM_MONTHS"), "Integer"),
            Fact(
                "asset",
                key,
                "contract_status",
                (p.get("CONTRACT_STATUS") or "").lower() or None,
                "CONTRACT_STATUS",
                p.get("CONTRACT_STATUS"),
                "Status map",
            ),
            Fact(
                "asset",
                key,
                "renewal_option",
                (p.get("RENEWAL_OPTION") or "").lower() or None,
                "RENEWAL_OPTION",
                p.get("RENEWAL_OPTION"),
                "Option map",
            ),
        ]
        if rental is not None:
            usd = to_usd(Decimal(str(rental)) * per_month, cur)
            facts.append(
                Fact(
                    "asset",
                    key,
                    "lease_rate",
                    usd,
                    "MONTHLY_RENTAL",
                    f"{Decimal(str(rental)):.2f} {cur}",
                    "Currency + period normalised",
                )
            )
        return facts

    def _asset(self, p: dict) -> list[Fact]:
        key = p["ASSET_NUMBER"]
        facts = [
            Fact(
                "asset",
                key,
                "lease_status",
                (p.get("LEASE_STATUS") or "").lower() or None,
                "LEASE_STATUS",
                p.get("LEASE_STATUS"),
                "Status map",
            ),
            Fact(
                "asset",
                key,
                "ownership_type",
                (p.get("OWNERSHIP_TYPE") or "").lower() or None,
                "OWNERSHIP_TYPE",
                p.get("OWNERSHIP_TYPE"),
                "Code map",
            ),
        ]
        if p.get("ORIGINAL_COST") is not None:
            cur = p.get("CURRENCY_CODE") or "USD"
            facts.append(
                Fact(
                    "asset",
                    key,
                    "original_cost",
                    to_usd(p["ORIGINAL_COST"], cur),
                    "ORIGINAL_COST",
                    f"{p['ORIGINAL_COST']} {cur}",
                    "Currency" if cur == "USD" else f"Currency at {FX_NOTE[cur]}",
                )
            )
        if p.get("RETURN_DATE"):
            facts.append(Fact("asset", key, "returned_on", p["RETURN_DATE"], "RETURN_DATE", p["RETURN_DATE"], "ISO date"))
        if not p.get("LEASE_CONTRACT_ID"):
            # not on a returned contract (e.g. MTR-2077, still on lease): ownership comes from the asset record
            owner = p.get("OWNER_NAME") or p.get("LESSEE_NAME")
            facts.append(Fact("asset", key, "owner_tenant", tenant_name(owner), "OWNER_NAME", owner, "Tenant key"))
            if p.get("LESSEE_NAME"):
                facts.append(
                    Fact("asset", key, "lessee", tenant_name(p["LESSEE_NAME"]), "LESSEE_NAME", p["LESSEE_NAME"], "Tenant key")
                )
        return facts

    def _renewal(self, p: dict) -> list[Fact]:
        key = p["LEASE_OPPORTUNITY_ID"]
        status = {"FORECAST": "forecast", "CONFIRMED": "confirmed"}.get(p.get("STATUS") or "", (p.get("STATUS") or "").lower())
        facts = [
            Fact("demand", key, "kind", "re_lease", "RENEWAL_TYPE", p.get("RENEWAL_TYPE"), "Renewal type map"),
            Fact("demand", key, "asset_ref", p["ASSET_NUMBER"], "ASSET_NUMBER", p["ASSET_NUMBER"], "Pass-through"),
            Fact("demand", key, "lease_ref", p["LEASE_CONTRACT_ID"], "LEASE_CONTRACT_ID", p["LEASE_CONTRACT_ID"], "Pass-through"),
            Fact(
                "demand",
                key,
                "need_by",
                p.get("OPTION_EXPIRY_DATE"),
                "OPTION_EXPIRY_DATE",
                p.get("OPTION_EXPIRY_DATE"),
                "ISO date",
            ),
            Fact("demand", key, "status", status, "STATUS", p.get("STATUS"), "Status map"),
            Fact("demand", key, "site", p.get("SITE"), "SITE", p.get("SITE"), "Pass-through"),
            Fact(
                "demand",
                key,
                "proposed_term_months",
                p.get("PROPOSED_TERM_MONTHS"),
                "PROPOSED_TERM_MONTHS",
                p.get("PROPOSED_TERM_MONTHS"),
                "Integer",
            ),
        ]
        if p.get("PROPOSED_MONTHLY_RENTAL") is not None:
            cur = p.get("CURRENCY_CODE") or "USD"
            facts.append(
                Fact(
                    "demand",
                    key,
                    "proposed_rental",
                    to_usd(p["PROPOSED_MONTHLY_RENTAL"], cur),
                    "PROPOSED_MONTHLY_RENTAL",
                    f"{Decimal(str(p['PROPOSED_MONTHLY_RENTAL'])):.2f} {cur}",
                    "Currency + period normalised",
                )
            )
        return facts


ADAPTER = OracleLeaseAdapter()
